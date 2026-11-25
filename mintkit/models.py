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
    half_safe: bool = False  # fp16 document vectors checked against fp32 (cosine >= 0.9995)

    def load(self, device: str, *, query: bool = False, revision: str | None = None, precision: str = "fp32"):
        if not self.task_adapter and revision is None:
            model = _ref.load_embedding_model(self.name, device)
        else:
            from sentence_transformers import SentenceTransformer

            kwargs = {}
            if self.task_adapter:
                kwargs = {
                    "trust_remote_code": True,
                    "model_kwargs": {"default_task": "retrieval.query" if query else "retrieval.passage"},
                }
            model = SentenceTransformer(self.name, device=device, revision=revision, **kwargs)
        if precision != "fp32":
            import torch

            model.to(PRECISIONS[precision](torch))
        return model


PRECISIONS = {"fp32": lambda torch: torch.float32, "fp16": lambda torch: torch.float16, "bf16": lambda torch: torch.bfloat16}


def resolve_precision(requested: str, device: str, spec: ModelSpec) -> str:
    """Pick the encoder precision: fp16 only on accelerators and for models checked against fp32."""
    if requested == "auto":
        return "fp16" if device.startswith("cuda") and spec.half_safe else "fp32"
    if requested == "fp16" and device == "cpu":
        raise ValueError("--precision fp16 requires a cuda or mps device")
    return requested


def default_device() -> str:
    try:
        import torch
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


MODELS = {
    "bge": ModelSpec("bge", "BAAI/bge-small-en-v1.5", 384, 1, "Represent this sentence for searching relevant passages: ", half_safe=True),
    "mbert": ModelSpec("mbert", "bert-base-multilingual-cased", 768, 2),
    "mpnet": ModelSpec("mpnet", "sentence-transformers/paraphrase-multilingual-mpnet-base-v2", 768, 3, half_safe=True),
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
