"""Evaluate vector retrieval on real and optionally scaled collections."""

import csv
import hashlib
import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

import numpy as np

from . import _ref
from .benchmark import append_rows
from .models import ModelSpec, resolve_models
from .operations import read_run, variants
from .reductions import normalize
from .retrieve.backends import make_backends
from .retrieve.matrix import CardMatrix, advisory_evict, card_rows, export_variant, write_strided
from .retrieve.metrics import agreement, ir_metrics, lexical_rankings, rescore
from .sources._io import read_qrels_tsv

RESULT_FIELDS = (
    "schema", "run_id", "host", "cpu", "gpus", "model", "reduction", "dim", "backend", "params",
    "size", "synthetic", "k", "index_seconds", "load_seconds", "query_qps", "p50_ms", "p99_ms",
    "MRR@10", "nDCG@10", "R@10", "R@100", "reference_agreement",
)


def _ids(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return [row["doc_id"] for row in csv.DictReader(stream, delimiter="\t")]


def _collections(run_dir, model, label, root, output):
    full = run_dir / "vectors" / model / label
    matrix_path = full / "docs.f32.npy"
    export = run_dir / "export" / model / label
    packed = None
    if output["layout"] != "vectors":
        packed = export_variant(root, output, export)
    if matrix_path.is_file():
        matrix = np.load(matrix_path, mmap_mode="r", allow_pickle=False)
        ids = _ids(full / "docs.ids.tsv")
    else:
        matrix, ids = packed, _ids(export / "docs.ordinal.tsv")
    if matrix is None or len(matrix) != len(ids) or not len(ids):
        raise ValueError(f"No usable vectors for {model}/{label}")
    if packed is not None and (len(packed) != len(matrix) or _ids(export / "docs.ordinal.tsv") != ids):
        raise ValueError(f"Card and full-width vector ordinals differ for {model}/{label}")
    return matrix, ids, packed


def _queries(run_dir, alias, config, queries, args):
    model_config = config.get("model_specs", {}).get(alias)
    spec = ModelSpec(**model_config) if model_config else resolve_models(
        [alias], allow_remote_code=False, revision=None,
    )[alias]
    revision = config.get("model_revision")
    identity = json.dumps([asdict(spec), revision, args.query_device, queries], sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(identity.encode()).hexdigest()
    directory = run_dir / "queries"
    directory.mkdir(exist_ok=True)
    path = directory / f"{alias}.f32.npy"
    metadata = directory / f"{alias}.json"
    started = perf_counter()
    if metadata.is_file() and path.is_file() and metadata.read_text(encoding="utf-8").strip() == digest:
        vectors = np.load(path, allow_pickle=False)
        if vectors.shape == (len(queries), spec.dim):
            return vectors, perf_counter() - started, True
    if spec.task_adapter and not args.allow_remote_code:
        raise ValueError("Pass --allow-remote-code to evaluate a jina-v3 run")
    model = spec.load(args.query_device, query=True, revision=revision)
    vectors = model.encode(
        [spec.query_prefix + query["text"] for query in queries], normalize_embeddings=True,
        convert_to_numpy=True, show_progress_bar=False,
    ).astype("<f4")
    if vectors.shape != (len(queries), spec.dim) or not np.isfinite(vectors).all():
        raise ValueError(f"Invalid query vectors for {alias}")
    np.save(path, vectors, allow_pickle=False)
    metadata.write_text(digest + "\n", encoding="utf-8")
    return vectors, perf_counter() - started, False


def _quantize(work, matrix, dimension, count, *, packed):
    if count == len(matrix) and packed is not None:
        return packed
    output = np.lib.format.open_memmap(work / "docs.f16.npy", mode="w+", dtype="<f2", shape=(count, dimension))
    rng = np.random.default_rng(20260910)
    for start in range(0, len(matrix), 8192):
        end = min(len(matrix), start + 8192)
        output[start:end] = packed[start:end] if packed is not None else normalize(np.asarray(matrix[start:end, :dimension], dtype=np.float32))
    for start in range(len(matrix), count, 8192):
        end = min(count, start + 8192)
        ids = np.arange(start, end) % len(matrix)
        source = np.asarray(matrix[ids, :dimension], dtype=np.float32)
        source += rng.standard_normal(source.shape, dtype=np.float32) * np.float32(0.001)
        output[start:end] = normalize(source)
    output.flush()
    return output


def _batches(backend, queries, k):
    pairs = [backend.search(queries[start:start + 32], k) for start in range(0, len(queries), 32)]
    return tuple(np.concatenate([pair[index] for pair in pairs]) for index in (0, 1))


def _latency(backend, queries, width):
    times = []
    for query in queries:
        started = perf_counter()
        backend.search(query[None], width)
        times.append((perf_counter() - started) * 1000)
    return {"p50_ms": float(np.percentile(times, 50)), "p99_ms": float(np.percentile(times, 99))}


def _evaluate_scale(work, root, output, packed, matrix, ids, queries, qids, qrels, dim, count, args):
    synthetic = count > len(ids)
    native = packed if packed is not None and packed.shape[1] == dim else None
    build_started = perf_counter()
    working = _quantize(work, matrix, dim, count, packed=native)
    n = len(working)
    original = not synthetic and native is not None and output["layout"] == "shards"
    if original:
        mmap_matrix = CardMatrix(root, output, dim)
        paths = mmap_matrix.paths
    else:
        path = work / "vectors.strided"
        mmap_matrix = write_strided(path, working)
        paths = [path]
    matrix_build_s = perf_counter() - build_started
    requested_k = sorted(set(args.k))
    width = min(n, max(100, *requested_k) + 16)
    records, reference_raw, reference = [], None, None
    for backend in make_backends(args.backends, args.device, args.dtype, args.block_size, args.nprobe, args.ef_search):
        cold_hint = advisory_evict(paths) if backend.name == "mmap" else False
        cold_start = perf_counter()
        stats = backend.build(mmap_matrix if backend.name == "mmap" else working)
        backend.search(queries[:1], width)
        cold_s = perf_counter() - cold_start if cold_hint else None
        warm_start = perf_counter()
        backend.search(queries[:1], width)
        warm_s = perf_counter() - warm_start
        started = perf_counter()
        raw = _batches(backend, queries, width)
        seconds = perf_counter() - started
        ranked = rescore(queries, working, raw[1]) if backend.exact else raw
        if reference is None:
            reference_raw, reference = raw, ranked
        metrics = ir_metrics(ranked[1], qids, qrels, ids)
        latency_indices = np.linspace(0, len(queries) - 1, num=min(len(queries), args.latency_queries), dtype=int)
        latency = _latency(backend, queries[latency_indices], min(n, max(requested_k)))
        for k in requested_k:
            records.append({
                "backend": backend.name, "params": backend.params(), "size": n, "synthetic": synthetic,
                "k": k, "effective_k": min(n, k), "build": asdict(stats),
                "matrix_build_s": matrix_build_s, "load_seconds": cold_s,
                "warm_first_query_s": warm_s, "cold_first_query_s": cold_s,
                "cold_method": "posix_fadvise" if cold_hint else None,
                "query_qps": len(queries) / max(seconds, 1e-9), "latency_queries": len(latency_indices),
                **latency, "metrics": metrics,
                "agreement": agreement(
                    reference, ranked, qids, min(n, k), exact=backend.exact,
                    raw_reference=reference_raw, raw_actual=raw,
                ),
            })
    return records


def _collapse(matrix):
    rng = np.random.default_rng(20260910)
    rows = rng.choice(len(matrix), size=min(256, len(matrix)), replace=False)
    vectors = normalize(np.asarray(matrix[rows], dtype=np.float32))
    values = (vectors @ vectors.T)[np.triu_indices(len(vectors), 1)]
    return {"mean": float(values.mean()), "stddev": float(values.std())} if len(values) else None


def _run_to_run(other, alias, label, ids, matrix):
    if other is None:
        return None
    root = other / "vectors" / alias / label
    peer = np.load(root / "docs.f32.npy", mmap_mode="r", allow_pickle=False)
    if peer.shape[1] != matrix.shape[1]:
        raise ValueError(f"Run comparison dimension mismatch for {alias}/{label}")
    positions = {doc_id: i for i, doc_id in enumerate(_ids(root / "docs.ids.tsv"))}
    matched = [(i, positions[doc_id]) for i, doc_id in enumerate(ids) if doc_id in positions]
    total, minimum, identical = 0.0, 1.0, 0
    for start in range(0, len(matched), 8192):
        left, right = np.asarray(matched[start:start + 8192]).T
        left_vectors, right_vectors = np.asarray(matrix[left], dtype=np.float32), np.asarray(peer[right], dtype=np.float32)
        score = np.sum(normalize(left_vectors) * normalize(right_vectors), axis=1)
        identical += int(np.count_nonzero(np.all(
            left_vectors.astype("<f2").view("<u2") == right_vectors.astype("<f2").view("<u2"), axis=1,
        )))
        total += float(score.sum(dtype=np.float64))
        minimum = min(minimum, float(score.min()))
    if not matched:
        return {"matched": 0}
    return {
        "matched": len(matched), "mean": total / len(matched), "min": minimum,
        "f16_bit_identical_fraction": identical / len(matched),
    }


def _lexical(run_dir, alias, root, output, ids, queries, qids, qrels, args):
    if not args.lexical:
        return {}
    text_by_field = {}
    if output["layout"] != "vectors":
        text_by_field["card"] = {
            row["doc_id"]: _ref.unpack_basic(card)["body_prefix"] for row, card in card_rows(root, output)
        }
    full = run_dir / "text" / f"{alias}.jsonl"
    if full.is_file():
        with full.open(encoding="utf-8") as stream:
            text_by_field["full"] = {doc["doc_id"]: doc["text"] for doc in map(json.loads, stream)}
    results = {} if full.is_file() else {"full": {"status": "not recorded"}}
    for field, docs in text_by_field.items():
        if any(doc_id not in docs for doc_id in ids):
            results[field] = {"status": "incomplete text coverage"}
            continue
        rankings = lexical_rankings([docs[doc_id] for doc_id in ids], [query["text"] for query in queries], min(len(ids), 100))
        results[field] = {name: ir_metrics(ranks, qids, qrels, ids) for name, ranks in rankings.items()}
    return results


def evaluate(args):
    from .checkpoint import exclusive_run

    with exclusive_run(args.run_dir):
        return _evaluate(args)


def _evaluate(args):
    run_dir = args.run_dir
    run = read_run(run_dir)
    source = run_dir / "queries.jsonl"
    if not source.is_file():
        raise ValueError("Run has no sampled evaluation queries")
    queries = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    if not queries:
        raise ValueError("Run has no queries with a relevant document in the sample")
    qids = [query["qid"] for query in queries]
    qrels = read_qrels_tsv(run_dir / "qrels.tsv")
    rows = []
    for alias, label, root, output in variants(run_dir, run, model=args.model, reduction=args.reduction):
        if not output.get("model") or output.get("vectors", output["cards"]) == 0:
            continue
        matrix, ids, packed = _collections(run_dir, alias, label, root, output)
        if args.scale_to is not None and args.scale_to < len(ids):
            raise ValueError("--scale-to must be at least the size of the real collection")
        queries_f32, query_s, cached = _queries(run_dir, alias, run["config"], queries, args)
        dims = sorted(set(args.dims or [output.get("card_dim") or matrix.shape[1]]), reverse=True)
        unavailable = [dim for dim in dims if dim > matrix.shape[1] or dim * 2 > _ref.ARENA_BYTES]
        if args.model and unavailable:
            raise ValueError(f"Unsupported dimensions for {alias}: {unavailable}")
        records = []
        for dim in (dim for dim in dims if dim not in unavailable):
            q = normalize(queries_f32[:, :dim])
            for size in sorted({len(ids), args.scale_to or len(ids)}):
                with tempfile.TemporaryDirectory(prefix=".eval-", dir=run_dir) as directory:
                    records.extend({"dim": dim, **item} for item in _evaluate_scale(
                        Path(directory), root, output, packed, matrix, ids, q, qids, qrels, dim, size, args,
                    ))
        details = {
            "query_encoding_s": query_s, "query_cache_hit": cached, "collapse": _collapse(matrix),
            "run_to_run": _run_to_run(args.compare_run, alias, label, ids, matrix),
            "lexical": _lexical(run_dir, alias, root, output, ids, queries, qids, qrels, args),
            "unavailable_dimensions": unavailable, "results": records,
        }
        results = run_dir / "eval" / alias / label
        results.mkdir(parents=True, exist_ok=True)
        pending = results / "results.json.tmp"
        pending.write_text(json.dumps(details, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        pending.replace(results / "results.json")
        machine = run["machine"]
        for item in records:
            rows.append({
                "schema": "mintkit-retrieval-1", "run_id": run["run_id"], "host": machine["host_label"],
                "cpu": machine["cpu"], "gpus": json.dumps(machine.get("gpus", [])), "model": alias, "reduction": label,
                **{key: item[key] for key in ("dim", "backend", "size", "synthetic", "k", "load_seconds", "query_qps", "p50_ms", "p99_ms")},
                "params": json.dumps(item["params"], sort_keys=True), "index_seconds": item["build"]["seconds"],
                **{key: value for key, value in item["metrics"].items() if key in RESULT_FIELDS},
                "reference_agreement": item["agreement"].get("identical_fraction", item["agreement"].get("recall_at_k")),
            })
    if not rows:
        raise ValueError("No vector output matched the evaluation")
    append_rows(args.output, RESULT_FIELDS, rows)
    return len(rows)
