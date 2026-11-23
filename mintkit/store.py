"""Read and write fixed-stride CXCC shards or individual card files."""

import csv
import hashlib
import io
import json
import mmap
import struct
from contextlib import ExitStack
from itertools import zip_longest
from pathlib import Path

import numpy as np
import zstandard
from cryptography.exceptions import InvalidSignature

from . import _ref
from .sources._io import sha256_file

INDEX_COLUMNS = ("ordinal", "doc_id", "card_id", "object_sha256", "tokens", "chunks")
PROFILE_DIMS = {pid: dim for pid, dim, _ in _ref.EMBEDDING_PROFILES.values()}


def _tsv_writer(stream):
    return csv.writer(stream, delimiter="\t", lineterminator="\n")


def _json_line(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _card_path(directory: Path, ordinal: int) -> Path:
    return directory / f"{ordinal:012d}.cxcc"


class CardWriter:
    """Append cards in input order and publish checksums when closed."""

    def __init__(self, directory: Path, *, layout: str = "shards", shard_size: int = 100_000) -> None:
        if layout not in {"shards", "files"} or shard_size < 1:
            raise ValueError("A card store needs layout shards or files, and a positive shard size")
        self.directory = directory
        self.layout = layout
        self.shard_size = shard_size
        self.count = 0
        self.shards: list[dict] = []
        self.stack = ExitStack()
        self.shard: ExitStack | None = None

    def __enter__(self):
        self.directory.mkdir(parents=True)
        try:
            self.sums = self.stack.enter_context((self.directory / "SHA256SUMS").open("w", encoding="utf-8"))
            if self.layout == "files":
                index_path = self.directory / "index.tsv"
                stream = self.stack.enter_context(index_path.open("w", encoding="utf-8", newline=""))
                self.index = _tsv_writer(stream)
                self.index.writerow(INDEX_COLUMNS)
        except BaseException:
            self.stack.close()
            raise
        return self

    def _open_shard(self) -> None:
        self._close_shard()
        base = f"shard-{len(self.shards):05d}"
        self.cards_path = self.directory / f"{base}.cxcc"
        self.index_path = self.directory / f"{base}.index.tsv"
        self.meta_path = self.directory / f"{base}.meta.jsonl.zst"
        with ExitStack() as stack:
            self.cards = stack.enter_context(self.cards_path.open("wb"))
            index = stack.enter_context(self.index_path.open("w", encoding="utf-8", newline=""))
            self.index = _tsv_writer(index)
            self.index.writerow(INDEX_COLUMNS)
            raw = stack.enter_context(self.meta_path.open("wb"))
            self.meta = stack.enter_context(zstandard.ZstdCompressor().stream_writer(raw, closefd=False))
            self.shard = stack.pop_all()
        self.shard_start = self.count

    def _record_digest(self, path: Path, digest: str) -> None:
        self.sums.write(f"{digest}  {path.name}\n")

    def _close_shard(self) -> None:
        if self.shard is None:
            return
        stack, self.shard = self.shard, None
        stack.close()
        digest = sha256_file(self.cards_path)
        self._record_digest(self.cards_path, digest)
        for path in (self.index_path, self.meta_path):
            self._record_digest(path, sha256_file(path))
        self.shards.append({
            "path": self.cards_path.name, "index": self.index_path.name, "meta": self.meta_path.name,
            "sha256": digest, "cards": self.count - self.shard_start,
        })

    def append(self, doc_id: str, card: bytes, meta: dict) -> None:
        if len(card) != _ref.CARD_BYTES:
            raise ValueError(f"Expected a {_ref.CARD_BYTES}-byte card")
        sidecar = _json_line(meta).encode("utf-8")
        chunking = meta["policy"].get("chunking", {})
        row = (
            self.count, doc_id, meta["cxcc"]["card_id"], meta["artifact"]["sha256"],
            chunking.get("token_count", 0), chunking.get("chunk_count", 0),
        )
        if self.layout == "shards":
            if self.count % self.shard_size == 0:
                self._open_shard()
            self.cards.write(card)
            self.meta.write(sidecar)
        else:
            card_path = _card_path(self.directory, self.count)
            meta_path = card_path.with_suffix(".cxcc.json")
            card_path.write_bytes(card)
            meta_path.write_bytes(sidecar)
            self._record_digest(card_path, row[2])
            self._record_digest(meta_path, hashlib.sha256(sidecar).hexdigest())
        self.index.writerow(row)
        self.count += 1

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            if self.layout == "files":
                self.stack.close()
                if exc_type is None:
                    index = self.directory / "index.tsv"
                    with (self.directory / "SHA256SUMS").open("a", encoding="utf-8") as sums:
                        sums.write(f"{sha256_file(index)}  {index.name}\n")
            elif exc_type is None:
                self._close_shard()
            elif self.shard is not None:
                self.shard.close()
        finally:
            self.stack.close()


class ShardReader:
    """Memory-map a shard and return cards by zero-based local ordinal."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.mapping: mmap.mmap | None = None
        self.opened = False
        self.count = 0

    def __enter__(self):
        with self.path.open("rb") as stream:
            size = stream.seek(0, io.SEEK_END)
            if size % _ref.CARD_BYTES:
                raise ValueError(f"{self.path} is not a whole number of cards")
            self.count = size // _ref.CARD_BYTES
            if size:
                self.mapping = mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ)
        self.opened = True
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.mapping is not None:
            self.mapping.close()
            self.mapping = None
        self.opened = False

    def __len__(self) -> int:
        return self.count

    def card(self, ordinal: int) -> bytes:
        if not self.opened:
            raise ValueError("ShardReader must be open")
        if not 0 <= ordinal < self.count:
            raise IndexError(ordinal)
        assert self.mapping is not None
        start = ordinal * _ref.CARD_BYTES
        return self.mapping[start:start + _ref.CARD_BYTES]

    def vector(self, ordinal: int) -> np.ndarray:
        return np.frombuffer(_vector_bytes(self.card(ordinal)), dtype="<f2")

    def __iter__(self):
        for ordinal in range(self.count):
            yield self.card(ordinal)


def _vector_bytes(card: bytes) -> bytes:
    split = struct.unpack_from("<H", card, 0x008)[0]
    profile = struct.unpack_from("<H", card, 0x304)[0]
    if split > _ref.ARENA_BYTES:
        raise ValueError("Invalid arena split")
    # Profile 0 includes non-vector payloads such as image previews.
    return card[_ref.HEADER_BYTES:_ref.HEADER_BYTES + split] if profile else b""


def _verify_card(card: bytes, row: dict, meta: dict, ordinal: int, profile_id: int) -> None:
    layout = (_ref.LAYOUT_MAJOR, _ref.LAYOUT_MINOR)
    if len(card) != _ref.CARD_BYTES or struct.unpack_from("<HH", card, 4) != layout:
        raise ValueError(f"Invalid card size or layout at ordinal {ordinal}")
    split = struct.unpack_from("<H", card, 0x008)[0]
    if split > _ref.ARENA_BYTES:
        raise ValueError(f"Invalid arena split at ordinal {ordinal}")
    try:
        info = _ref.unpack_basic(card)
    except InvalidSignature as exc:
        raise ValueError(f"Invalid signature at ordinal {ordinal}") from exc
    if (
        int(row["ordinal"]) != ordinal
        or info["card_id"] != row["card_id"]
        or info["object_sha256"] != row["object_sha256"]
        or info["card_id"] != meta["cxcc"]["card_id"]
        or info["object_sha256"] != meta["artifact"]["sha256"]
    ):
        raise ValueError(f"Card, index, or sidecar mismatch at ordinal {ordinal}")

    if bool(split) != bool(info["flags"] & _ref.FLAG_EMBEDDING_PRESENT):
        raise ValueError(f"Invalid machine payload at ordinal {ordinal}")
    payload = card[_ref.HEADER_BYTES:_ref.HEADER_BYTES + split]
    payload_hash = _ref.sha256_bytes(payload) if payload else bytes(32)
    if payload_hash != card[0x330:0x350]:
        raise ValueError(f"Machine payload digest mismatch at ordinal {ordinal}")
    profile = info["embedding_profile_id"]
    if profile != meta["policy"].get("embedding_profile_id", 0):
        raise ValueError(f"Card and sidecar disagree on embedding profile at ordinal {ordinal}")
    if profile:
        if profile != profile_id or profile not in PROFILE_DIMS or split != PROFILE_DIMS[profile] * 2:
            raise ValueError(f"Invalid embedding profile or dimension at ordinal {ordinal}")
        vector = np.frombuffer(payload, dtype="<f2").astype(np.float32)
        if not np.isclose(np.linalg.norm(vector), 1.0, atol=1e-3, rtol=0):
            raise ValueError(f"Invalid vector norm at ordinal {ordinal}")


def _verify_checksums(directory: Path, expected: set[str], card_digests: dict[str, str] | None = None) -> None:
    with (directory / "SHA256SUMS").open(encoding="utf-8") as stream:
        for line in stream:
            digest, separator, name = line.rstrip("\n").partition("  ")
            if not separator or name not in expected:
                raise ValueError(f"Unexpected or duplicate SHA256SUMS entry in {directory}: {name!r}")
            if card_digests is not None and name in card_digests and card_digests[name] != digest:
                raise ValueError(f"Manifest checksum mismatch: {directory / name}")
            if sha256_file(directory / name) != digest:
                raise ValueError(f"Checksum mismatch: {directory / name}")
            expected.remove(name)
    if expected:
        raise ValueError(f"Missing SHA256SUMS entries in {directory}: {len(expected)}")


def verify_output(directory: Path, output: dict) -> int:
    expected_count = output["cards"]
    profile = output["profile"]
    if output["layout"] == "shards":
        expected = {name for shard in output["shards"] for name in (shard["path"], shard["index"], shard["meta"])}
        if any(Path(name).name != name or name in {"", ".", ".."} for name in expected):
            raise ValueError(f"Invalid shard filenames in {directory}")
        _verify_checksums(directory, expected, {shard["path"]: shard["sha256"] for shard in output["shards"]})
        count = 0
        for shard in output["shards"]:
            cards = directory / shard["path"]
            with (
                ShardReader(cards) as reader,
                (directory / shard["index"]).open(encoding="utf-8", newline="") as index,
                (directory / shard["meta"]).open("rb") as raw,
                io.TextIOWrapper(
                    zstandard.ZstdDecompressor().stream_reader(raw, closefd=False), encoding="utf-8",
                ) as sidecars,
            ):
                if len(reader) != shard["cards"]:
                    raise ValueError(f"Shard manifest card count mismatch: {cards}")
                for card, row, line in zip_longest(reader, csv.DictReader(index, delimiter="\t"), sidecars):
                    if card is None or row is None or line is None:
                        raise ValueError(f"Shard, index, and sidecar counts differ: {cards}")
                    _verify_card(card, row, json.loads(line), count, profile)
                    count += 1
    elif output["layout"] == "files":
        expected = {"index.tsv"}
        with (directory / "index.tsv").open(encoding="utf-8", newline="") as index:
            count = 0
            for row in csv.DictReader(index, delimiter="\t"):
                card = _card_path(directory, count)
                sidecar = card.with_suffix(".cxcc.json")
                expected.update((card.name, sidecar.name))
                _verify_card(card.read_bytes(), row, json.loads(sidecar.read_text(encoding="utf-8")), count, profile)
                count += 1
        _verify_checksums(directory, expected)
    else:
        raise ValueError(f"Unknown output layout {output['layout']!r}")
    if count != expected_count:
        raise ValueError(f"Manifest card count mismatch in {directory}")
    return count
