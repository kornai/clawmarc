"""File readers used by multiple source adapters."""

import csv
import gzip
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

from .base import Qrels, Query


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def jsonl_rows(path: Path) -> Iterator[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("expected a JSON object")
            except ValueError as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc
            yield row


def read_queries_tsv(path: Path) -> list[Query]:
    queries = []
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.reader(stream, delimiter="\t"):
            if not row:
                continue
            if not queries and tuple(row) in {("qid", "text"), ("query_id", "text"), ("qid", "query"), ("query_id", "query")}:
                continue
            if len(row) != 2 or not row[0]:
                raise ValueError(f"{path}: expected query ID and text in two columns")
            queries.append(Query(*row))
    return queries


def read_qrels_tsv(path: Path) -> Qrels:
    qrels: Qrels = {}
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.reader(stream, delimiter="\t"):
            if not row:
                continue
            if not qrels and row[0] in {"query-id", "query_id", "qid"} and row[-1] in {"score", "relevance"}:
                continue
            try:
                qid, doc_id, grade = row if len(row) != 4 else (row[0], row[2], row[3])
                if not qid or not doc_id:
                    raise ValueError("empty ID")
                qrels.setdefault(qid, {})[doc_id] = int(grade)
            except ValueError as exc:
                raise ValueError(f"{path}: expected query ID, document ID, and integer relevance") from exc
    return qrels
