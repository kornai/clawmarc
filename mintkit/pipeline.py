"""Run ordered prepare, embedding, signing, and checkpoint stages."""

import json
import shutil
import sys
import tempfile
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import asdict
from itertools import islice
from pathlib import Path

from . import _ref, manifest
from .artifacts import CacheWriter, OutputWriter, tsv
from .checkpoint import Journal, exclusive_run, window_identity
from .operations import read_run
from .produce import Producer, TextCache, failure, prepared_template
from .sources._io import sha256_file
from .sources.base import select
from .sources.folder import FolderSource
from .timing import Timing


def _write_retrieval_inputs(run_dir, selection, minted):
    if not (selection.queries or selection.qrels):
        return 0
    restricted = selection.restrict_qrels(minted)
    queries = [q for q in selection.queries if any(g > 0 for g in restricted.get(q.qid, {}).values())]
    with (
        (run_dir / "queries.jsonl").open("w", encoding="utf-8") as stream,
        (run_dir / "qrels.tsv").open("w", encoding="utf-8", newline="") as judgments,
    ):
        writer = tsv(judgments)
        writer.writerow(("qid", "doc_id", "relevance"))
        for query in queries:
            stream.write(json.dumps({"qid": query.qid, "text": query.text}, ensure_ascii=False) + "\n")
            for doc_id, grade in restricted[query.qid].items():
                writer.writerow((query.qid, doc_id, grade))
    return len(selection.queries) - len(queries)


def _prepare(producer, doc):
    started = time.perf_counter()
    try:
        with producer.timing.measure("prepare"):
            prep = producer.prepare(doc)
        return prep, None, started
    except Exception as exc:
        stage = "extract" if isinstance(exc, _ref.ExtractionError) else "prepare"
        return None, failure(doc.doc_id, producer.spec.alias if producer.spec else "no-embed", stage, exc), started


