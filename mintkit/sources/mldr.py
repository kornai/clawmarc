"""Stream MLDR corpus and split files from disk or the Hugging Face Hub."""

import re
from collections.abc import Iterator
from importlib import import_module
from pathlib import Path

from ._io import jsonl_rows, sha256_file
from .base import Doc, Qrels, Query, Source

REPO_ID = "Shitao/MLDR"
SPLITS = ("train", "dev", "test")


class MLDRSource(Source):
    def __init__(
        self, language: str, *, root: str | Path = "data/mldr", split: str = "dev",
        mode: str = "corpus", revision: str | None = None,
    ) -> None:
        if not re.fullmatch(r"[a-z]{2,3}", language):
            raise ValueError(f"Invalid MLDR language code {language!r}")
        if split not in SPLITS:
            raise ValueError(f"Unknown MLDR split {split!r}")
        if mode not in {"corpus", "positives"}:
            raise ValueError(f"Unknown MLDR mode {mode!r}")
        self.name = f"mldr:{language}"
        self.language = language
        self.mode = mode
        self.split = split
        self.document_split = split if mode == "positives" else None
        self.revision = revision
        self.directory = f"mldr-v1.0-{language}"
        self.root = Path(root).expanduser().resolve()
        self._files: dict[str, Path] = {}
        self._judgments: dict[str, tuple[list[Query], Qrels]] = {}

    def _file(self, name: str) -> Path:
        if name in self._files:
            return self._files[name]
        filename = f"{name}.jsonl.gz"
        local_dir = self.root if self.root.name == self.directory else self.root / self.directory
        path = local_dir / filename
        if not path.is_file():
            plain = path.with_suffix("")
            if plain.is_file():
                path = plain
            else:
                try:
                    hub = import_module("huggingface_hub")
                except ModuleNotFoundError as exc:
                    raise ValueError(f"{path} is missing; install the mldr extra to fetch it") from exc
                path = Path(hub.hf_hub_download(
                    repo_id=REPO_ID, repo_type="dataset",
                    filename=f"{self.directory}/{filename}", revision=self.revision,
                ))
                for parent in path.parents:
                    if parent.parent.name == "snapshots":
                        self.revision = parent.name
                        break
        self._files[name] = path
        return path

    def _split_data(self, split: str) -> tuple[list[Query], Qrels]:
        if split not in SPLITS:
            raise ValueError(f"Unknown MLDR split {split!r}")
        if split not in self._judgments:
            queries = []
            qrels: Qrels = {}
            for row in jsonl_rows(self._file(split)):
                qid = str(row["query_id"])
                queries.append(Query(qid, row["query"]))
                qrels[qid] = {str(passage["docid"]): 1 for passage in row["positive_passages"]}
            self._judgments[split] = queries, qrels
        return self._judgments[split]

    def iter_docs(self) -> Iterator[Doc]:
        if self.mode == "corpus":
            for row in jsonl_rows(self._file("corpus")):
                yield Doc(str(row["docid"]), text=row["text"], title=row.get("title"))
            return
        seen: set[str] = set()
        for row in jsonl_rows(self._file(self.split)):
            for passage in row["positive_passages"]:
                doc_id = str(passage["docid"])
                if doc_id not in seen:
                    seen.add(doc_id)
                    yield Doc(doc_id, text=passage["text"], title=passage.get("title"))

    def splits(self) -> list[str]:
        return list(SPLITS)

    def queries(self, split: str) -> list[Query]:
        return self._split_data(split)[0]

    def qrels(self, split: str) -> Qrels:
        return self._split_data(split)[1]

    def describe(self) -> dict:
        return {
            "repo": REPO_ID, "language": self.language, "mode": self.mode,
            "split": self.split, "revision": self.revision,
            "files": {
                str(path): sha256_file(path) for path in self._files.values()
            },
        }
