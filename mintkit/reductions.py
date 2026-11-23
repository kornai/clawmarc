"""Resolve independent embedding reductions and context-prefix settings."""

import hashlib
import json
import math
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np

from ._ref import reduce_mean_tokw


class Method(NamedTuple):
    defaults: dict
    reducer: str


REGISTRY = {
    "mean_tokw": Method({}, "mean_tokw"),
    "mean": Method({}, "mean"),
    "max": Method({}, "max"),
    "head": Method({"decay": 0.9}, "head"),
    "ema": Method({"alpha": 0.5, "order": "forward"}, "ema"),
    "ctxprefix": Method({"prev_tokens": 64, "title": 1}, "mean_tokw"),
}


@dataclass(frozen=True)
class Reduction:
    name: str
    options: dict

    @property
    def canonical(self) -> dict:
        return {"name": self.name, "version": 1, **self.options}

    @property
    def sha256(self) -> str:
        encoded = json.dumps(self.canonical, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    @property
    def label(self) -> str:
        return f"{self.name}-{self.sha256[:6]}"

    @property
    def chunking_label(self) -> str:
        return self.label if self.name == "ctxprefix" else "independent"

    def reduce(self, chunks: np.ndarray, counts: list[int]) -> np.ndarray:
        operation = REGISTRY[self.name].reducer
        if operation == "mean_tokw":
            return reduce_mean_tokw(chunks, counts)
        if operation == "mean":
            return normalize(chunks.mean(axis=0))
        if operation == "max":
            return normalize(chunks.max(axis=0))
        if operation == "head":
            positions = np.arange(len(chunks), dtype=np.float32)
            return normalize(np.average(chunks, axis=0, weights=self.options["decay"] ** positions))
        ordered = chunks if self.options["order"] == "forward" else chunks[::-1]
        alpha = self.options["alpha"]
        state = ordered[0]
        for vector in ordered[1:]:
            state = (1 - alpha) * state + alpha * vector
        return normalize(state)


def normalize(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector, axis=-1, keepdims=True)
    if not np.isfinite(norm).all() or np.any(norm == 0):
        raise ValueError("Cannot normalize a zero or nonfinite vector")
    return vector / norm


def parse_reductions(specs: list[str]) -> list[Reduction]:
    reductions = {}
    for spec in specs:
        name, separator, raw = spec.partition(":")
        if name not in REGISTRY:
            raise ValueError(f"Unknown reduction {name!r}")
        options = REGISTRY[name].defaults.copy()
        seen = set()
        for assignment in raw.split(",") if separator else ():
            key, equals, value = assignment.partition("=")
            if not equals or key not in options or key in seen:
                raise ValueError(f"Invalid parameter {assignment!r} in {spec!r}")
            seen.add(key)
            options[key] = type(options[key])(value)
        for key in ("alpha", "decay"):
            if key in options and (not math.isfinite(options[key]) or not 0 < options[key] <= 1):
                raise ValueError(f"{key} must be in (0, 1]")
        if options.get("order", "forward") not in {"forward", "reverse"}:
            raise ValueError("EMA order must be forward or reverse")
        if options.get("title", 0) not in {0, 1} or options.get("prev_tokens", 0) < 0:
            raise ValueError("Context prefix requires title=0 or 1 and prev_tokens >= 0")
        reduction = Reduction(name, options)
        reductions[reduction.label] = reduction
    return list(reductions.values())
