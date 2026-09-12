#!/usr/bin/env python3
"""Bounded Cranfield/NewReuters comparison for the clawmarc paper.

Primary evaluation: Cranfield's judged queries and qrels.
Secondary stress test: deterministic NewReuters sample with same-topic
retrieval used only as a weak proxy (NewReuters has no standard qrels).
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import tarfile
import time
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sklearn.feature_extraction.text import TfidfVectorizer


MODELS = {
    "bge": ("/Volumes/114/Sandbox/bge-small-en-v1.5", 480),
    "mbert": ("/Volumes/114/Sandbox/bert-base-multilingual-cased", 480),
    "xlmr": ("/Volumes/114/Sandbox/xlm-roberta-base", 480),
    "mpnet": ("/Volumes/114/Sandbox/paraphrase-multilingual-mpnet-base-v2", 126),
}


def cran_members(path: Path) -> dict[str, str]:
    with tarfile.open(path, "r:gz") as tf:
        return {name: tf.extractfile(name).read().decode("latin-1") for name in
                ("cran.all.1400", "cran.qry", "cranqrel")}


def parse_marked(text: str, first_marker: str = ".I") -> list[dict[str, str]]:
    blocks = re.split(r"(?m)^\.I\s+", text)
    out = []
    for block in blocks[1:]:
        lines = block.splitlines()
        if not lines:
            continue
        item = {"id": lines[0].strip()}
        current = None
        parts: list[str] = []
        for line in lines[1:]:
            if line in {".T", ".A", ".B", ".W"}:
                if current is not None:
                    item[current] = " ".join(parts).strip()
                current = {".T": "title", ".A": "author", ".B": "bib", ".W": "text"}[line]
                parts = []
            elif current is not None:
                parts.append(line.strip())
        if current is not None:
            item[current] = " ".join(parts).strip()
        out.append(item)
    return out


def parse_cran(path: Path):
    members = cran_members(path)
    docs = parse_marked(members["cran.all.1400"])
    # cran.qry uses legacy document-like identifiers with gaps, while
    # cranqrel numbers the 225 queries consecutively.  Qrel order is the
    # canonical mapping, so expose queries by ordinal position.
    query_rows = parse_marked(members["cran.qry"])
    queries = {str(i + 1).zfill(3): x.get("text", "")
               for i, x in enumerate(query_rows)}
    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    for line in members["cranqrel"].splitlines():
        f = line.split()
        if len(f) >= 3:
            qrels[f[0].zfill(3)][f[1]] = int(f[2])
    return docs, queries, qrels


def parse_newreuters(path: Path, limit: int, seed: int, zip_limit: int = 0):
    rng = random.Random(seed)
    reservoir: list[dict] = []
    seen = 0
    zpaths = sorted(path.glob("*.zip"))
    if zip_limit:
        zpaths = zpaths[:zip_limit]
    for zpath in zpaths:
        with zipfile.ZipFile(zpath) as zf:
            for name in sorted(zf.namelist()):
                if not name.lower().endswith(".xml"):
                    continue
                try:
                    root = ET.fromstring(zf.read(name))
                except ET.ParseError:
                    continue
                title = (root.findtext("title") or root.findtext("headline") or "").strip()
                body = " ".join(x.text.strip() for x in root.findall(".//text//p") if x.text).strip()
                if not body:
                    body = " ".join(x.strip() for x in root.itertext() if x and x.strip()).strip()
                codes = set()
                for node in root.findall(".//codes"):
                    if "topic" in (node.attrib.get("class", "").lower()):
                        codes.update(c.attrib.get("code", "") for c in node.findall(".//code"))
                if not title or not body or not codes:
                    continue
                item = {"id": root.attrib.get("itemid", name), "title": title,
                        "text": title + " " + body, "topics": sorted(c for c in codes if c)}
                seen += 1
                if len(reservoir) < limit:
                    reservoir.append(item)
                else:
                    j = rng.randrange(seen)
                    if j < limit:
                        reservoir[j] = item
    return sorted(reservoir, key=lambda x: x["id"])


def bm25_matrix(docs: list[str], queries: list[str], k1: float = 1.2, b: float = .75):
    tok = lambda s: re.findall(r"[a-z0-9]+", s.lower())
    dterms = [tok(x) for x in docs]
    qterms = [tok(x) for x in queries]
    vocab = {w for terms in dterms for w in set(terms)}
    df = Counter(w for terms in dterms for w in set(terms))
    avgdl = sum(map(len, dterms)) / max(1, len(dterms))
    scores = np.zeros((len(queries), len(docs)), dtype=np.float32)
    for qi, terms in enumerate(qterms):
        qtf = Counter(terms)
        for di, dt in enumerate(dterms):
            dl = len(dt)
            tf = Counter(dt)
            score = 0.0
            for w in qtf:
                if w not in vocab or not tf[w]:
                    continue
                idf = math.log(1 + (len(docs) - df[w] + .5) / (df[w] + .5))
                score += idf * (tf[w] * (k1 + 1)) / (tf[w] + k1 * (1 - b + b * dl / avgdl))
            scores[qi, di] = score
    return scores


def embed_model(model_path: str, texts: list[str], chunk_limit: int, label: str = "model"):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_path)
    tokenizer = model.tokenizer
    original = getattr(tokenizer, "model_max_length", 512)
    body = min(chunk_limit, (getattr(model, "max_seq_length", None) or 512) - 2)

    chunks_all: list[str] = []
    weights_all: list[np.ndarray] = []
    spans: list[tuple[int, int]] = []
    for text in texts:
        tokenizer.model_max_length = max(original, 1_000_000)
        ids = tokenizer.encode(text, add_special_tokens=False)
        tokenizer.model_max_length = original
        chunks = [ids[i:i + body] for i in range(0, len(ids), body)] or [[]]
        strings = [tokenizer.decode(c, skip_special_tokens=True,
                                    clean_up_tokenization_spaces=False) for c in chunks]
        start = len(chunks_all)
        chunks_all.extend(strings)
        weights_all.append(np.asarray([max(1, len(c)) for c in chunks], dtype=np.float32))
        spans.append((start, len(chunks_all)))
    encoded = []
    batch_size = 32
    for start in range(0, len(chunks_all), batch_size):
        end = min(start + batch_size, len(chunks_all))
        encoded.append(model.encode(chunks_all[start:end], batch_size=batch_size,
                                    normalize_embeddings=True, convert_to_numpy=True,
                                    show_progress_bar=False))
        print(f"[{label}] chunks {end}/{len(chunks_all)}", flush=True)
    cv = np.concatenate(encoded, axis=0)
    vectors = []
    for (start, end), weights in zip(spans, weights_all):
        v = np.average(cv[start:end], axis=0, weights=weights)
        vectors.append((v / np.linalg.norm(v)).astype(np.float32))
    return np.stack(vectors)


def rankings(scores: np.ndarray):
    return np.argsort(-scores, axis=1)


def cran_metrics(scores: np.ndarray, qids: list[str], qrels: dict[str, dict[str, int]], doc_ids: list[str]):
    order = rankings(scores)
    aps, ndcg10, p10, r100 = [], [], [], []
    for qi, qid in enumerate(qids):
        rel = {d for d, v in qrels.get(qid, {}).items() if v > 0}
        graded = qrels.get(qid, {})
        if not rel:
            continue
        ranked = [doc_ids[i] for i in order[qi]]
        hits = [d in rel for d in ranked]
        seen = 0; precs = []
        for rank, hit in enumerate(hits, 1):
            if hit:
                seen += 1; precs.append(seen / rank)
        aps.append(sum(precs) / len(rel))
        gains = [max(0, graded.get(d, 0)) for d in ranked[:10]]
        dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
        ideal = sorted((max(0, v) for v in graded.values()), reverse=True)[:10]
        idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal)) or 1
        ndcg10.append(dcg / idcg)
        p10.append(sum(hits[:10]) / 10)
        r100.append(sum(hits[:100]) / len(rel))
    return {"MAP": float(np.mean(aps)), "nDCG@10": float(np.mean(ndcg10)),
            "P@10": float(np.mean(p10)), "Recall@100": float(np.mean(r100)),
            "queries": len(aps)}


def proxy_metrics(scores: np.ndarray, queries: list[dict], docs: list[dict]):
    order = rankings(scores); aps, p10 = [], []
    for qi, q in enumerate(queries):
        rel = set(q["topics"])
        relevant = {i for i, d in enumerate(docs)
                    if rel.intersection(d["topics"]) and d["id"] != q["id"]}
        ranked = [i for i in order[qi] if docs[i]["id"] != q["id"]]
        if not relevant: continue
        hits = [i in relevant for i in ranked]
        prec = []; seen = 0
        for rank, hit in enumerate(hits, 1):
            if hit: seen += 1; prec.append(seen / rank)
        aps.append(sum(prec) / len(relevant)); p10.append(sum(hits[:10]) / 10)
    return {"proxy_MAP": float(np.mean(aps)), "proxy_P@10": float(np.mean(p10)),
            "queries": len(aps), "warning": "same-topic proxy, not human qrels"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cran", default="/Volumes/114/Data/cran.tar.gz")
    ap.add_argument("--reuters", default="/Volumes/114/Data/NewReuters")
    ap.add_argument("--out", default="ir_experiment_results.json")
    ap.add_argument("--reuters-docs", type=int, default=5000)
    ap.add_argument("--reuters-queries", type=int, default=100)
    ap.add_argument("--reuters-zips", type=int, default=0,
                    help="smoke-test limit; 0 scans the complete Reuters directory")
    ap.add_argument("--seed", type=int, default=20260910)
    args = ap.parse_args()
    t0 = time.time()

    cran_docs, cran_queries, qrels = parse_cran(Path(args.cran))
    cran_ids = [d["id"] for d in cran_docs]
    cran_text = [d.get("title", "") + " " + d.get("text", "") for d in cran_docs]
    cran_qids = sorted(qrels, key=int)
    cran_qtext = [cran_queries[q] for q in cran_qids]
    result = {"seed": args.seed, "started_unix": time.time(), "models": {},
              "datasets": {"cranfield": {"documents": len(cran_docs), "queries": len(cran_qids)},
                           "newreuters": {"requested_documents": args.reuters_docs}},
              "design": "Cranfield judged evaluation; NewReuters same-topic proxy"}

    bm = bm25_matrix(cran_text, cran_qtext)
    result["models"]["bm25"] = {"cranfield": cran_metrics(bm, cran_qids, qrels, cran_ids)}
    tf = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=1, sublinear_tf=True)
    dm = tf.fit_transform(cran_text); qm = tf.transform(cran_qtext)
    tfidf = (qm @ dm.T).toarray()
    result["models"]["tfidf"] = {"cranfield": cran_metrics(tfidf, cran_qids, qrels, cran_ids)}

    nr_docs = parse_newreuters(Path(args.reuters), args.reuters_docs, args.seed, args.reuters_zips)
    topic_counts = Counter(t for d in nr_docs for t in d["topics"])
    eligible = [d for d in nr_docs if any(topic_counts[t] >= 3 for t in d["topics"])]
    rng = random.Random(args.seed); nr_queries = rng.sample(eligible, min(args.reuters_queries, len(eligible)))
    nr_text = [d["text"] for d in nr_docs]; nr_qtext = [d["title"] for d in nr_queries]
    result["datasets"]["newreuters"].update({"documents": len(nr_docs), "queries": len(nr_queries),
                                                "topic_count": len(topic_counts)})
    nr_bm = bm25_matrix(nr_text, nr_qtext)
    result["models"]["bm25"]["newreuters"] = proxy_metrics(nr_bm, nr_queries, nr_docs)
    nr_tf = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), sublinear_tf=True)
    nr_dm = nr_tf.fit_transform(nr_text); nr_qm = nr_tf.transform(nr_qtext)
    result["models"]["tfidf"]["newreuters"] = proxy_metrics((nr_qm @ nr_dm.T).toarray(), nr_queries, nr_docs)

    all_sims = {}
    for name, (path, chunk) in MODELS.items():
        started = time.time()
        cdoc = embed_model(path, cran_text, chunk)
        cq = embed_model(path, cran_qtext, chunk)
        ns = cq @ cdoc.T
        ndoc = embed_model(path, nr_text, chunk)
        nq = embed_model(path, nr_qtext, chunk)
        ns_nr = nq @ ndoc.T
        all_sims[name] = cdoc @ cdoc.T
        result["models"][name] = {"cranfield": cran_metrics(ns, cran_qids, qrels, cran_ids),
                                  "newreuters": proxy_metrics(ns_nr, nr_queries, nr_docs),
                                  "dimensions": int(cdoc.shape[1]), "seconds": round(time.time() - started, 1)}
        # Storage test: float16 card payload and cosine rankings.
        qdoc = cdoc.astype(np.float16).astype(np.float32)
        qdoc /= np.linalg.norm(qdoc, axis=1, keepdims=True)
        qsim = cq.astype(np.float16).astype(np.float32)
        qsim /= np.linalg.norm(qsim, axis=1, keepdims=True)
        result["models"][name]["float16_query_rank_agreement"] = float(
            np.mean(np.argmax(ns, axis=1) == np.argmax(qsim @ qdoc.T, axis=1)))

    names = list(all_sims)
    result["cross_model"] = {}
    iu = np.triu_indices(len(cran_docs), k=1)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            result["cross_model"][f"{a}-vs-{b}"] = {
                "document_pair_spearman": float(spearmanr(all_sims[a][iu], all_sims[b][iu]).statistic),
                "nearest_neighbor_agreement": float(np.mean(np.argmax(all_sims[a] - np.eye(len(cran_docs))*2, axis=1) ==
                                                              np.argmax(all_sims[b] - np.eye(len(cran_docs))*2, axis=1))) }
    result["finished_unix"] = time.time(); result["elapsed_seconds"] = time.time() - t0
    Path(args.out).write_text(json.dumps(result, indent=2))
    print(json.dumps({"out": args.out, "elapsed_seconds": result["elapsed_seconds"],
                      "datasets": result["datasets"], "models": result["models"],
                      "cross_model": result["cross_model"]}, indent=2))


if __name__ == "__main__":
    main()
