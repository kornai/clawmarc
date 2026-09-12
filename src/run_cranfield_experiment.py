#!/usr/bin/env python3
"""Cranfield-only clawmarc evaluation with visible progress reporting."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sklearn.feature_extraction.text import TfidfVectorizer

from run_ir_experiments import MODELS, bm25_matrix, cran_metrics, parse_cran, embed_model


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cran", default="/Volumes/114/Data/cran.tar.gz")
    ap.add_argument("--out", default="cranfield_experiment_results.json")
    args = ap.parse_args()
    started = time.time()
    docs, queries, qrels = parse_cran(Path(args.cran))
    doc_ids = [d["id"] for d in docs]
    doc_text = [d.get("title", "") + " " + d.get("text", "") for d in docs]
    qids = sorted(qrels, key=int)
    query_text = [queries[q] for q in qids]
    print(f"Cranfield: {len(docs)} documents, {len(qids)} judged queries", flush=True)

    result = {"started_unix": started, "dataset": {"documents": len(docs), "queries": len(qids)},
              "models": {}, "cross_model": {},
              "design": "BM25 and TF-IDF baselines versus four local embedding models; qrels are graded."}
    print("[bm25] scoring", flush=True)
    result["models"]["bm25"] = cran_metrics(bm25_matrix(doc_text, query_text), qids, qrels, doc_ids)
    print("[tfidf] scoring", flush=True)
    tf = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), sublinear_tf=True)
    dm = tf.fit_transform(doc_text)
    result["models"]["tfidf"] = cran_metrics((tf.transform(query_text) @ dm.T).toarray(), qids, qrels, doc_ids)

    doc_sims = {}
    for name, (path, chunk) in MODELS.items():
        print(f"=== {name}: loading {path}", flush=True)
        t0 = time.time()
        D = embed_model(path, doc_text, chunk, name + " docs")
        Q = embed_model(path, query_text, chunk, name + " queries")
        scores = Q @ D.T
        result["models"][name] = cran_metrics(scores, qids, qrels, doc_ids)
        result["models"][name]["dimensions"] = int(D.shape[1])
        result["models"][name]["seconds"] = round(time.time() - t0, 1)
        D16 = D.astype(np.float16).astype(np.float32)
        D16 /= np.linalg.norm(D16, axis=1, keepdims=True)
        Q16 = Q.astype(np.float16).astype(np.float32)
        Q16 /= np.linalg.norm(Q16, axis=1, keepdims=True)
        result["models"][name]["float16_query_rank_agreement"] = float(
            np.mean(np.argmax(scores, axis=1) == np.argmax(Q16 @ D16.T, axis=1)))
        doc_sims[name] = D @ D.T
        print(f"[{name}] finished in {result['models'][name]['seconds']} s", flush=True)

    names = list(doc_sims)
    iu = np.triu_indices(len(docs), k=1)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            aa = doc_sims[a][iu]; bb = doc_sims[b][iu]
            na = np.argmax(doc_sims[a] - np.eye(len(docs)) * 2, axis=1)
            nb = np.argmax(doc_sims[b] - np.eye(len(docs)) * 2, axis=1)
            result["cross_model"][f"{a}-vs-{b}"] = {
                "document_pair_spearman": float(spearmanr(aa, bb).statistic),
                "nearest_neighbor_agreement": float(np.mean(na == nb)),
            }
    result["finished_unix"] = time.time()
    result["elapsed_seconds"] = result["finished_unix"] - started
    Path(args.out).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
