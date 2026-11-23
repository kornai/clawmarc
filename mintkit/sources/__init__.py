"""Registry for sources addressed by kind:value."""

from pathlib import Path

from .base import Doc, Qrels, Query, Source, select
from .beir import BEIRSource
from .folder import FolderSource
from .mldr import MLDRSource
from .msmarco import MSMarcoSource

SOURCES: dict[str, type[Source]] = {
    "folder": FolderSource,
    "mldr": MLDRSource,
    "beir": BEIRSource,
    "msmarco": MSMarcoSource,
}


def load_source(spec: str, **options) -> Source:
    kind, separator, value = spec.partition(":")
    if not separator or not value or kind not in SOURCES:
        available = ", ".join(SOURCES)
        raise ValueError(f"Invalid source {spec!r}; expected kind:value with kind in {available}")
    if kind == "beir":
        path = Path(value).expanduser()
        if path.parent == Path(".") and not path.exists():
            value = str(Path("data/beir") / path)
    return SOURCES[kind](value, **options)


__all__ = ["Doc", "Qrels", "Query", "Source", "SOURCES", "load_source", "select"]