def _prepared_windows(selected, journal, producer, executor):
    args = producer.args
    size = args.sort_window
    ahead = max(1, args.max_inflight // size) if executor else 1
    docs = iter(selected.iter_docs())
    pending = deque()
    resumed = len(journal.windows)
    index = 0
    while True:
        while len(pending) < ahead:
            with producer.timing.measure("read"):
                batch = list(islice(docs, size))
            if not batch:
                break
            identity = window_identity(batch)
            if index < resumed:
                if journal.identity(index) != identity:
                    raise ValueError(f"Source changed in checkpoint window {index}")
            else:
                jobs = [executor.submit(_prepare, producer, doc) for doc in batch] if executor else []
                pending.append((identity, batch, jobs))
            index += 1
        if not pending:
            if index < resumed:
                raise ValueError("Source now ends before the last checkpoint")
            return
        producer.timing.depths = {"prepared_windows": len(pending), "prepare_documents": len(pending) * size}
        identity, batch, jobs = pending.popleft()
        yield identity, batch, jobs


def _complete_window(producer, batch, jobs, prep_pool, sign_pool):
    ready = [job.result() for job in jobs] if jobs else [_prepare(producer, doc) for doc in batch]
    prepared = {index: prep for index, (prep, error, _) in enumerate(ready) if error is None}
    vectors, errors = producer.encode_window(prepared, prep_pool)
    alias = producer.spec.alias if producer.spec else "no-embed"

    def pack(index, doc):
        prep, error, started = ready[index]
        row = {"doc_id": doc.doc_id}
        if error is None and index in errors:
            _, exc = errors[index]
            error = failure(doc.doc_id, alias, "embed", exc)
        if error is None:
            try:
                with producer.timing.measure("pack_sign"):
                    row["results"], caches = producer.pack_all(prep, vectors.get(index, {}))
                row["object_sha256"] = prep.object_sha256.hex()
                if producer.args.keep_chunk_vectors:
                    row["template"] = prepared_template(prep, include_preimage=producer.args.include_preimage)
                    row["caches"] = caches
                allowance = prep.content_policy.get("max_text_prefix_chars", 0) or 0
                if producer.args.keep_full_text and prep.content_policy.get("allow_text_prefix") and (
                    prep.content_policy["name"] == "public_library_science" or len(prep.extracted_text) <= int(allowance)
                ):
                    row["full_text"] = prep.extracted_text
                if index in vectors:
                    plans = [plan for plan, _ in vectors[index].values()]
                    row["tokens"] = sum(sum(plan.token_counts) for plan in plans)
                    row["chunks"] = sum(len(plan.chunks) for plan in plans)
            except Exception as exc:
                error = failure(doc.doc_id, alias, "pack_sign", exc)
        if error is not None:
            row = {"doc_id": doc.doc_id, "failure": error}
        return row, started

    jobs = [sign_pool.submit(pack, i, doc) for i, doc in enumerate(batch)] if sign_pool else []
    return [job.result() for job in jobs] if jobs else [pack(i, doc) for i, doc in enumerate(batch)]


def _publish(run_dir, alias, spec, reductions, args, journal, *, first, judged_ids):
    minted = set()
    failed = documents = 0
    with tempfile.TemporaryDirectory(prefix=".publish-", dir=run_dir) as path:
        work = Path(path)
        with ExitStack() as stack:
            writers = {red.label: OutputWriter(stack, work, spec, red, args) for red in reductions}
            caches = {}
            if args.keep_chunk_vectors and spec is not None:
                for key in dict.fromkeys(red.chunking_label for red in reductions):
                    caches[key] = CacheWriter(stack, work / "chunks" / key, spec.dim)
            docs = None
            if first and args.record_docs:
                docs = tsv(stack.enter_context((work / "docs.tsv").open("w", encoding="utf-8", newline="")))
                docs.writerow(("doc_id", "object_sha256"))
            text = None
            if args.keep_full_text:
                text = stack.enter_context((work / "full_text.jsonl").open("w", encoding="utf-8"))
            for sequence, row in enumerate(journal.rows()):
                doc_id = row["doc_id"]
                if "failure" in row:
                    failed += 1
                    continue
                results = row["results"]
                for label, item in results.items():
                    writers[label].append(doc_id, item)
                for key, cache in caches.items():
                    cache.append(sequence, doc_id, row["template"], row["caches"].get(key))
                documents += bool(results)
                if results and doc_id in judged_ids:
                    minted.add(doc_id)
                if docs is not None and results:
                    primary = next(iter(results.values()))
                    docs.writerow((doc_id, primary.get("meta", {}).get("artifact", {}).get("sha256", row.get("object_sha256", ""))))
                if text is not None and "full_text" in row and results:
                    text.write(json.dumps({"doc_id": doc_id, "text": row["full_text"]}, ensure_ascii=False) + "\n")
        for category in ("cards", "vectors", "chunks"):
            if (work / category).is_dir():
                target = run_dir / category / alias
                target.parent.mkdir(exist_ok=True)
                if target.exists():
                    shutil.rmtree(target)  # Outputs are reproducible from the committed journal.
                (work / category).replace(target)
        if (work / "docs.tsv").is_file():
            (work / "docs.tsv").replace(run_dir / "docs.tsv")
        if (work / "full_text.jsonl").is_file():
            (run_dir / "text").mkdir(exist_ok=True)
            (work / "full_text.jsonl").replace(run_dir / "text" / f"{alias}.jsonl")
        progress = {label: writer.result() for label, writer in writers.items()}
    return {
        "model": spec.name if spec else None, "profile": spec.profile if spec else 0,
        "cards": sum(item["cards"] for item in progress.values()), "documents": documents,
        "failed": failed, "reductions": progress,
    }, minted


def _mint_model(run_dir, run, selected, alias, spec, reductions, args, source, failures, first, judged_ids, timing_data, text_cache):
    journal = Journal(run_dir / ".checkpoints" / alias)
    def log_failures(rows):
        for row in rows:
            if "failure" in row:
                failures.write(json.dumps(row["failure"], ensure_ascii=False) + "\n")
        failures.flush()

    if journal.windows:
        log_failures(journal.rows())
    error = None
    timing = Timing(args.device if spec else "cpu")
    new_cards = tokens = chunks = 0
    with timing:
        try:
            producer = Producer(args, source.name, spec, reductions, timing, text_cache)
            with ExitStack() as stack:
                prep_pool = stack.enter_context(ThreadPoolExecutor(args.prep_workers)) if args.threads else None
                sign_pool = stack.enter_context(ThreadPoolExecutor(args.sign_workers)) if args.threads and args.sign_workers > 1 else None
                for identity, batch, jobs in _prepared_windows(selected, journal, producer, prep_pool):
                    completed = _complete_window(producer, batch, jobs, prep_pool, sign_pool)
                    rows = [row for row, _ in completed]
                    with timing.measure("write", len(rows)):
                        journal.commit(identity, rows)
                        log_failures(rows)
                    new_cards += sum(bool(row.get("results")) for row in rows)
                    tokens += sum(row.get("tokens", 0) for row in rows)
                    chunks += sum(row.get("chunks", 0) for row in rows)
                    timing.record_latency(time.perf_counter() - started for _, started in completed)
                    if not args.quiet and len(journal.windows) % 10 == 0:
                        print(f"\r{alias}: {len(journal.windows)} windows, {new_cards} documents this session", end="", file=sys.stderr, flush=True)
                    if args.fail_fast and (failed := next((row["failure"] for row in rows if "failure" in row), None)):
                        raise RuntimeError(f"{failed['doc_id']}: {failed['error']}")
        except (Exception, KeyboardInterrupt) as exc:
            error = exc
        with timing.measure("flush"):
            journal = Journal(journal.directory)
            output, minted = _publish(
                run_dir, alias, spec, reductions, args, journal, first=first, judged_ids=judged_ids,
            )
        run["outputs"][alias] = output
    timing_data[alias] = timing.result(
        new_cards, {"read": 1, "prepare": args.prep_workers if args.threads else 1,
                    "chunk": args.prep_workers if args.threads else 1, "embed": 1, "pack_sign": args.sign_workers if args.threads else 1, "write": 1},
        tokens, chunks,
    )
    if not args.quiet:
        result = timing_data[alias]
        print(f"\r{alias}: {new_cards} documents, {result['cards_per_s']:.2f} documents/s, bottleneck {result['bottleneck']}", file=sys.stderr)
    return minted, error


def run_serial(source, args, models, command, reductions, *, resume_dir=None, previous=None):
    started = manifest.utc_now()
    args.card_issued_unix = args.card_issued_unix or int(started.timestamp())
    machine = manifest.machine_info(args.device, args.host_label)
    software = manifest.software_info()
    input_hashes = {
        name: sha256_file(Path(path))
        for name in ("schema", "content_policy") if (path := getattr(args, name))
    }
    run_root = args.runs_dir.expanduser().resolve()
    run_dir = resume_dir or run_root / manifest.make_run_id(started, machine["host_label"])
    if not resume_dir:
        run_dir.mkdir(parents=True)
    elif any(previous["software"].get(key) != software.get(key) for key in (
        "reference_sha256", "mintkit_sha256", "numpy", "torch", "sentence-transformers", "transformers", "zstandard",
    )) or previous["machine"].get("device") != machine.get("device"):
        raise ValueError("Mintkit code, runtime, or device changed since the checkpoint was written")
    if isinstance(source, FolderSource):
        run_root = run_dir.parent
        if run_root != source.root and run_root.is_relative_to(source.root):
            source.excluded_dirs.add(run_root)
        else:
            source.excluded_dirs.add(run_dir)
        source.excluded_files.update(run_root / name for name in ("INDEX.tsv", ".index.lock", ".index.pending"))

    config = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()
              if key not in {"subcommand", "resume", "config"}}
    config["split"] = args.split or "none"
    config["model_specs"] = {alias: asdict(spec) if spec else None for alias, spec in models.items()}
    run = previous or {
        "schema": "mintkit-run-1", "run_id": run_dir.name, "started_utc": started.isoformat(),
        "command": command, "cwd": str(Path.cwd()), "machine": machine, "software": software,
        "source": {"spec": source.name, "sampling": args.sample, "seed": args.seed, "split": args.split},
        "config": config, "input_sha256": input_hashes, "outputs": {},
    }
    with exclusive_run(run_dir):
        if previous:
            current = read_run(run_dir, allow_partial=True)
            if current["status"] == "complete" or not (run_dir / ".checkpoints").is_dir():
                raise ValueError("The run has no resumable checkpoint")
            if current.get("input_sha256") != input_hashes:
                raise ValueError("Schema or content policy changed since the checkpoint was written")
            run = current
        run.update(status="running", finished_utc=None)
        run.pop("error", None)
        manifest.write_manifest(run_dir, run)
        timing_data = {}
        text_cache = TextCache(args.text_cache_mb) if len(models) > 1 and args.text_cache_mb else None
        minted = set()
        try:
            selection = select(source, args.sample, split=args.split, seed=args.seed)
            judged_ids = {doc_id for judgments in selection.qrels.values() for doc_id in judgments}
            with (run_dir / "failures.jsonl").open("w", encoding="utf-8") as failures:
                for index, (alias, spec) in enumerate(models.items()):
                    docs, error = _mint_model(
                        run_dir, run, selection, alias, spec, reductions, args, source, failures,
                        index == 0, judged_ids, timing_data, text_cache,
                    )
                    minted.update(docs)
                    failures.flush()
                    manifest.write_manifest(run_dir, run)
                    if error is not None:
                        raise error
            run["source"]["describe"] = source.describe()
            run["source"]["doc_count"] = next(iter(run["outputs"].values()))["documents"]
            if args.record_docs:
                run["source"]["docs_file"] = "docs.tsv"
            run["status"] = "complete"
        except KeyboardInterrupt:
            run["status"] = "partial"
            raise
        except Exception as exc:
            run.update(status="failed", error=str(exc))
            raise RuntimeError(f"{run_dir}: {exc}") from exc
        finally:
            if "selection" in locals():
                run["source"]["queries_dropped"] = _write_retrieval_inputs(run_dir, selection, minted)
            (run_dir / "timing.json").write_text(json.dumps(timing_data, indent=2) + "\n", encoding="utf-8")
            run["finished_utc"] = manifest.utc_now().isoformat()
            manifest.write_manifest(run_dir, run)
            manifest.append_run_index(run_dir, run)
        if not args.keep_checkpoints:
            shutil.rmtree(run_dir / ".checkpoints")
    return run_dir
