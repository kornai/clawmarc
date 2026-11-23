"""Commit complete input windows so resume preserves encoder batch composition."""

import hashlib
import io
import json
import os
from contextlib import contextmanager
from pathlib import Path

import zstandard


@contextmanager
def exclusive_run(run_dir: Path):
    with (run_dir / ".lock").open("a") as stream:
        if os.name == "posix":
            import fcntl

            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError(f"Run is already active: {run_dir}") from exc
        yield


def window_identity(docs) -> str:
    digest = hashlib.sha256()
    for doc in docs:
        if doc.path is None:
            payload = hashlib.sha256(doc.text.encode("utf-8")).hexdigest()
        else:
            try:
                stat = doc.path.stat()
                payload = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            except OSError:
                payload = None
        digest.update((json.dumps([doc.doc_id, doc.title, payload], ensure_ascii=False) + "\n").encode())
    return digest.hexdigest()


class Journal:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.windows = sorted(directory.glob("*.json.zst"))
        if any(path.name != f"{index:012d}.json.zst" for index, path in enumerate(self.windows)):
            raise ValueError(f"Nonconsecutive checkpoints in {directory}")

    @staticmethod
    @contextmanager
    def _open(path):
        with path.open("rb") as raw, io.TextIOWrapper(
            zstandard.ZstdDecompressor().stream_reader(raw, closefd=False), encoding="utf-8",
        ) as stream:
            yield stream

    def identity(self, index):
        with self._open(self.windows[index]) as stream:
            return json.loads(stream.readline())["identity"]

    def commit(self, identity, rows):
        path = self.directory / f"{len(self.windows):012d}.json.zst"
        pending = path.with_suffix(".pending")
        with pending.open("wb") as raw:
            with zstandard.ZstdCompressor().stream_writer(raw, closefd=False) as stream:
                stream.write((json.dumps({"identity": identity}) + "\n").encode())
                for row in rows:
                    stream.write((json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode())
            raw.flush()
            os.fsync(raw.fileno())
        pending.replace(path)
        if os.name == "posix":
            fd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        self.windows.append(path)

    def rows(self):
        for window in self.windows:
            with self._open(window) as stream:
                next(stream)
                for line in stream:
                    yield json.loads(line)
