"""Read documents lazily from a directory, with optional TSV judgments."""

import json
from collections.abc import Iterator
from pathlib import Path

from ._io import read_qrels_tsv, read_queries_tsv, sha256_file
from .base import Doc, Qrels, Query, Source


class FolderSource(Source):
    def __init__(
        self, root: str | Path, *, glob: str = "*", queries_path: Path | None = None,
        qrels_path: Path | None = None, include_hidden: bool = False,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError(f"Folder does not exist: {self.root}")
        self.name = f"folder:{self.root.name or 'root'}"
        self.glob = glob
        self.include_hidden = include_hidden
        self.queries_path = self._optional_file(queries_path, "queries.tsv")
        self.qrels_path = self._optional_file(qrels_path, "qrels.tsv")
        self.excluded_dirs: set[Path] = set()
        self.excluded_files: set[Path] = set()

    def _optional_file(self, override: Path | None, default: str) -> Path | None:
        if override is not None:
            path = Path(override).expanduser().resolve()
            if not path.is_file():
                raise FileNotFoundError(path)
            return path
        path = self.root / default
        return path if path.is_file() else None

    def iter_docs(self) -> Iterator[Doc]:
        pattern = self.glob if "/" in self.glob else f"**/{self.glob}"
        metadata = {self.queries_path, self.qrels_path}
        checked: dict[Path, bool] = {}
        for path in sorted(self.root.glob(pattern)):
            relative = path.relative_to(self.root)
            if not self.include_hidden and any(part.startswith(".") for part in relative.parts):
                continue
            if path in metadata or path in self.excluded_files or not path.is_file():
                continue
            if any(path.is_relative_to(parent) for parent in self.excluded_dirs):
                continue
            if any(self._generated(parent, checked) for parent in path.parents if parent.is_relative_to(self.root) and parent != self.root):
                continue
            yield Doc(relative.as_posix(), path=path)

    @staticmethod
    def _generated(directory: Path, checked: dict[Path, bool]) -> bool:
        if directory not in checked:
            try:
                meta = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
                checked[directory] = isinstance(meta, dict) and meta.get("schema") == "mintkit-run-1"
            except (OSError, ValueError):
                checked[directory] = False
        return checked[directory]

    def splits(self) -> list[str]:
        return ["default"] if self.queries_path or self.qrels_path else []

    def queries(self, split: str) -> list[Query]:
        return read_queries_tsv(self.queries_path) if split == "default" and self.queries_path else []

    def qrels(self, split: str) -> Qrels:
        return read_qrels_tsv(self.qrels_path) if split == "default" and self.qrels_path else {}

    def describe(self) -> dict:
        files = [path for path in (self.queries_path, self.qrels_path) if path is not None]
        return {
            "root": str(self.root),
            "glob": self.glob,
            "include_hidden": self.include_hidden,
            "files": {str(path): sha256_file(path) for path in files},
        }
