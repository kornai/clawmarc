"""Prepare, batch-embed, and sign source documents."""

import base64
import dataclasses
import hashlib
import traceback
from copy import deepcopy
from collections import OrderedDict, defaultdict
from threading import Lock, local

import numpy as np

from . import _ref
from .reductions import normalize


def failure(doc_id, model, stage, exc):
    return {
        "doc_id": doc_id, "model": model, "stage": stage, "error": str(exc),
        "traceback": "".join(traceback.format_exception(exc)),
    }


def prepared_template(prep, *, include_preimage=False):
    fields = {
        field.name: getattr(prep, field.name)
        for field in dataclasses.fields(prep)
        if field.name not in {"extracted_text", "full_text", "preimage", "segments"}
    }
    for key in ("object_sha256", "machine_payload", "source_or_manifest_sha256"):
        fields[key] = fields[key].hex()
    fields["segments"] = dataclasses.asdict(prep.segments)
    fields["preimage"] = prep.preimage if include_preimage else ""
    fields["preimage_sha256"] = hashlib.sha256(prep.preimage.encode()).hexdigest()
    return fields


def restore_template(fields):
    fields = fields.copy()
    fields.pop("preimage_sha256")
    for key in ("object_sha256", "machine_payload", "source_or_manifest_sha256"):
        fields[key] = bytes.fromhex(fields[key])
    fields["segments"] = _ref.TextSegments(**fields["segments"])
    return _ref.Prepared(**fields, extracted_text="", full_text="")


def _span_metadata(plan):
    return [{
        "kind": chunk.kind, "section_path": chunk.section_path, "char_span": chunk.char_span,
        "token_start": chunk.token_start, "token_end": chunk.token_end,
    } for chunk in plan.chunks]


class TextCache:
    """Share prepared document text between model passes under a byte limit."""

    def __init__(self, limit_mb):
        self.limit = limit_mb * 1024**2
        self.size = 0
        self.entries = OrderedDict()
        self.lock = Lock()

    def get(self, doc, prepare):
        if not self.limit:
            return prepare(doc)
        if doc.path is None:
            key = doc.doc_id, hashlib.sha256(doc.text.encode()).digest(), doc.title
        else:
            stat = doc.path.stat()
            key = doc.doc_id, doc.path, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns
        with self.lock:
            if key in self.entries:
                self.entries.move_to_end(key)
                return self.entries[key][0]
        value = prepare(doc)
        cost = 2048 + len(value.machine_payload) + 4 * sum(map(len, (
            value.extracted_text, value.full_text, value.body_text, value.preimage, value.segments.abstract,
        )))
        if cost > self.limit:
            return value
        with self.lock:
            if key in self.entries:
                self.size -= self.entries.pop(key)[1]
            self.entries[key] = value, cost
            self.size += cost
            while self.size > self.limit:
                self.size -= self.entries.popitem(last=False)[1][1]
        return value


