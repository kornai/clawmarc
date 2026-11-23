"""Stream document and chunk vectors to NumPy files and TSV indexes."""

import base64
import csv
import json
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from .produce import decode_array
from .store import CardWriter


def tsv(stream):
    return csv.writer(stream, delimiter="\t", lineterminator="\n")


class MatrixWriter:
    def __init__(self, path: Path, dimension: int):
        self.path = path
        self.dimension = dimension
        self.count = 0
        self.raw = path.with_suffix(".raw")

    def __enter__(self):
        self.stream = self.raw.open("wb")
        return self

    def append(self, array):
        array = np.asarray(array, dtype="<f4").reshape(-1, self.dimension)
        self.stream.write(array.tobytes())
        self.count += len(array)

    def __exit__(self, exc_type, *_):
        self.stream.close()
        if exc_type is None:
            shape = (self.count, self.dimension)
            if self.count:
                values = np.memmap(self.raw, dtype="<f4", mode="r", shape=shape)
                with self.path.open("wb") as stream:
                    np.lib.format.write_array(stream, values, allow_pickle=False)
                del values
            else:
                np.save(self.path, np.empty(shape, dtype="<f4"), allow_pickle=False)
            self.raw.unlink()


class OutputWriter:
    def __init__(self, stack, root, spec, reduction, args):
        self.spec = spec
        self.cards = None
        self.matrix = None
        label = reduction.label
        if spec is None or spec.profile:
            self.cards = stack.enter_context(CardWriter(root / "cards" / label, layout=args.layout, shard_size=args.shard_size))
        if spec is not None:
            directory = root / "vectors" / label
            directory.mkdir(parents=True)
            self.matrix = stack.enter_context(MatrixWriter(directory / "docs.f32.npy", spec.dim))
            stream = stack.enter_context((directory / "docs.ids.tsv").open("w", encoding="utf-8", newline=""))
            self.ids = tsv(stream)
            self.ids.writerow(("ordinal", "doc_id", "card_id"))
        self.description = {
            "model": spec.name if spec else None, "profile": spec.profile if spec else 0,
            "reduction": reduction.canonical, "reduction_sha256": reduction.sha256,
            "card_dim": (args.card_dim or spec.dim) if spec else None,
            "native_dim": spec.dim if spec else None, "mrl_trained": spec.mrl if spec else False,
            "layout": args.layout if self.cards is not None else "vectors",
        }

    def append(self, doc_id, item):
        card_id = ""
        if "card" in item:
            self.cards.append(doc_id, base64.b64decode(item["card"]), item["meta"])
            card_id = item["meta"]["cxcc"]["card_id"]
        if item["vector"] is not None:
            self.ids.writerow((self.matrix.count, doc_id, card_id))
            self.matrix.append(decode_array(item["vector"]))

    def result(self):
        return self.description | {
            "cards": self.cards.count if self.cards else 0,
            "shards": self.cards.shards if self.cards else [],
            "vectors": self.matrix.count if self.matrix else 0,
        }


class CacheWriter:
    def __init__(self, stack, directory, dimension):
        directory.mkdir(parents=True)
        self.matrix = stack.enter_context(MatrixWriter(directory / "chunks.f32.npy", dimension))
        self.templates = stack.enter_context((directory / "documents.jsonl").open("w", encoding="utf-8"))
        self.index = tsv(stack.enter_context((directory / "chunks.index.tsv").open("w", encoding="utf-8", newline="")))
        self.index.writerow(("doc_ordinal", "chunk_idx", "token_start", "token_end", "tokens", "section_path", "kind", "char_start", "char_end"))

    def append(self, sequence, doc_id, template, cache):
        count = len(cache["counts"]) if cache else 0
        self.templates.write(json.dumps({
            "doc_id": doc_id, "template": template, "start": self.matrix.count, "count": count,
            "counts": cache["counts"] if cache else [], "limit": cache["limit"] if cache else 0,
        }, ensure_ascii=False) + "\n")
        if not count:
            return
        self.matrix.append(decode_array(cache["chunks"]))
        for index, (span, tokens) in enumerate(zip(cache["spans"], cache["counts"], strict=True)):
            start, end = span["char_span"] if span["char_span"] is not None else ("", "")
            self.index.writerow((
                sequence, index, span["token_start"], span["token_end"], tokens,
                json.dumps(span["section_path"]), span["kind"], start, end,
            ))
