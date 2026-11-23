"""Ranking agreement, qrels metrics, and lexical retrieval baselines."""

import math
import re
from collections import Counter, defaultdict

import numpy as np

from .backends import topk


def ir_metrics(rankings, query_ids, qrels, doc_ids):
    available = set(doc_ids)
    values = []
    for ranked, qid in zip(rankings, query_ids, strict=True):
        judged = {doc: grade for doc, grade in qrels.get(qid, {}).items() if grade > 0 and doc in available}
        if not judged:
            continue
        gains = [judged.get(doc_ids[ordinal], 0) if 0 <= ordinal < len(doc_ids) else 0 for ordinal in ranked[:100]]
        ideal = sorted(judged.values(), reverse=True)[:10]
        dcg = sum(gain / math.log2(rank + 2) for rank, gain in enumerate(gains[:10]))
        idcg = sum(gain / math.log2(rank + 2) for rank, gain in enumerate(ideal))
        values.append((
            next((1 / rank for rank, gain in enumerate(gains[:10], 1) if gain), 0),
            dcg / idcg, sum(gain > 0 for gain in gains[:10]) / len(judged),
            sum(gain > 0 for gain in gains) / len(judged),
        ))
    labels = ("MRR@10", "nDCG@10", "R@10", "R@100")
    return dict(zip(labels, map(float, np.mean(values, axis=0)), strict=True)) | {"queries": len(values)} if values else {"queries": 0}


def rescore(queries, matrix, candidates):
    result = np.empty(candidates.shape, dtype=np.float32)
    for index, ids in enumerate(candidates):
        result[index] = np.asarray(matrix[ids], dtype=np.float32) @ queries[index]
    return topk(result, candidates, candidates.shape[1])


def agreement(reference, actual, qids, k, *, exact, raw_reference=None, raw_actual=None):
    ref_scores, ref_ids = reference[0][:, :k], reference[1][:, :k]
    scores, ids = actual[0][:, :k], actual[1][:, :k]
    if exact:
        diffs = []
        max_delta = 0.0
        for row, qid in enumerate(qids):
            unequal = np.flatnonzero(ref_ids[row] != ids[row])
            if len(unequal):
                at = int(unequal[0])
                diffs.append({
                    "qid": qid, "rank": at + 1, "reference_ordinal": int(ref_ids[row, at]),
                    "ordinal": int(ids[row, at]), "reference_score": float(ref_scores[row, at]),
                    "score": float(scores[row, at]),
                })
            ref = dict(zip(raw_reference[1][row], raw_reference[0][row]))
            for ordinal, score in zip(raw_actual[1][row], raw_actual[0][row]):
                if ordinal in ref:
                    max_delta = max(max_delta, abs(float(score) - float(ref[ordinal])))
        return {
            "identical_fraction": 1 - len(diffs) / len(qids), "max_abs_score_delta": max_delta,
            "first_rank": min((row["rank"] for row in diffs), default=None), "disagreements": diffs,
        }

    recalls, correlations = [], []
    for expected, found in zip(ref_ids, ids, strict=True):
        shared = set(expected) & {int(value) for value in found if value >= 0}
        recalls.append(len(shared) / len(expected))
        if len(shared) > 1:
            expected_ranks = {ordinal: rank for rank, ordinal in enumerate(x for x in expected if x in shared)}
            found_ranks = {ordinal: rank for rank, ordinal in enumerate(x for x in found if x in shared)}
            squared = sum((expected_ranks[ordinal] - found_ranks[ordinal]) ** 2 for ordinal in shared)
            n = len(shared)
            correlations.append(1 - 6 * squared / (n * (n * n - 1)))
    return {"recall_at_k": float(np.mean(recalls)), "spearman_shared": float(np.mean(correlations)) if correlations else None}


def lexical_rankings(documents, queries, k):
    tokens = re.compile(r"[^\W_]+", re.UNICODE)
    postings = defaultdict(list)
    lengths = np.empty(len(documents), dtype=np.int64)
    for ordinal, text in enumerate(documents):
        counts = Counter(tokens.findall(text.casefold()))
        lengths[ordinal] = sum(counts.values())
        for term, count in counts.items():
            postings[term].append((ordinal, count))
    n = len(documents)
    avgdl = max(float(lengths.mean()), 1)
    norms = np.zeros(n, dtype=np.float32)
    weighted = {}
    for term, entries in postings.items():
        ids, counts = np.asarray(entries).T
        idf = math.log((1 + n) / (1 + len(entries))) + 1
        weights = (1 + np.log(counts)) * idf
        norms[ids] += weights * weights
        weighted[term] = (ids, weights, idf, counts)
    norms = np.sqrt(norms)
    norms[norms == 0] = 1
    results = {"bm25": [], "tfidf": []}
    for query in queries:
        bm25 = np.zeros(n, dtype=np.float32)
        tfidf = np.zeros(n, dtype=np.float32)
        for term, frequency in Counter(tokens.findall(query.casefold())).items():
            if term not in weighted:
                continue
            ids, weights, idf, counts = weighted[term]
            bm25[ids] += math.log(1 + (n - len(ids) + .5) / (len(ids) + .5)) * (2.2 * counts) / (
                counts + 1.2 * (.25 + .75 * lengths[ids] / avgdl)
            )
            tfidf[ids] += weights * ((1 + math.log(frequency)) * idf)
        for name, scores in (("bm25", bm25), ("tfidf", tfidf / norms)):
            results[name].append(topk(scores[None], np.arange(n), k)[1][0])
    return results