class Producer:
    def __init__(self, args, source_name, spec, reductions, timing, text_cache=None):
        self.args = args
        self.source_name = source_name
        self.spec = spec
        self.timing = timing
        self.text_cache = text_cache
        self.model = None
        self.tokenizers = local()
        self.tokenizer_lock = Lock()
        self.reductions = reductions
        self.groups = defaultdict(list)
        for reduction in reductions:
            self.groups[reduction.chunking_label].append(reduction)
        self.policy = _ref.resolve_content_policy(args)
        self.signing = _ref.signing_context(args)

    def prepare(self, doc):
        return self.text_cache.get(doc, self._prepare_document) if self.text_cache else self._prepare_document(doc)

    def _prepare_document(self, doc):
        name = f"{self.source_name}/{doc.doc_id}"
        if doc.path is not None:
            prep = _ref.prepare_card(
                doc.path.read_bytes(), doc.path.name, self.args, path=doc.path,
                content_policy=self.policy, strict_tools=True,
            )
            prep.artifact_path = name
            return prep
        return _ref.prepare_card(
            doc.text.encode("utf-8"), name, self.args, mime="text/plain", content_policy=self.policy,
            dataset_title=doc.title, synthetic_title=f"{self.source_name} {doc.doc_id}",
        )

    def _load(self):
        with self.timing.measure("load"):
            if self.args.device == "cpu" and self.args.torch_threads is not None:
                try:
                    import torch
                except ImportError:
                    pass
                else:
                    torch.set_num_threads(self.args.torch_threads)
            self.model = self.spec.load(self.args.device, revision=self.args.model_revision)
        with self.timing.measure("warmup", accelerator=True):
            self.model.encode(["mintkit warm-up"], normalize_embeddings=True, show_progress_bar=False)

    def _plan(self, prep, reduction):
        with self.timing.measure("chunk"):
            if not hasattr(self.tokenizers, "value"):
                try:
                    self.tokenizers.value = deepcopy(self.model.tokenizer)
                except (TypeError, AttributeError, RuntimeError):
                    self.tokenizers.value = None
            if self.tokenizers.value is not None:
                return self._plan_with_tokenizer(prep, reduction, self.tokenizers.value)
            with self.tokenizer_lock:
                return self._plan_with_tokenizer(prep, reduction, self.model.tokenizer)

    def _plan_with_tokenizer(self, prep, reduction, tokenizer):
        limit = _ref.body_tokens_for(self.model)
        if reduction.name != "ctxprefix":
            return _ref.plan_chunks(prep, tokenizer, f"fixed:{limit}")
        previous_limit = min(reduction.options["prev_tokens"], (limit - 1) // 2)
        title = prep.segments.title if prep.title_source not in {"synthetic", "filename"} else ""
        title_ids = tokenizer.encode(title, add_special_tokens=False) if reduction.options["title"] and title else []
        title_ids = title_ids[:(limit - previous_limit - 1) // 2]
        body_window = limit - len(title_ids) - previous_limit
        raw = dataclasses.replace(prep, preimage=prep.full_text)
        plan = _ref.plan_chunks(raw, tokenizer, f"fixed:{body_window}")
        previous = []
        chunks = []
        for chunk in plan.chunks:
            ids = tokenizer.encode(chunk.text, add_special_tokens=False)[:body_window]
            prefix = previous[-previous_limit:] if previous_limit else []
            text = tokenizer.decode(title_ids + prefix + ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)
            chunks.append(dataclasses.replace(chunk, text=text))
            previous = ids
        return dataclasses.replace(plan, chunks=chunks)

    def encode_window(self, entries, executor=None):
        active = {index: prep for index, prep in entries.items() if prep.wants_vector and self.spec is not None}
        if not active:
            return {}, {}
        if self.model is None:
            self._load()
        vectors, errors = defaultdict(dict), {}
        for label, reductions in self.groups.items():
            plans = {}
            pending = {index: prep for index, prep in active.items() if index not in errors}
            tasks = {
                index: executor.submit(self._plan, prep, reductions[0]) for index, prep in pending.items()
            } if executor else {}
            for index, prep in pending.items():
                try:
                    plans[index] = tasks[index].result() if tasks else self._plan(prep, reductions[0])
                except Exception as exc:
                    errors[index] = (label, exc)
            slots = [(index, chunk_index, chunk) for index, plan in plans.items() for chunk_index, chunk in enumerate(plan.chunks)]
            if self.args.threads:
                slots.sort(key=lambda item: (
                    -(item[2].token_end - item[2].token_start), -len(item[2].text), item[0], item[1],
                ))
                steps = (slots[start:start + self.args.batch_chunks] for start in range(0, len(slots), self.args.batch_chunks))
            else:
                steps = ([(index, pos, chunk) for pos, chunk in enumerate(plan.chunks)] for index, plan in plans.items())
            gathered = {index: np.empty((len(plan.chunks), self.spec.dim), dtype=np.float32) for index, plan in plans.items()}
            for batch in steps:
                try:
                    with self.timing.measure("embed", len(batch), accelerator=True):
                        options = {"batch_size": self.args.batch_chunks} if self.args.threads else {}
                        values = self.model.encode(
                            [item[2].text for item in batch], normalize_embeddings=True,
                            convert_to_numpy=True, show_progress_bar=False, **options,
                        )
                        if values.shape != (len(batch), self.spec.dim) or not np.isfinite(values).all():
                            raise ValueError("Unexpected embedding shape or nonfinite chunk values")
                        for (index, pos, _), vector in zip(batch, values, strict=True):
                            gathered[index][pos] = vector
                except Exception as exc:
                    for index, _, _ in batch:
                        errors.setdefault(index, (label, exc))
            for index, plan in plans.items():
                if index not in errors:
                    vectors[index][label] = (plan, gathered[index])
        return vectors, errors

    def pack_all(self, prep, groups):
        results, caches = {}, {}
        for reduction in self.reductions:
            grouped = groups.get(reduction.chunking_label)
            if grouped is None:
                if self.spec is None or self.spec.profile:
                    card, meta = _ref.pack_and_sign(
                        prep, b"", {"embedding_mode": "none"}, self.args, include_preimage=self.args.include_preimage,
                        signing=self.signing, record_title_source=True,
                    )
                    results[reduction.label] = encode_result(card, meta, None)
                continue
            plan, chunks = grouped
            vector = reduction.reduce(chunks, plan.token_counts)
            results[reduction.label] = self.pack_vector(prep, plan, vector, reduction)
            if self.args.keep_chunk_vectors and reduction.chunking_label not in caches:
                caches[reduction.chunking_label] = {
                    "chunks": encode_array(chunks), "spans": _span_metadata(plan),
                    "limit": plan.max_body_tokens, "counts": plan.token_counts,
                }
        return results, caches

    def pack_vector(self, prep, plan, vector, reduction, *, preimage_sha=None):
        full = encode_array(vector)
        if not self.spec.profile:
            return {"vector": full}
        dim = self.args.card_dim or self.spec.dim
        stored = normalize(vector[:dim]) if dim != self.spec.dim else vector
        embedding = _ref.vector_to_f16le(stored)
        policy = _ref.embedding_policy_meta(self.spec.name, plan, stored, embedding, prep.preimage, recipe=_ref.PREIMAGE_RECIPE_V2)
        if preimage_sha is not None:
            policy["source_text_sha256"] = preimage_sha
        if reduction.name != "mean_tokw":
            policy.pop("pooling")
            policy.update(reduction=reduction.canonical, reduction_sha256=reduction.sha256)
            if reduction.name == "ctxprefix":
                digest = hashlib.sha256()
                for chunk in plan.chunks:
                    text = chunk.text.encode()
                    digest.update(len(text).to_bytes(8, "little"))
                    digest.update(text)
                policy["chunk_inputs_sha256"] = digest.hexdigest()
        policy["mrl"] = {"native_dim": self.spec.dim, "card_dim": dim, "mrl_trained": self.spec.mrl}
        card, meta = _ref.pack_and_sign(
            prep, embedding, policy, self.args, signing=self.signing,
            include_preimage=self.args.include_preimage, record_title_source=True,
        )
        if preimage_sha is not None and not self.args.include_preimage:
            meta["text_segments"]["embedding_preimage_sha256"] = preimage_sha
        if self.args.threads:
            meta["embedding_batching"] = {"batch_chunks": self.args.batch_chunks, "length_sorted": True, "sort_window": self.args.sort_window}
        return encode_result(card, meta, full)


def encode_array(value):
    return base64.b64encode(np.asarray(value, dtype="<f4").tobytes()).decode("ascii")


def decode_array(value):
    return np.frombuffer(base64.b64decode(value), dtype="<f4")


def encode_result(card, meta, vector):
    return {"card": base64.b64encode(card).decode("ascii"), "meta": meta, "vector": vector}
