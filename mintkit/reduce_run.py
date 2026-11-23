"""Mint additional independent reductions from persisted chunk vectors."""

import json
import shutil
import tempfile
from argparse import Namespace
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from . import _ref, manifest
from .artifacts import OutputWriter
from .checkpoint import exclusive_run
from .models import ModelSpec
from .operations import read_run
from .produce import Producer, encode_result, restore_template
from .sources._io import sha256_file
from .timing import Timing


def reduce_run(run_dir, reductions, model=None):
    if any(reduction.name == "ctxprefix" for reduction in reductions):
        raise ValueError("ctxprefix changes encoder inputs; use mint to create its chunk cache")
    with exclusive_run(run_dir):
        run = read_run(run_dir)
        args = Namespace(**run["config"])
        for name, digest in run.get("input_sha256", {}).items():
            if sha256_file(Path(getattr(args, name))) != digest:
                raise ValueError(f"Run {name} changed since minting")
        matched = False
        for alias, output in run["outputs"].items():
            if model is not None and alias != model:
                continue
            model_config = run["config"].get("model_specs", {}).get(alias)
            if not model_config:
                continue
            if not alias.replace("-", "").replace("_", "").isalnum():
                raise ValueError(f"Invalid model alias {alias!r}")
            directory = run_dir / "chunks" / alias / "independent"
            if not (directory / "documents.jsonl").is_file():
                raise ValueError(f"{alias} has no independent chunk cache; mint with --keep-chunk-vectors")
            missing = [red for red in reductions if red.label not in output["reductions"]]
            if missing:
                _mint_cached(run_dir, alias, ModelSpec(**model_config), args, directory, missing, output)
                manifest.write_manifest(run_dir, run)
                manifest.append_run_index(run_dir, run)
            matched = True
        if not matched:
            raise ValueError("No cached model matched the selection")


def _mint_cached(run_dir, alias, spec, args, directory, reductions, output):
    matrix = np.load(directory / "chunks.f32.npy", mmap_mode="r", allow_pickle=False)
    producer = Producer(args, "", spec, reductions, Timing("cpu"))
    with tempfile.TemporaryDirectory(prefix=".reduce-", dir=run_dir) as temporary:
        work = Path(temporary)
        with ExitStack() as stack:
            writers = {red.label: OutputWriter(stack, work, spec, red, args) for red in reductions}
            source = stack.enter_context((directory / "documents.jsonl").open(encoding="utf-8"))
            for line in source:
                row = json.loads(line)
                prep = restore_template(row["template"])
                for reduction in reductions:
                    if row["count"]:
                        start = row["start"]
                        vectors = matrix[start:start + row["count"]]
                        chunks, position = [], 0
                        for count in row["counts"]:
                            chunks.append(_ref.Chunk("", position, position + count))
                            position += count
                        plan = _ref.ChunkPlan(chunks, row["limit"])
                        vector = reduction.reduce(vectors, row["counts"])
                        item = producer.pack_vector(prep, plan, vector, reduction, preimage_sha=row["template"]["preimage_sha256"])
                    elif spec.profile:
                        card, meta = _ref.pack_and_sign(
                            prep, b"", {"embedding_mode": "none"}, args, signing=producer.signing,
                            include_preimage=args.include_preimage, record_title_source=True,
                        )
                        item = encode_result(card, meta, None)
                    else:
                        continue
                    writers[reduction.label].append(row["doc_id"], item)
        for category in ("cards", "vectors"):
            for reduction in reductions:
                generated = work / category / reduction.label
                if generated.is_dir():
                    target = run_dir / category / alias / reduction.label
                    target.parent.mkdir(parents=True, exist_ok=True)
                    marker = ".reduction-sha256"
                    if target.exists():
                        prior = target / marker
                        if target.is_symlink() or not prior.is_file() or prior.read_text(encoding="utf-8").strip() != reduction.sha256:
                            raise ValueError(f"Existing files do not belong to this reduction: {target}")
                        shutil.rmtree(target)
                    (generated / marker).write_text(reduction.sha256 + "\n", encoding="utf-8")
                    generated.replace(target)
        for label, writer in writers.items():
            description = writer.result()
            output["reductions"][label] = description
            output["cards"] += description["cards"]
