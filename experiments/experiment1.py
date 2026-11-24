#!/usr/bin/env python3
"""Mint clawmarc cards for N random English MLDR documents and time it.

Documents are drawn (seeded) from the distinct positive documents of a locally
downloaded MLDR split (data/mldr/mldr-v1.0-en/<split>.jsonl.gz). Each document
is written as a .txt artefact and catalogued with the reference producer
(reference/libangel_catalog.build_card), once per embedding profile model.

By default each model is loaded once and reused for every card ("warm"), so
the per-card time is extraction + embedding + pack/sign/verify. With --cold
the model is reloaded for every card, as when libangel_catalog.py is run once
per file (the 5.9 s/card figure in the paper).

    python experiments/experiment1.py          # 10 docs, all three profiles
    python experiments/experiment1.py --models mbert --cold --device cpu
"""
from __future__ import annotations

import argparse
import gzip
import json
import platform
import random
import statistics
import struct
import sys
import time
from argparse import Namespace
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "reference"))

import libangel_catalog  # noqa: E402
from libangel_card import unpack_basic  # noqa: E402

MODELS = {
    "bge": "BAAI/bge-small-en-v1.5",                                       # profile 1
    "mbert": "bert-base-multilingual-cased",                               # profile 2
    "mpnet": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",  # profile 3
}
PRODUCER_CHUNK_TOKENS = 480  # hard-coded in libangel_mint.document_embedding_f16le
ISSUED_UNIX = 1791936000     # fixed so reruns produce byte-identical cards


