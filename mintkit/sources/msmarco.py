"""Adapt the ir_datasets MS MARCO passage collection."""

from collections.abc import Iterable, Iterator
from importlib import import_module
from importlib.metadata import version

from .base import Doc, Qrels, Query, Source


class MSMarcoSource(Source):
    DATASET = "msmarco-passage"
    SPLITS = ("train", "dev/small", "trec-dl-2019", "trec-dl-2020")

    def __init__(self, variant: str = "passage") -> None:
        if variant != "passage":
            raise ValueError(f"Unsupported MS MARCO variant {variant!r}; available: passage")
        self.name = f"msmarco:{variant}"

    def _load(self, split: str | None = None):
        if split is not None and split not in self.SPLITS:
            raise ValueError(f"Unknown MS MARCO passage split {split!r}")
        try:
            ir_datasets = import_module("ir_datasets")
        except ModuleNotFoundError as exc:
            raise ValueError("Install the msmarco extra to use MS MARCO") from exc
        return ir_datasets.load(f"{self.DATASET}/{split}" if split else self.DATASET)

    def iter_docs(self) -> Iterator[Doc]:
        for doc in self._load().docs_iter():
            yield Doc(str(doc.doc_id), text=doc.text)

    def get_docs(self, ids: Iterable[str]) -> Iterator[Doc]:
        ids = sorted(set(ids))
        if not ids:
            return
        store = self._load().docs_store()
        for doc_id in ids:
            try:
                doc = store.get(doc_id)
            except KeyError:
                continue
            if doc is not None:
                yield Doc(str(doc.doc_id), text=doc.text)

    def splits(self) -> list[str]:
        return list(self.SPLITS)

    def queries(self, split: str) -> list[Query]:
        return [Query(str(query.query_id), query.text) for query in self._load(split).queries_iter()]

    def qrels(self, split: str) -> Qrels:
        qrels: Qrels = {}
        for judgment in self._load(split).qrels_iter():
            qrels.setdefault(str(judgment.query_id), {})[str(judgment.doc_id)] = judgment.relevance
        return qrels

    def count(self) -> int | None:
        return self._load().docs_count()

    def describe(self) -> dict:
        return {"dataset": self.DATASET, "ir_datasets": version("ir_datasets")}
