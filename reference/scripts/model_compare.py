#!/usr/bin/env python3
"""Compare embedding models on the pilot sample (seed 20260907, 20 PDFs).

Same extraction, chunking (480 body tokens, no special tokens), token-count
weighted mean pooling, and L2 norm for every model; the model is the only
variable. Reports per-model cosine stats and top-3 neighbours, and pairwise
cross-model rank agreement (Spearman over off-diagonal similarities, top-3
overlap).
"""
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

SANDBOX = Path.home() / "Sandbox"
MODELS = {
    "bge": str(SANDBOX / "bge-small-en-v1.5"),
    "mbert": str(SANDBOX / "bert-base-multilingual-cased"),
    "xlmr": str(SANDBOX / "xlm-roberta-base"),
    "mpnet": str(SANDBOX / "paraphrase-multilingual-mpnet-base-v2"),
}

ROOT = Path.home() / "Other/Paper/Pdf"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("model_compare_report.json")


def embed_all(model_path, texts):
    from sentence_transformers import SentenceTransformer
    t0 = time.time()
    model = SentenceTransformer(model_path)
    t_load = time.time() - t0
    tok = model.tokenizer
    orig = getattr(tok, "model_max_length", 512)
    # chunk at the model's own window so nothing is silently truncated
    body = min(480, (getattr(model, "max_seq_length", None) or 512) - 2)
    print(f"chunk size: {body} body tokens", flush=True)
    vecs, tokens_total, t_enc_total = [], 0, 0.0
    for txt in texts:
        tok.model_max_length = max(orig, 1_000_000)
        ids = tok.encode(txt, add_special_tokens=False)
        tok.model_max_length = orig
        chunks = [ids[i:i + body] for i in range(0, len(ids), body)] or [[]]
        chunk_texts = [tok.decode(c, skip_special_tokens=True, clean_up_tokenization_spaces=False) for c in chunks]
        t0 = time.time()
        cv = model.encode(chunk_texts, normalize_embeddings=True, convert_to_numpy=True)
        t_enc_total += time.time() - t0
        w = np.array([max(1, len(c)) for c in chunks], dtype=np.float32)
        v = np.average(cv, axis=0, weights=w)
        v = v / np.linalg.norm(v)
        vecs.append(v.astype(np.float32))
        tokens_total += len(ids)
    return np.stack(vecs), {"load_s": round(t_load, 1), "encode_s": round(t_enc_total, 1),
                            "tokens": tokens_total, "tok_per_s": round(tokens_total / t_enc_total)}


def spearman(a, b):
    ra, rb = np.argsort(np.argsort(a)).astype(float), np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean(); rb -= rb.mean()
    return float((ra @ rb) / np.sqrt((ra @ ra) * (rb @ rb)))


def main():
    pdfs = sorted(p for p in ROOT.iterdir() if p.suffix.lower() == ".pdf")
    sample = random.Random(20260907).sample(pdfs, 20)
    names, texts = [], []
    for p in sample:
        r = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(p), "-"],
                           capture_output=True, text=True, timeout=120)
        txt = re.sub(r"\s+", " ", r.stdout).strip()
        if txt:
            names.append(p.name)
            texts.append(txt)
        print(f"extracted {p.name}: {len(txt)} chars", flush=True)

    report = {"sample": names, "models": {}, "cross": {}}
    sims, tops = {}, {}
    for key, path in MODELS.items():
        print(f"=== embedding with {key} ({path})", flush=True)
        M, stats = embed_all(path, texts)
        S = M @ M.T
        off = S[~np.eye(len(names), dtype=bool)]
        top3 = {}
        for i, n in enumerate(names):
            order = np.argsort(-S[i])
            top3[n] = [(names[j], round(float(S[i, j]), 3)) for j in order if j != i][:3]
        sims[key], tops[key] = S, top3
        # how much of the ranking survives the card's binary16 encoding
        Mq = M.astype(np.float16).astype(np.float32)
        Mq /= np.linalg.norm(Mq, axis=1, keepdims=True)
        Sq = Mq @ Mq.T
        iu_ = np.triu_indices(len(names), k=1)
        f16_rho = spearman(S[iu_], Sq[iu_])
        f16_nn = np.mean([np.argsort(-S[i])[1] == np.argsort(-Sq[i])[1] for i in range(len(names))])
        report["models"][key] = {
            "path": path, **stats,
            "cosine_mean": round(float(off.mean()), 3),
            "cosine_min": round(float(off.min()), 3),
            "cosine_max": round(float(off.max()), 3),
            "f16_spearman_vs_f32": round(f16_rho, 3),
            "f16_nn_agreement": round(float(f16_nn), 2),
            "top3": top3,
        }
        np.savez(OUT.with_suffix(f".{key}.npz"), vectors=M, names=np.array(names))
        print(json.dumps(report["models"][key], indent=2, default=str)[:400], flush=True)

    keys = list(MODELS)
    iu = np.triu_indices(len(names), k=1)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            rho = spearman(sims[a][iu], sims[b][iu])
            overlap = np.mean([len({x for x, _ in tops[a][n][:3]} & {x for x, _ in tops[b][n][:3]}) for n in names])
            nn_agree = np.mean([tops[a][n][0][0] == tops[b][n][0][0] for n in names])
            report["cross"][f"{a}-vs-{b}"] = {
                "spearman_pairwise": round(rho, 3),
                "mean_top3_overlap": round(float(overlap), 2),
                "nearest_neighbour_agreement": round(float(nn_agree), 2),
            }
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps({"cross": report["cross"]}, indent=2), flush=True)
    print(f"report written to {OUT}", flush=True)


if __name__ == "__main__":
    main()
