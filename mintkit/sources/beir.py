"""Load a local dataset in the BEIR JSONL/TSV format."""

from collections.abc import Iterator
from pathlib import Path

from ._io import jsonl_rows, read_qrels_tsv, sha256_file
from .base import Doc, Qrels, Query, Source


class BEIRSource(Source):
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.name = f"beir:{self.root.name or 'root'}"
        self.corpus_path = self.root / "corpus.jsonl"
        self.queries_path = self.root / "queries.jsonl"
        self._qrels: dict[str, Qrels] = {}
        if not self.corpus_path.is_file():
            raise FileNotFoundError(self.corpus_path)

    def iter_docs(self) -> Iterator[Doc]:
        for row in jsonl_rows(self.corpus_path):
            yield Doc(str(row["_id"]), text=row["text"], title=row.get("title"), meta=row.get("metadata") or {})

    def splits(self) -> list[str]:
        if not self.queries_path.is_file():
            return []
        return [path.stem for path in sorted((self.root / "qrels").glob("*.tsv")) if path.is_file()]

    def _qrels_path(self, split: str) -> Path:
        if split not in self.splits():
            raise ValueError(f"Unknown BEIR split {split!r} in {self.root}")
        return self.root / "qrels" / f"{split}.tsv"

    def queries(self, split: str) -> list[Query]:
        # BEIR's query file is shared by all splits.
        query_ids = self.qrels(split).keys()
        return [
            Query(str(row["_id"]), row["text"])
            for row in jsonl_rows(self.queries_path) if str(row["_id"]) in query_ids
        ]

    def qrels(self, split: str) -> Qrels:
        if split not in self._qrels:
            self._qrels[split] = read_qrels_tsv(self._qrels_path(split))
        return self._qrels[split]

    def describe(self) -> dict:
        files = [self.corpus_path]
        if self._qrels:
            files.append(self.queries_path)
            files.extend(self._qrels_path(split) for split in self._qrels)
        return {"root": str(self.root), "files": {str(path): sha256_file(path) for path in files}}
