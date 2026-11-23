"""Document and judgment contracts shared by all mintkit sources."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path
from random import Random
from typing import Any

DEFAULT_SEED = 20260910
Qrels = dict[str, dict[str, int]]


@dataclass(frozen=True)
class Doc:
    doc_id: str
    text: str | None = None
    path: Path | None = None
    title: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.doc_id:
            raise ValueError("A document must have an ID")
        if (self.text is None) == (self.path is None):
            raise ValueError("A document must have exactly one of text or path")


@dataclass(frozen=True)
class Query:
    qid: str
    text: str


class Source(ABC):
    """A repeatable stream of documents and optional retrieval judgments."""

    name: str
    document_split: str | None = None

    @abstractmethod
    def iter_docs(self) -> Iterator[Doc]:
        ...

    def get_docs(self, ids: Iterable[str]) -> Iterator[Doc]:
        remaining = set(ids)
        if remaining:
            for doc in self.iter_docs():
                if doc.doc_id in remaining:
                    remaining.remove(doc.doc_id)
                    yield doc
                    if not remaining:
                        break

    def splits(self) -> list[str]:
        return []

    def queries(self, split: str) -> list[Query]:
        return []

    def qrels(self, split: str) -> Qrels:
        return {}

    def count(self) -> int | None:
        return None

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class Selection:
    iter_docs: Callable[[], Iterator[Doc]]
    queries: list[Query]
    qrels: Qrels

    def restrict_qrels(self, doc_ids: set[str]) -> Qrels:
        return {
            qid: kept
            for qid, judgments in self.qrels.items()
            if (kept := {doc_id: grade for doc_id, grade in judgments.items() if doc_id in doc_ids})
        }


def reservoir(docs: Iterable[Doc], size: int, rng: Random) -> list[Doc]:
    """Return a uniform sample in source order, using O(size) memory."""
    if size == 0:
        return []
    sampled: list[tuple[int, Doc]] = []
    for position, doc in enumerate(docs):
        if position < size:
            sampled.append((position, doc))
        else:
            slot = rng.randrange(position + 1)
            if slot < size:
                sampled[slot] = (position, doc)
    sampled.sort(key=lambda item: item[0])
    return [doc for _, doc in sampled]


def _nonnegative(raw: str, spec: str) -> int:
    if not raw.isascii() or not raw.isdecimal():
        raise ValueError(f"Expected a nonnegative integer in sample {spec!r}")
    return int(raw)


def _by_ids(source: Source, ids: Iterable[str]) -> Iterator[Doc]:
    missing = set(ids)
    for doc in source.get_docs(sorted(missing)):
        if doc.doc_id in missing:
            missing.remove(doc.doc_id)
            yield doc
    if missing:
        example = ", ".join(sorted(missing)[:5])
        raise ValueError(f"{source.name} is missing {len(missing)} requested document IDs: {example}")


def _qrels_sample(
    source: Source, queries: list[Query], qrels: Qrels, spec: str, raw: str, seed: int,
) -> Selection:
    raw_queries, separator, raw_distractors = raw.partition("+")
    query_count = _nonnegative(raw_queries, spec)
    distractors = _nonnegative(raw_distractors, spec) if separator else 0
    eligible = [query for query in queries if any(grade > 0 for grade in qrels.get(query.qid, {}).values())]
    if query_count > len(eligible):
        raise ValueError(f"{source.name} has only {len(eligible)} queries with positive judgments")
    rng = Random(seed)
    chosen_positions = set(rng.sample(range(len(eligible)), query_count))
    chosen = [query for index, query in enumerate(eligible) if index in chosen_positions]
    chosen_qrels = {query.qid: qrels[query.qid] for query in chosen}
    relevant = {
        doc_id for judgments in chosen_qrels.values() for doc_id, grade in judgments.items()
        if grade > 0
    }

    def iter_docs() -> Iterator[Doc]:
        if not distractors:
            yield from _by_ids(source, relevant)
            return
        positives: dict[str, Doc] = {}

        def candidates() -> Iterator[Doc]:
            for doc in source.iter_docs():
                if doc.doc_id in relevant:
                    positives.setdefault(doc.doc_id, doc)
                else:
                    yield doc

        random_docs = reservoir(candidates(), distractors, Random(seed))
        missing = relevant - positives.keys()
        if missing:
            example = ", ".join(sorted(missing)[:5])
            raise ValueError(f"{source.name} is missing {len(missing)} relevant documents: {example}")
        if len(random_docs) < distractors:
            raise ValueError(f"{source.name} has only {len(random_docs)} available distractors")
        yield from positives.values()
        yield from random_docs

    return Selection(iter_docs, chosen, chosen_qrels)


def select(
    source: Source, sample: str = "all", *, split: str | None = None, seed: int = DEFAULT_SEED,
) -> Selection:
    """Resolve a sample and the queries/judgments associated with it."""
    if split is not None:
        available = source.splits()
        if split not in available:
            raise ValueError(f"Unknown split {split!r} for {source.name}; available: {', '.join(available) or 'none'}")
        if source.document_split is not None and split != source.document_split:
            raise ValueError(f"{source.name} documents are from split {source.document_split!r}, not {split!r}")
    queries = source.queries(split) if split is not None else []
    qrels = source.qrels(split) if split is not None else {}
    if sample == "all":
        return Selection(source.iter_docs, queries, qrels)
    kind, separator, raw = sample.partition(":")
    if not separator:
        raise ValueError(f"Invalid sample {sample!r}; use all, first:N, random:N, qrels:Q[+D], or ids:FILE")
    if kind == "first":
        size = _nonnegative(raw, sample)
        return Selection(lambda: islice(source.iter_docs(), size), queries, qrels)
    if kind == "random":
        size = _nonnegative(raw, sample)
        return Selection(lambda: iter(reservoir(source.iter_docs(), size, Random(seed))), queries, qrels)
    if kind == "ids" and raw:
        ids = [value for line in Path(raw).expanduser().read_text(encoding="utf-8").splitlines() if (value := line.strip())]
        return Selection(lambda: _by_ids(source, ids), queries, qrels)
    if kind == "qrels":
        if split is None:
            raise ValueError("qrels sampling requires a query split")
        return _qrels_sample(source, queries, qrels, sample, raw, seed)
    raise ValueError(f"Unknown sample {sample!r}")
