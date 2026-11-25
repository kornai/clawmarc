"""Acceptance checks for the mintkit speed-up (Blackboard/CLAUDE_mintkit_speedup_20261124.md).

Mints the same documents with several encoder settings and compares document vectors, sidecar
chunk/token counts, and card bytes:

  fp32 encode  vs fp32 direct   token ids fed directly must match encode (cosine >= 0.99999)
  fp16 encode  vs fp16 direct   same check at fp16
  fp32 direct  vs fp16 direct   fp16 must keep every document at cosine >= 0.9995
  sign-procs 0 vs sign-procs 3  cards must be byte-identical

Usage: python scripts/mintkit_speedup_check.py --runs-dir /tmp/check [--models bge mpnet mbert]
"""

import argparse
import io
import json
import sys
from pathlib import Path

import numpy as np
import zstandard

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mintkit.cli import main  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ["mldr:en", "--mode", "positives", "--split", "dev", "--sample", "random:200", "--mldr-root", str(ROOT / "data" / "mldr")]


def mint(runs, model, *extra):
    argv = ["mint", *SOURCE, "--models", model, "--runs-dir", str(runs), "--issued-unix", "1782071790",
            "--quiet", *extra]
    before = set(runs.glob("2*"))
    main(argv)
    run, = set(runs.glob("2*")) - before
    return run


def load(run, model):
    vectors, = (run / "vectors" / model).glob("*/docs.f32.npy")
    rows = (vectors.parent / "docs.ids.tsv").read_text(encoding="utf-8").splitlines()[1:]
    ids = [row.split("\t")[1] for row in rows]
    metas = []
    for shard in sorted((run / "cards" / model).glob("*/shard-*.meta.jsonl.zst")):
        with zstandard.ZstdDecompressor().stream_reader(shard.open("rb")) as stream:
            metas += [json.loads(line) for line in io.TextIOWrapper(stream, encoding="utf-8")]
    cards = b"".join(path.read_bytes() for path in sorted((run / "cards" / model).glob("*/shard-*.cxcc")))
    timing = json.loads((run / "timing.json").read_text(encoding="utf-8"))[model]
    return {"ids": ids, "vectors": np.load(vectors), "metas": metas, "cards": cards, "timing": timing}


def counts(run):
    return [(m["policy"]["chunking"]["chunk_count"], m["policy"]["chunking"]["token_count"]) for m in run["metas"]]


def compare(a, b):
    assert a["ids"] == b["ids"]
    cosine = np.sum(a["vectors"] * b["vectors"], axis=1) / (
        np.linalg.norm(a["vectors"], axis=1) * np.linalg.norm(b["vectors"], axis=1))
    same_f16 = np.all(a["vectors"].astype(np.float16) == b["vectors"].astype(np.float16), axis=1)
    return {
        "cosine_min": float(cosine.min()), "cosine_mean": float(cosine.mean()),
        "worst_doc": a["ids"][int(cosine.argmin())],
        "f16_card_vectors_identical": f"{int(same_f16.sum())}/{len(same_f16)}",
        "counts_identical": counts(a) == counts(b),
    }


def retokenized_differences(model):
    """Count chunks whose decoded text does not re-tokenize to the planned ids (v0 embedded the re-tokenized text)."""
    from mintkit.cli import _parser, _source_for_mint
    from mintkit.models import MODELS
    from mintkit.produce import Producer
    from mintkit.reductions import parse_reductions
    from mintkit.sources.base import select
    from mintkit.timing import Timing

    parser, _ = _parser()
    args = parser.parse_args(["mint", *SOURCE, "--models", model, "--no-direct-ids"])
    args.device, args.precisions, args.prep_workers, args.torch_threads = "cpu", {model: "fp32"}, 1, 4
    source = _source_for_mint(args)
    producer = Producer(args, source.name, MODELS[model], parse_reductions(["mean_tokw"]), Timing("cpu"))
    producer._load()
    tokenizer = producer.model.tokenizer
    total = differ = 0
    for doc in select(source, args.sample, split=args.split, seed=args.seed).iter_docs():
        plan, ids = producer._plan(producer.prepare(doc), producer.reductions[0])
        for chunk, chunk_ids in zip(plan.chunks, ids, strict=True):
            total += 1
            differ += tokenizer.encode(chunk.text, add_special_tokens=False) != list(chunk_ids)
    return {"chunks": total, "retokenized_differently": differ}


