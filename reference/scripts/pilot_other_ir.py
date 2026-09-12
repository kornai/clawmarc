#!/usr/bin/env python3
"""Pilot: mint clawmarc cards for a random sample of PDFs and run offline IR
over the cards alone (no index, no artefact access).

Successor to Gemini's test_mint_and_ir.py (2026-09-07), which ran before
libangel_catalog.py had a PDF branch and therefore embedded the placeholder
string "Generic artefact: <name>; MIME application/pdf; <n> bytes" instead of
the document text. This version records what was actually embedded.

Usage: pilot_other_ir.py [--n 20] [--seed 20260907] [--root ~/Other/Paper/Pdf]
                         [--out /tmp/pilot_cards] [--report report.md]
"""
from __future__ import annotations

import argparse
import json
import random
import struct
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REF = HERE.parent
CATALOG = REF / "libangel_catalog.py"
SCHEMA = REF / "clawmarc_catalog_card.h"


def read_vector(card: bytes) -> np.ndarray | None:
    split = struct.unpack_from("<H", card, 0x008)[0]
    profile = struct.unpack_from("<H", card, 0x304)[0]
    # profile 1 = bge-small 384-dim, profiles 2 (mBERT) and 3 (mpnet) 768-dim; f16le = 2 bytes/dim
    if profile not in (1, 2, 3) or split not in (768, 1536):
        return None
    return np.frombuffer(card[0x4C0:0x4C0 + split], dtype="<f2").astype(np.float32)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20260907)
    ap.add_argument("--root", default=str(Path.home() / "Other/Paper/Pdf"))
    ap.add_argument("--out", default="/tmp/pilot_cards")
    ap.add_argument("--report", default="")
    args = ap.parse_args()

    root = Path(args.root)
    pdfs = sorted(p for p in root.iterdir() if p.suffix.lower() == ".pdf")
    rng = random.Random(args.seed)
    sample = rng.sample(pdfs, min(args.n, len(pdfs)))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    t_total = time.time()
    for p in sample:
        t0 = time.time()
        subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(p), "/dev/null"],
                       capture_output=True)
        t_extract = time.time() - t0
        card = out / (p.stem + ".cxcc")
        meta = out / (p.stem + ".cxcc.json")
        t1 = time.time()
        r = subprocess.run([sys.executable, str(CATALOG), str(p), "--out-card", str(card),
                            "--out-meta", str(meta), "--schema", str(SCHEMA),
                            "--allow-doc-vector", "--allow-text-prefix"],
                           capture_output=True, text=True)
        t_mint = time.time() - t1
        ok = r.returncode == 0 and card.exists()
        m = json.load(open(meta)) if ok else {}
        seg = m.get("text_segments") or m.get("segments") or {}
        rows.append({
            "file": p.name, "bytes": p.stat().st_size, "ok": ok,
            "t_extract_s": round(t_extract, 2), "t_mint_s": round(t_mint, 2),
            "handler": (m.get("policy") or {}).get("text_extractor") or m.get("handler"),
            "arena_class": (m.get("cxcc") or {}).get("arena_class"),
            "preimage_chars": len(seg.get("embedding_preimage", "") or ""),
            "truncated": (m.get("cxcc") or {}).get("text_truncated"),
            "err": (r.stderr or "")[-300:] if not ok else "",
        })
        print(f"{p.name:40s} extract {t_extract:6.2f}s  mint {t_mint:6.2f}s  {'ok' if ok else 'FAIL'}", flush=True)
    wall = time.time() - t_total

    # Offline IR over the cards alone.
    vecs, names = [], []
    for row in rows:
        if not row["ok"]:
            continue
        card = (out / (Path(row["file"]).stem + ".cxcc")).read_bytes()
        v = read_vector(card)
        if v is not None:
            vecs.append(v / np.linalg.norm(v)); names.append(row["file"])
    ir = []
    if len(vecs) > 2:
        M = np.stack(vecs)
        S = M @ M.T
        for i, n in enumerate(names):
            order = np.argsort(-S[i])
            nn = [(names[j], round(float(S[i, j]), 3)) for j in order if j != i][:3]
            ir.append({"query": n, "top3": nn})
        offdiag = S[~np.eye(len(names), dtype=bool)]
        stats = {"n_vectors": len(names), "pair_cosine_mean": round(float(offdiag.mean()), 3),
                 "pair_cosine_min": round(float(offdiag.min()), 3), "pair_cosine_max": round(float(offdiag.max()), 3)}
    else:
        stats = {"n_vectors": len(names)}

    # Keyword search over the human text region of the cards alone.
    kw = "grammar"
    hits = []
    for row in rows:
        if not row["ok"]:
            continue
        card = (out / (Path(row["file"]).stem + ".cxcc")).read_bytes()
        split = struct.unpack_from("<H", card, 0x008)[0]
        text = card[0x4C0 + split:0xFC0].rstrip(b"\0").decode("utf-8", "replace")
        if kw in text.lower():
            hits.append(row["file"])

    ok_rows = [r for r in rows if r["ok"]]
    summary = {
        "seed": args.seed, "root": str(root), "n_pdfs_in_root": len(pdfs), "sampled": len(sample),
        "minted": len(ok_rows), "wall_s": round(wall, 1),
        "mean_extract_s": round(float(np.mean([r["t_extract_s"] for r in ok_rows])), 2) if ok_rows else None,
        "mean_mint_s": round(float(np.mean([r["t_mint_s"] for r in ok_rows])), 2) if ok_rows else None,
        "mean_preimage_chars": int(np.mean([r["preimage_chars"] for r in ok_rows])) if ok_rows else None,
        "ir": stats, "keyword": kw, "keyword_hits": hits,
    }
    result = {"summary": summary, "rows": rows, "ir": ir}
    print(json.dumps(summary, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
