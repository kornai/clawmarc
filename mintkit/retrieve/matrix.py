"""Represent native card vectors as a strided matrix or export packed copies."""

import csv
import os
import struct
from pathlib import Path

import numpy as np

from .._ref import CARD_BYTES, HEADER_BYTES
from ..operations import iter_cards, read_run, variants
from ..store import _vector_bytes


def index_rows(root, output):
    paths = [root / "index.tsv"] if output["layout"] == "files" else [root / shard["index"] for shard in output["shards"]]
    for path in paths:
        with path.open(encoding="utf-8", newline="") as stream:
            yield from csv.DictReader(stream, delimiter="\t")


def card_rows(root, output):
    yield from zip(index_rows(root, output), iter_cards(root, output), strict=True)


class CardMatrix:
    """Expose eligible rows of native shards in their packed-export order."""

    def __init__(self, root, output, dimension):
        self.segments = []
        self.paths = []
        row_count = 0
        for shard in output["shards"]:
            path = root / shard["path"]
            if not shard["cards"]:
                continue
            raw = np.memmap(path, dtype=np.uint8, mode="r")
            n = shard["cards"]
            profile = np.ndarray((n,), dtype="<u2", buffer=raw, offset=0x304, strides=(CARD_BYTES,))
            selected = profile != 0
            rows = np.ndarray((n, dimension), dtype="<f2", buffer=raw, offset=HEADER_BYTES, strides=(CARD_BYTES, 2))
            self.segments.append((rows, None if selected.all() else np.flatnonzero(selected)))
            self.paths.append(path)
            row_count += int(selected.sum())
        self.shape = row_count, dimension

    def blocks(self, block_size):
        offset = 0
        for matrix, selected in self.segments:
            size = len(matrix) if selected is None else len(selected)
            for start in range(0, size, block_size):
                stop = min(size, start + block_size)
                yield offset + start, matrix[start:stop] if selected is None else matrix[selected[start:stop]]
            offset += size


def write_strided(path, matrix):
    n, dim = matrix.shape
    records = np.memmap(path, dtype=np.uint8, mode="w+", shape=(n * CARD_BYTES,))
    rows = np.ndarray((n, dim), dtype="<f2", buffer=records, offset=HEADER_BYTES, strides=(CARD_BYTES, 2))
    for start in range(0, n, 8192):
        rows[start:start + 8192] = matrix[start:start + 8192]
    records.flush()
    return rows


def advisory_evict(paths):
    advice = getattr(os, "POSIX_FADV_DONTNEED", None)
    if advice is None or not hasattr(os, "posix_fadvise") or not paths:
        return False
    try:
        for path in paths:
            with Path(path).open("rb") as stream:
                os.posix_fadvise(stream.fileno(), 0, 0, advice)
    except OSError:
        return False
    return True


def export_variant(root, output, directory):
    directory.mkdir(parents=True, exist_ok=True)
    dim = output.get("card_dim")
    if dim is None:
        for _, card in card_rows(root, output):
            if vector := _vector_bytes(card):
                dim = len(vector) // 2
                break
    dim = dim or 0
    count = output.get("vectors")
    if count is None:
        count = sum(bool(_vector_bytes(card)) for _, card in card_rows(root, output))
    documents = np.lib.format.open_memmap(directory / "docs.f16.npy", mode="w+", dtype="<f2", shape=(count, dim))
    fields = {
        "profile_id": np.lib.format.open_memmap(directory / "profile_id.npy", mode="w+", dtype="<u2", shape=(count,)),
        "arena_class": np.lib.format.open_memmap(directory / "arena_class.npy", mode="w+", dtype="u1", shape=(count,)),
        "flags": np.lib.format.open_memmap(directory / "flags.npy", mode="w+", dtype="<u4", shape=(count,)),
    }
    position = 0
    with (directory / "docs.ordinal.tsv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(("ordinal", "doc_id", "card_id", "card_ordinal"))
        for row, card in card_rows(root, output):
            vector = _vector_bytes(card)
            if not vector:
                continue
            documents[position] = np.frombuffer(vector, dtype="<f2")
            fields["profile_id"][position] = struct.unpack_from("<H", card, 0x304)[0]
            fields["arena_class"][position] = card[0x00A]
            fields["flags"][position] = struct.unpack_from("<I", card, 0x00C)[0]
            writer.writerow((position, row["doc_id"], row["card_id"], row["ordinal"]))
            position += 1
    if position != count:
        raise ValueError(f"Exported {position} vectors, expected {count}")
    documents.flush()
    for array in fields.values():
        array.flush()
    return documents


def export_run(directory, model=None, reduction=None):
    run = read_run(directory)
    count = 0
    for alias, label, root, output in variants(directory, run, model=model, reduction=reduction):
        if output["layout"] == "vectors":
            continue
        exported = export_variant(root, output, directory / "export" / alias / label)
        count += len(exported)
    return count