def chunk_level(model, half):
    """Chunk vectors: direct ids vs encode where the ids survive decoding, and each precision vs fp32."""
    import torch

    from mintkit.cli import _parser, _source_for_mint
    from mintkit.models import MODELS
    from mintkit.produce import DirectEncoder, Producer
    from mintkit.reductions import parse_reductions
    from mintkit.sources.base import select
    from mintkit.timing import Timing

    parser, _ = _parser()
    args = parser.parse_args(["mint", *SOURCE, "--models", model, "--no-direct-ids"])
    args.device, args.precisions, args.prep_workers = "cuda", {model: "fp32"}, 1
    source = _source_for_mint(args)
    producer = Producer(args, source.name, MODELS[model], parse_reductions(["mean_tokw"]), Timing("cpu"))
    producer._load()
    tokenizer = producer.model.tokenizer
    texts, ids = [], []
    for doc in select(source, args.sample, split=args.split, seed=args.seed).iter_docs():
        plan, chunk_ids = producer._plan(producer.prepare(doc), producer.reductions[0])
        texts += plan.texts
        ids += [list(item) for item in chunk_ids]
    same = [tokenizer.encode(text, add_special_tokens=False) == item for text, item in zip(texts, ids, strict=True)]
    encoded = producer.model.encode(texts, batch_size=64, normalize_embeddings=True, convert_to_numpy=True)
    direct = {"fp32": DirectEncoder(producer.model, "cuda")(ids, 64)}
    for precision in half:
        producer.model.to(torch.float16 if precision == "fp16" else torch.bfloat16)
        direct[precision] = DirectEncoder(producer.model, "cuda")(ids, 64)
    mask = np.array(same)
    result = {"chunks": len(ids), "ids_survive_decoding": int(mask.sum()),
              "direct_vs_encode_cosine_min_on_those": float(np.sum(encoded[mask] * direct["fp32"][mask], axis=1).min())}
    for precision in half:
        cosine = np.sum(direct["fp32"] * direct[precision], axis=1)
        worst = int(cosine.argmin())
        result[f"{precision}_vs_fp32_chunk_cosine_min"] = float(cosine.min())
        result[f"{precision}_vs_fp32_chunks_below_0.999"] = int((cosine < 0.999).sum())
        result[f"{precision}_worst_chunk_tokens"] = len(ids[worst])
    return result


def main_check():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--models", nargs="+", default=["bge", "mpnet", "mbert"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--chunks-only", action="store_true", help="Only run the chunk-level comparisons")
    options = parser.parse_args()
    if options.chunks_only:
        for model in options.models:
            half = ["fp16", "bf16"] if model == "mbert" else ["fp16"]
            print(json.dumps({model: chunk_level(model, half)}, indent=2), flush=True)
        return
    runs = options.runs_dir.resolve()
    runs.mkdir(parents=True, exist_ok=True)
    report = {}
    for model in options.models:
        half = "bf16" if model == "mbert" else "fp16"
        variants = {
            "fp32-encode": ("--precision", "fp32", "--no-direct-ids"),
            "fp32-direct": ("--precision", "fp32"),
            f"{half}-encode": ("--precision", half, "--no-direct-ids"),
            f"{half}-direct": ("--precision", half),
        }
        if model == "mbert":
            variants["fp16-direct"] = ("--precision", "fp16")
        results = {name: load(mint(runs, model, *extra), model) for name, extra in variants.items()}
        entry = {
            "direct_vs_encode_fp32": compare(results["fp32-encode"], results["fp32-direct"]),
            f"direct_vs_encode_{half}": compare(results[f"{half}-encode"], results[f"{half}-direct"]),
            f"{half}_vs_fp32_direct": compare(results["fp32-direct"], results[f"{half}-direct"]),
            "s_per_doc": {name: run["timing"]["steady_s"] / run["timing"]["cards"] for name, run in results.items()},
            "embed_busy_share": {name: run["timing"]["stages"]["embed"]["busy_s"] / run["timing"]["steady_s"]
                                 for name, run in results.items()},
            "tokenization": retokenized_differences(model),
        }
        if model == "mbert":
            entry["fp16_vs_fp32_direct"] = compare(results["fp32-direct"], results["fp16-direct"])
        if model == options.models[0]:
            signed = load(mint(runs, model, "--precision", "fp32", "--sign-procs", "3"), model)
            entry["sign_procs_cards_identical"] = signed["cards"] == results["fp32-direct"]["cards"]
        report[model] = entry
        print(json.dumps({model: entry}, indent=2), flush=True)
    if options.output:
        options.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main_check()
