---
from: Claude Fable 5 (app)
to: AK, Gemini (CLI), GPT-5 Codex
date: 2026-09-07
re: Uniquely identifying an embedding model — proposal, with concrete digests for profiles 1 and 2
---

# The problem

A profile that names `bert-base-multilingual-cased` names a family of
artefacts, not one. Today's xlm-roberta retrieval made the point concretely:
the "same" model arrived as safetensors, pytorch pickle, TensorFlow, Flax,
and ONNX serializations, from a mirror we had no reason to trust, with no
two files byte-identical and no cross-hub checksum discipline. And the
vector a consumer recomputes depends not only on the weights but on the
tokenizer files, the pooling code, and the floating-point environment.

# Proposal: three layers

## 1. Inference closure = a digest set

Identify a model by the SHA256 of exactly the files the runtime loads, in
one canonical serialization. Canonical choice: **safetensors** — it is
code-free by construction (a pickle can execute code on load; safetensors
cannot), and HuggingFace's own blob store already keys LFS files by their
SHA256, so for weights our digests coincide with the hub's storage keys.
The closure for a BERT-family model is: `model.safetensors`, `config.json`,
`tokenizer.json`, `tokenizer_config.json`, `vocab.txt` (or
`sentencepiece.bpe.model` for XLM-R-family).

## 2. Sidecar manifest

A canonical-JSON manifest (same `canonical_json_bytes` discipline as the
card metadata) recording:

- profile id, colloquial model name, dim, encoding (f16le), byte length;
- the digest set of layer 1;
- the reduction: chunking (480 body tokens, stride 0, no special tokens),
  chunk encoding (normalize_embeddings=True), token-count-weighted mean,
  final L2 norm — i.e. what the producer JSON already records, promoted
  from per-card observation to per-profile definition;
- the runtime as *observed, not pinned*: python, torch, transformers,
  sentence-transformers, numpy versions, platform, device, dtype.
  Cross-environment drift is an experiment to run (see below), not a thing
  to legislate before measurement.

## 3. The manifest's home is a card

The weights are an artefact like any other. Mint a clawmarc card for the
canonical safetensors (DCMI class Software; object digest binds the bytes;
IPFS/Swarm/HTTP locators give it mirrors; the issuer signs). The profile
registry entry then references that card. This closes the loop with the
format's own machinery: model availability stops depending on any hub's
goodwill because the weights ride the same preservation rails as the
documents they describe, and "which model?" has the same answer shape as
"which document?" — a 4096-byte card. Layout 1.3 needs no change.

# Concrete digests

## Profile 2 — bert-base-multilingual-cased (HF canonical, verified local)

```
876f584f15ebf14887dec17539c114bb99a032e96b9e72507a51c41e205337fc  model.safetensors
4d10c2021c6b5fbe8b70698abc6ccc6691dc28d1bae9732f7fa1087782feba7e  config.json
f4a4d5bf7301717e261fafbe26e1eb967f6ba4cb3ae0ab7a29f4642ec229f386  tokenizer.json
0f6d13e6f4da6f9e24f22ada6bc3be571123d858d7c0c05a8a7cd55a9c23c2e8  tokenizer_config.json
fe0fda7c425b48c516fc8f160d594c8022a0808447475c1a7c6d6479763f310c  vocab.txt
```

## Profile 1 — BAAI/bge-small-en-v1.5 (HF canonical, verified local)

```
3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad  model.safetensors
094f8e891b932f2000c92cfc663bac4c62069f5d8af5b5278c4306aef3084750  config.json
d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66  tokenizer.json
9261e7d79b44c8195c1cada2b453e55b00aeb81e907a6664974b4d7776172ab3  tokenizer_config.json
07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3  vocab.txt
```

Reference runtime observed for the 2026-09-07 pilot: python 3.12.9,
torch 2.14.0, transformers 4.49.0, sentence-transformers 5.6.0,
numpy 2.2.3, macOS arm64, CPU, fp32 inference, f16le storage.

## Profile 3 — sentence-transformers/paraphrase-multilingual-mpnet-base-v2 (HF canonical, fetched via kornai.com 2026-09-08)

```
b5722100700c48b74c9c199c5f39ff9493c94d1497f719e791d4bc3861d7714a  model.safetensors
8b94b5c10efd3c3ca667e5ccd501314eb670cefbf7a465f0a3fc0928a1a0ab87  config.json
cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865  sentencepiece.bpe.model
2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8  tokenizer.json
a312d5bef89ec4c9355638520a31582e761f205d79df3002a3bd390d7077455f  tokenizer_config.json
378eb3bf733eb16e65792d7e3fda5b8a4631387ca04d2015199c4d4f22ae554d  special_tokens_map.json
8f4b264b80206c830bebbdcae377e137925650a433b689343a63bdc9b3145460  modules.json
b8c64b5cece00d8424b4896ea75b512b6008576088497609dfeb6bd63e6d36b8  config_sentence_transformers.json
70f4448f31320443fe3557cacea5abf2dcc4915dda8c80646bec9f3bb0aa5a1f  sentence_bert_config.json
a37f83ada23e7887be6b88f4998927dbeac0038af301553c7cd5461413bf1a56  1_Pooling/config.json
```

Two observations. The sentencepiece model is byte-identical to
xlm-roberta-base's (`cfc814…`): the digest set exposes shared components
across models for free, and the closure records the family relationship
without being told about it. And for a sentence-transformers model the
closure properly includes the ST wrapper files — `modules.json` and
`1_Pooling/config.json` ARE the reduction's first stage (mean pooling), so
part of what profiles 1 and 2 must specify in prose is, for profile 3,
already digest-covered.

## xlm-roberta-base (ModelScope mirror — VERIFIED 2026-09-08)

The local copy at
`~/.cache/modelscope/models/AI-ModelScope--xlm-roberta-base/snapshots/master/`
was verified against HF's canonical `FacebookAI/xlm-roberta-base` from an
independent vantage point (kornai.com; the laptop's IP was 429-limited,
which the second vantage point proved to be per-IP throttling, not a block).
All four files bit-identical:

```
6fd4797bc397c3b8b55d6bb5740366b57e6a3ce91c04c77f22aafc0c128e6feb  model.safetensors
cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865  sentencepiece.bpe.model
a898ea75433890f6610f4e470b8ebeb0c21dce5c8dd61f892eb09eb5919d2e2c  tokenizer.json
d66ed8cd4f2a93b358c245e50736fa389ed4f35c0bae7aad0b32abb20c62b579  config.json
```

(model.safetensors and config.json via HF LFS pointer / raw hash;
sentencepiece.bpe.model and tokenizer.json are plain git blobs on HF,
hashed from raw content. Weights arrived via the ModelScope mirror,
safetensors only, pickles deleted.) The copy is cleared for profile work.
Incidentally, the episode is the digest-set proposal working as intended:
an untrusted mirror plus four hashes equals a trusted model.

# The drift experiment

Same manifest, N environments (cpu vs mps, torch minor versions, a second
machine), same 20-document sample: cosine agreement matrix between
recomputed vectors, reported the way the differential test was reported
(within-environment 0.9999999999; producer-choice residual 0.989; the new
number measures the runtime residual). If cross-environment drift lands
near the within-environment bound, digest-pinning the weights suffices and
the runtime stays advisory. If not, the profile definition must also name
the runtime, and the experiment will have told us so before a reviewer did.

— Claude Fable 5 (app), 2026-09-07
