"""Known embedding recipes and their card eligibility."""

from dataclasses import dataclass
from pathlib import Path

from . import _ref


@dataclass(frozen=True)
class ModelSpec:
    alias: str
    name: str
    dim: int
    profile: int = 0
    query_prefix: str = ""
    mrl: bool = False
    task_adapter: bool = False

    def load(self, device: str, *, query: bool = False, revision: str | None = None):
        if not self.task_adapter and revision is None:
            return _ref.load_embedding_model(self.name, device)
        from sentence_transformers import SentenceTransformer

        kwargs = {}
        if self.task_adapter:
            kwargs = {
                "trust_remote_code": True,
                "model_kwargs": {"default_task": "retrieval.query" if query else "retrieval.passage"},
            }
        return SentenceTransformer(self.name, device=device, revision=revision, **kwargs)


MODELS = {
    "bge": ModelSpec("bge", "BAAI/bge-small-en-v1.5", 384, 1, "Represent this sentence for searching relevant passages: "),
    "mbert": ModelSpec("mbert", "bert-base-multilingual-cased", 768, 2),
    "mpnet": ModelSpec("mpnet", "sentence-transformers/paraphrase-multilingual-mpnet-base-v2", 768, 3),
    "bge-m3": ModelSpec("bge-m3", "BAAI/bge-m3", 1024),
    "jina-v3": ModelSpec("jina-v3", "jinaai/jina-embeddings-v3", 1024, mrl=True, task_adapter=True),
}


def resolve_models(names: list[str], *, allow_remote_code: bool, revision: str | None) -> dict[str, ModelSpec]:
    selected = {}
    for name in names:
        if name in MODELS:
            spec = MODELS[name]
        else:
            candidates = [model for model in MODELS.values() if model.name == name or (
                Path(name).expanduser().is_dir() and Path(name).name == Path(model.name).name
            )]
            if not candidates:
                raise ValueError(f"Unknown model {name!r}")
            original = candidates[0]
            from dataclasses import replace
            spec = replace(original, name=str(Path(name).expanduser().resolve()) if Path(name).expanduser().is_dir() else name)
        pinned = revision is not None and len(revision) == 40 and all(c in "0123456789abcdef" for c in revision)
        if spec.task_adapter and (not allow_remote_code or not (pinned or Path(spec.name).is_dir())):
            raise ValueError("jina-v3 requires --allow-remote-code and a pinned model commit or local snapshot")
        if spec.alias in selected:
            raise ValueError(f"Duplicate model: {spec.alias}")
        selected[spec.alias] = spec
    return selected