def sample_docs(path: Path, n: int, seed: int) -> list[tuple[str, str]]:
    """Seeded sample of distinct positive documents from one MLDR query split."""
    docs: dict[str, str] = {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            for p in json.loads(line)["positive_passages"]:
                docs.setdefault(p["docid"], p["text"])
    ids = random.Random(seed).sample(sorted(docs), n)
    return [(d, docs[d]) for d in ids]


def card_args(artifact: Path, model: str, docid: str) -> Namespace:
    """The arguments libangel_catalog.py's CLI would pass to build_card."""
    return Namespace(
        # libangel_catalog.DEFAULT_SCHEMA resolves to reference/reference/..., so pass the header explicitly
        artifact=str(artifact), schema=str(REPO / "reference/clawmarc_catalog_card.h"),
        issuer_seed=libangel_catalog.DEFAULT_ISSUER_SEED, sequence=1,
        card_issued_unix=ISSUED_UNIX, work_created_unix=None, work_revised_unix=None,
        title=f"MLDR en {docid}", abstract="", keywords="", classification="MLDR en (Wikipedia)",
        # license is an 8-byte field; MLDR en is Wikipedia text
        orcid="", license_id="CC-BY-SA", swarm_reference="", ipfs_cid="", ipns_name="",
        http_hint="", embedding_model=model,
        content_policy=str(REPO / "reference/content_policies/public_library_science.json"),
        policy_name=None, max_text_prefix_chars=None,
        allow_text_prefix=False, no_text_prefix=False, allow_doc_vector=False, no_doc_vector=False,
        allow_image_thumbnail=False, no_image_thumbnail=False, allow_ocr=False, no_ocr=False,
        embed=True,
    )


def install_hooks(device: str | None, cold: bool, timings: dict):
    """Patch the producer so the model is cached (unless cold) and embedding is timed separately."""
    import sentence_transformers

    original_cls = sentence_transformers.SentenceTransformer
    cache: dict[str, object] = {}

    def load(name, *a, **kw):
        if not cold and name in cache:
            return cache[name]
        t = time.perf_counter()
        model = original_cls(name, *a, device=device, **kw)
        timings["load"].append(time.perf_counter() - t)
        cache[name] = model
        return model

    # document_embedding_f16le imports SentenceTransformer at call time, so it picks this up
    sentence_transformers.SentenceTransformer = load

    original_embed = libangel_catalog.document_embedding_f16le

    def timed_embed(text, model_name):
        t = time.perf_counter()
        out = original_embed(text, model_name)
        timings["embed"].append(time.perf_counter() - t)
        return out

    libangel_catalog.document_embedding_f16le = timed_embed
    return load


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=20260910)
    ap.add_argument("--split", default="dev", choices=["dev", "test", "train"])
    ap.add_argument("--models", nargs="+", default=list(MODELS), choices=list(MODELS))
    ap.add_argument("--device", default=None, help="cpu, cuda, ...; default: sentence-transformers' choice")
    ap.add_argument("--cold", action="store_true", help="reload the model for every card")
    ap.add_argument("--out-dir", default=str(HERE / "experiment1"))
    args = ap.parse_args()

    import torch

    out = Path(args.out_dir)
    split_file = REPO / f"data/mldr/mldr-v1.0-en/{args.split}.jsonl.gz"
    t = time.perf_counter()
    docs = sample_docs(split_file, args.n, args.seed)
    sample_s = time.perf_counter() - t
    (out / "docs").mkdir(parents=True, exist_ok=True)
    artefacts = []
    for docid, text in docs:
        path = out / "docs" / f"{docid}.txt"
        path.write_text(text, encoding="utf-8")
        artefacts.append((docid, path))
    print(f"sampled {len(docs)} docs from {split_file.name} in {sample_s:.1f}s: {[d for d, _ in docs]}")

    timings = {"load": [], "embed": []}
    load = install_hooks(args.device, args.cold, timings)
    result = {
        "experiment": "experiment1: mint N random MLDR en documents per embedding profile",
        "split": args.split, "seed": args.seed, "n": len(docs), "docids": [d for d, _ in docs],
        "doc_chars": [len(t) for _, t in docs], "mode": "cold" if args.cold else "warm",
        "runtime": {"python": platform.python_version(), "torch": torch.__version__,
                    "platform": platform.platform(), "cuda": torch.cuda.is_available() and
                    torch.cuda.get_device_name(0), "requested_device": args.device},
        "models": {},
    }

    for alias in args.models:
        name = MODELS[alias]
        timings["load"].clear(); timings["embed"].clear()
        # First load may download the model; keep it out of the per-card figures.
        model = load(name)
        first_load_s = timings["load"].pop()
        if args.cold:
            del model
        else:
            model.encode(["warm-up"])  # first CUDA call pays kernel/context setup
        device = str(getattr(model, "device", args.device)) if not args.cold else args.device

        cards_dir = out / "cards" / alias
        cards_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        for docid, path in artefacts:
            n_load, n_embed = len(timings["load"]), len(timings["embed"])
            t = time.perf_counter()
            card, meta = libangel_catalog.build_card(card_args(path, name, docid))
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            total = time.perf_counter() - t
            (cards_dir / f"{docid}.cxcc").write_bytes(card)
            (cards_dir / f"{docid}.cxcc.json").write_text(
                json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

            # read back: the card must verify and carry a unit-length f16 vector
            info = unpack_basic(card)
            split = info["arena_split"]
            vec = struct.unpack(f"<{split // 2}e", card[0x4C0:0x4C0 + split])
            norm = sum(x * x for x in vec) ** 0.5
            load_s = sum(timings["load"][n_load:])
            embed_s = sum(timings["embed"][n_embed:])
            chunking = meta["policy"]["chunking"]
            rows.append({
                "docid": docid, "card_id": meta["cxcc"]["card_id"],
                "profile": info["embedding_profile_id"], "dim": len(vec), "vector_norm": round(norm, 4),
                "tokens": chunking["token_count"], "chunks": chunking["chunk_count"],
                "total_s": total, "model_load_s": load_s, "embed_s": embed_s - load_s,
                "pack_sign_other_s": total - embed_s,
            })
            print(f"[{alias}] {docid:>14}  {chunking['token_count']:>6} tok  {chunking['chunk_count']:>3} chunks"
                  f"  {total:6.2f}s total  ({rows[-1]['embed_s']:.2f}s embed)", flush=True)

        tokens = sum(r["tokens"] for r in rows)
        embed = sum(r["embed_s"] for r in rows)
        summary = {
            "model": name, "profile": rows[0]["profile"], "dim": rows[0]["dim"], "device": device,
            "first_load_s": round(first_load_s, 2),
            "cards": len(rows), "tokens": tokens, "chunks": sum(r["chunks"] for r in rows),
            "total_s": round(sum(r["total_s"] for r in rows), 3),
            "mean_s_per_card": round(statistics.mean(r["total_s"] for r in rows), 3),
            "median_s_per_card": round(statistics.median(r["total_s"] for r in rows), 3),
            "embed_s": round(embed, 3), "model_load_s": round(sum(r["model_load_s"] for r in rows), 3),
            "pack_sign_other_s": round(sum(r["pack_sign_other_s"] for r in rows), 3),
            "embed_tokens_per_s": round(tokens / embed) if embed else None,
            "per_card": rows,
        }
        if not args.cold:
            max_seq = getattr(model, "max_seq_length", None)
            if max_seq and max_seq < PRODUCER_CHUNK_TOKENS + 2:
                summary["warning"] = (f"producer chunks are {PRODUCER_CHUNK_TOKENS} tokens but the model reads "
                                      f"{max_seq}; each chunk is truncated")
            del model
        result["models"][alias] = summary
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    (out / "experiment1_results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"\n{'model':6} {'prof':>4} {'device':>7} {'load s':>7} {'s/card':>7} {'embed s':>8} "
          f"{'pack s':>7} {'tok/s':>8}")
    for alias, s in result["models"].items():
        print(f"{alias:6} {s['profile']:>4} {s['device'] or '-':>7} {s['first_load_s']:>7.2f} "
              f"{s['mean_s_per_card']:>7.3f} {s['embed_s']:>8.2f} {s['pack_sign_other_s']:>7.2f} "
              f"{s['embed_tokens_per_s'] or 0:>8}")
        if "warning" in s:
            print(f"       warning: {s['warning']}")
    print(f"\nwrote {out / 'experiment1_results.json'} and cards under {out / 'cards'}")


if __name__ == "__main__":
    main()
