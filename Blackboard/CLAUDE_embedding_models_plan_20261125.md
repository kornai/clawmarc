---
from: Claude Opus 5.5 (Claude Code, VS Code), working with Vince Szigetvari (VS)
to: VS, AK
cc: GPT-5 Codex, Gemini
date: 2026-11-25
re: Plan for adding eight embedding model families to mintkit, with an emphasis on chunks embedded in context; questions to settle before implementation
---

# Summary

VS asked for mintkit to support these model families: e5, bge-m3,
jina v3/v4, CDE, Qwen3-Embedding, GTE-Qwen2, NV-Embed and E5-Mistral. The
priority is models that can embed **a chunk conditioned on its context**.

Three different things are called "context" here, and the families
support different ones:

- **Neighbouring text in the same document.** Two ways to use it:
  - *late chunking:* encode the whole document once, then pool each
    chunk's tokens. Fits jina v3/v4 and bge-m3; experimental for the
    decoder models.
  - *prefix conditioning* (the existing `ctxprefix`): prepend the title
    and the previous tokens as text. Works with every model.
- **The corpus.** CDE conditions each vector on a sample of the corpus.
- **A task instruction.** Qwen3, GTE-Qwen2, E5-Mistral, NV-Embed and
  e5-instruct use one; it mainly affects the query side.

The plan has five phases (§5):

1. Generalize the model registry and encoder path.
2. Add standard encoders.
3. Add late chunking.
4. Add CDE.
5. Run the 4–8B decoder models on evaluation subsets only.

Two constraints shape every decision:

- **Card size.** The 2,816-byte card arena holds at most about 1,024
  f16 dimensions plus a short text prefix. Anything wider needs
  Matryoshka (MRL) truncation, or it stays vectors-only.
- **The RTX 4060 Ti (16 GB).** The 7–8B models do not fit in fp16 with
  activations, and at about 1–2k tok/s they would need months for 2M long
  documents. They are realistic only for 200–1,000-document evaluation
  sets.

§6 lists the questions that need an answer before implementation.

# 1. Constraints from the repo

- **Card arena.** 4096-byte card = 1216 header + 2816 arena. At f16:

  | dims | bytes | bytes left for text |
  |---|---|---|
  | 384 | 768 | 2048 |
  | 768 | 1536 | 1280 |
  | 1024 | 2048 | 768 |
  | 2048+ | — | does not fit |

  `Embedding_Model_Rationale.md` already accepts spending more of the
  arena on the vector.
- **Profiles.** A card needs a registered profile, set in
  `EMBEDDING_PROFILES` (`reference/libangel_mint.py`) and in the spec
  draft. Today there are profiles 1–3. `bge-m3` and `jina-v3` are already
  in `mintkit/models.py` with `profile=0`, which means vectors only and
  no cards.
- **Model identity.** Under the 2026-09-07 proposal, a profile names one
  checkpoint through a digest set of its safetensors, config and
  tokenizer files. Remote-code models also need the digests of their
  `.py` files.
- **Pinned remote code.** mintkit already refuses `jina-v3` without
  `--allow-remote-code` and a pinned commit. That rule extends to CDE,
  NV-Embed, and any other model that needs `trust_remote_code`.
- **Runtime.** `myenv` has transformers 5.19 and sentence-transformers
  6.1. Several remote-code models were written for transformers 4.x
  (see §3).
- **Direct ids (from the speed-up branch).** The encoder now receives
  the chunker's token ids. That makes late chunking straightforward: the
  chunk spans (`token_start`/`token_end`) are already positions in the
  whole-document id sequence.

# 2. The models

Columns: approx. params; native dim; max context; pooling; prefix or
instruction; needs remote code; licence; fits on a card (≤ 1024 dims);
estimated tok/s on the 4060 Ti in fp16; estimated hours for 2M
MLDR-length documents (15.2B tokens).

| family / checkpoint | params | dim | context | pooling | prefix / instruction | remote code | licence | card | est. tok/s | est. h for 2M |
|---|---|---|---|---|---|---|---|---|---|---|
| e5: `intfloat/multilingual-e5-large` (or `-instruct`) | 560M | 1024 | 512 | mean | `passage: ` / `query: ` (instruct: task line on queries) | no | MIT | yes, 1024 | ~40k | ~105 |
| e5: `intfloat/multilingual-e5-base` | 278M | 768 | 512 | mean | `passage: ` / `query: ` | no | MIT | yes, 768 | ~120k | ~35 |
| e5: `intfloat/e5-base-v2` (English) | 110M | 768 | 512 | mean | as above | no | MIT | yes | ~140k | ~30 |
| `BAAI/bge-m3` (dense head) | 568M | 1024 | 8192 | CLS | none | no | MIT | yes, 1024 | ~40k | ~105 |
| `jinaai/jina-embeddings-v3` | 570M | 1024 (MRL to 32) | 8192 | mean | LoRA task adapter (`retrieval.passage` / `.query`) | **yes** | CC BY-NC 4.0 (check) | yes, ≤ 1024 | ~35k | ~120 |
| `jinaai/jina-embeddings-v4` | 3.8B (Qwen2.5-VL) | 2048 (MRL 128–2048) | 32k | mean | task adapters | **yes** | Qwen Research License (non-commercial) | only with MRL ≤ 1024 | ~3k | ~1,400 |
| CDE: `jxm/cde-small-v2` | ~140M (ModernBERT, check) | 768 | 512 | two-stage, corpus-conditioned | `search_document: ` / `search_query: ` (check) | **yes** | check | yes | ~100k | ~40 + first stage |
| `Qwen/Qwen3-Embedding-0.6B` | 0.6B | 1024 (MRL 32–1024) | 32k | last token (EOS) | instruction on queries only | no (ST-native) | Apache-2.0 | yes | ~25k | ~170 |
| `Qwen/Qwen3-Embedding-4B` | 4B | 2560 (MRL) | 32k | last token | as above | no | Apache-2.0 | only with MRL | ~3k | ~1,400 |
| `Qwen/Qwen3-Embedding-8B` | 8B | 4096 (MRL) | 32k | last token | as above | no | Apache-2.0 | only with MRL | ~1.5k | ~2,800 |
| `Alibaba-NLP/gte-Qwen2-1.5B-instruct` | 1.5B | 1536 | 32k | last token | instruction on queries | check | Apache-2.0 | no (no MRL) | ~9k | ~470 |
| `Alibaba-NLP/gte-Qwen2-7B-instruct` | 7B | 3584 | 32k | last token | as above | check | Apache-2.0 | no | ~1.7k | ~2,500 |
| `nvidia/NV-Embed-v2` | 7.9B (Mistral) | 4096 | 32k | latent-attention | instruction on queries | **yes** | CC BY-NC 4.0 | no | ~1.5k | ~2,800 |
| `intfloat/e5-mistral-7b-instruct` | 7B | 4096 | 4k (trained shorter, check) | last token | instruction on queries | no | MIT | no | ~1.7k | ~2,500 |

About the estimates:

- **Throughput** extrapolates from the speed-up measurements. Throughput
  falls roughly in proportion to non-embedding parameters (bge-small
  ≈ 450k tok/s, mBERT ≈ 170k tok/s in fp16 with direct ids). These are
  orders of magnitude to be replaced by `bench` rows. Long-window late
  chunking costs more than this, because attention grows with the
  square of the window.
- **Memory.** In fp16 the 7–8B models need about 15–16 GB for weights
  alone, so on a 16 GB card they need int8/4-bit quantization or CPU
  offload. The 4B models fit in fp16 with short windows.
- **Disk.** About 15 GB per 7–8B checkpoint, and about 75 GB for the
  whole list.
- **Licence and remote-code entries marked "check"** are from search
  results and memory. They must be confirmed on the model card when the
  revision is pinned.

# 3. Remarks per model

- **e5.** "e5" covers several checkpoints. VS's earlier experiment
  used `multilingual-e5-base` (768 dims natively, no truncation needed)
  and it beat bge-m3 (MRR@20 0.874 vs 0.849), so it is the first e5 to
  add; `multilingual-e5-large-instruct` follows.

  > **Do not forget the e5 prefixes.** Every document and chunk must be
  > encoded as `passage: <text>` and every query as `query: <text>`
  > (the `-instruct` variant: queries as
  > `Instruct: <task>\nQuery: <text>`, documents with no prefix). e5 was
  > trained only with these prefixes. Without them its retrieval
  > quality drops noticeably, and the failure is silent: nothing errors,
  > the vectors just get worse. mintkit enforces this:
  > - the prefixes live in the ModelSpec (`doc_prefix`, `query_prefix`),
  >   not in a CLI flag, so they cannot be omitted by accident;
  > - with direct ids the prefix tokens are prepended as ids after the
  >   chunking, so they do not count against the 480-token body budget
  >   and do not shift chunk spans;
  > - `eval` applies `query_prefix` to every query;
  > - the prefix strings are recorded in the manifest, the card's
  >   `policy`, and the profile;
  > - the P0 equivalence test fails if encoding without the prefix
  >   matches the stored reference vectors, i.e. the test checks the
  >   prefix was actually applied.
- **bge-m3.** The easiest long-context model: standard sentence-
  transformers, MIT, 1024 dims. Not MRL-trained, but VS's experiment
  shows plain truncation + re-normalisation is nearly lossless at 768
  (see §6.1), so it gets a 768 card. mintkit uses only the dense output; the
  sparse and ColBERT heads would need a different card payload. It pools
  with CLS, not mean, so late chunking (mean over a span of token
  states) is a step away from how it was trained, though the late-
  chunking paper reports that it still works for such models. It is a
  good control model: one model, with and without late chunking.
- **jina v3.** The model built for late chunking. Its task LoRA has to
  be selected by remote code; mintkit already pins it. Open points:
  - whether that code still loads under transformers 5.19 (untested);
  - the non-commercial licence;
  - **direct ids probably can't be used**, because the adapter is
    applied inside the custom forward. It needs its own adapter or
    `--no-direct-ids`.
- **jina v4.** A 3.8B multimodal Qwen2.5-VL backbone with 2048 dims, a
  32k context and non-commercial terms. It costs about 10× v3 per token.
  Recommendation: implement v3 first and treat v4 as an evaluation-
  subset model like the 7B group.
- **CDE (cde-small-v2).** Conditions on the **corpus**, not on
  neighbouring chunks. Stage 1 embeds a "minicorpus" (a few hundred
  documents sampled from the target corpus) into dataset embeddings.
  Stage 2 embeds every document and query given those. Consequences:
  - The vector depends on which documents were sampled. The sample (ids
    plus the digest of the dataset-embedding tensor) must be part of the
    run manifest, and probably of the profile.
  - Cards from two corpora with different minicorpora are not
    comparable unless one fixed minicorpus is published per profile.
  - Queries must be embedded with the same dataset embeddings, so
    `mintkit eval` has to load them from the run.
  - The maximum length is 512, so long documents still need chunking.
    The resulting chunk vectors are corpus-conditioned but not
    neighbour-conditioned. It can be combined with `ctxprefix`.
  - Needs remote code. Compatibility with transformers 5 is unknown.
- **Qwen3-Embedding.** The cleanest of the decoder models: Apache-2.0,
  sentence-transformers-native, MRL down to 32 dims (so 4B and 8B can be
  cut to 1024 for cards), last-token pooling with an appended EOS, and
  instructions on queries only. Notes:
  - The direct-ids path must append the same EOS that the tokenizer
    template adds, and its pooling must find the last real token with
    right padding. The model card uses left padding. This needs the same
    equivalence test as the speed-up work.
  - Decoder states only see the **left** context. "Late chunking" with a
    decoder means reading the hidden state at a chunk's last token after
    the whole document prefix. That is natural for left-context
    conditioning, but not what the model was trained for (it was trained
    to pool at EOS). It is an experiment, not a default.
  - 0.6B is the only size practical for millions of documents here.
- **GTE-Qwen2.** Very similar to Qwen3-Embedding but older, with no MRL:
  1536 and 3584 dims do not fit on a card without a projection (PCA or
  random), which would be our own change to the model. Suggest the
  1.5B for evaluation subsets, vectors only. Check whether current
  revisions still need `trust_remote_code`.
- **NV-Embed-v2.** Latent-attention pooling in remote code that was
  written for transformers 4.x. There are reports of breakage and a
  community fork for 5.x, and we should not run fork code. It is also
  non-commercial and 4096 dims with no MRL. It probably needs its own
  venv with the pinned transformers version from its model card.
  Possibly the lowest priority. NVIDIA's newer
  `llama-nemotron-embed-1b-v2` could be a smaller alternative (licence
  to be checked).
- **E5-Mistral-7B.** MIT and loads with sentence-transformers, last-
  token pooling, 4096 dims with no MRL. It was trained on short
  sequences, so long windows degrade it. Evaluation subsets only,
  vectors only.

# 4. Context-conditioned chunk embedding in mintkit

Today each long document is split into chunks of at most 480 body tokens
(`chunking_label` "independent"). `ctxprefix` is a second chunking label
whose encoder inputs differ. A reduction (`mean_tokw`, `ema`, …) turns
chunk vectors into the document vector. Each context mode below becomes
a **chunking label**, i.e. a different way of producing chunk vectors.
The existing reductions then apply unchanged.

| mode | chunking label | what the encoder sees | models |
|---|---|---|---|
| independent (exists) | `independent` | each chunk alone | all |
| prefix (exists) | `ctxprefix-…` | title + previous *k* tokens + chunk | all |
| late chunking (new) | `late-w{W}o{O}` | windows of up to *W* tokens with overlap *O*; chunk vector = pooled token states over the chunk's span | jina v3/v4, bge-m3, e5 (W = 512), Qwen3 (experimental) |
| corpus-conditioned (new) | `cde-{minicorpus digest}` | chunk + dataset embeddings | CDE |

Implementation outline:

1. **ModelSpec becomes a full model contract.** New fields: `pooling`;
   `doc_prefix` / `query_prefix` / `query_instruction`; `max_tokens`;
   `native_dim` / `mrl_dims`; `remote_code` with a pinned revision; a
   digest set; `licence`; `context_modes`; `half_safe`; `direct_ids_ok`.
   The manifest's `model_specs` already records the spec, so runs stay
   self-describing.
2. **The direct-ids encoder becomes pooling-aware.** It returns the
   transformer's token states. Pooling comes from the model's own module
   for whole chunks, or from our span pooling for late chunking. EOS and
   prefix ids are added from the tokenizer template. Every model gets
   the speed-up equivalence test against `encode` before use.
3. **Late chunking.**
   - Plan the chunks exactly as today, so token spans and sidecar
     counts are unchanged.
   - Encode the document in windows of *W* tokens with overlap.
   - For each chunk, mean-pool the token states inside its span from
     the window that holds it with the most context on both sides.
   - Normalize.

   Because the chunk spans don't change, `independent` vs `late` is a
   clean comparison, and `reduce` keeps working on cached chunk vectors.
4. **CDE.** A new `mint` stage before embedding:
   - sample the minicorpus with a recorded seed, or load a published
     minicorpus;
   - compute and store the dataset embeddings;
   - record their digest in the manifest;
   - use them in `eval` for queries.
5. **Query side.** `eval` uses `query_prefix` / `query_instruction` from
   the spec, so instruction models are evaluated the way they were
   trained.
6. **Card dimension: 768 for every profile.** MRL models (jina,
   Qwen3) and bge-m3 (validated by VS's experiment) are cut to 768 with
   the existing `--card-dim`. **Truncation must always be followed by
   re-normalisation to unit length**: the first 768 values of a unit
   vector are no longer unit length, and with a raw dot product the
   scores would shift. mintkit renormalises in `pack_vector`; `eval`
   and any external code using card vectors must do the same (or use
   cosine). Models whose truncation is untested or harmful stay
   `profile=0`.

# 5. Phases

| phase | content | done when |
|---|---|---|
| P0 | ModelSpec contract; pooling-aware direct encoder; prefixes; revision pinning and digest recording for every new model | bge/MPNet/mBERT unchanged byte-for-byte; equivalence test framework per model |
| P1 | multilingual-e5-base (prefixes!), bge-m3 (768 by truncation), Qwen3-Embedding-0.6B, then multilingual-e5-large-instruct: independent + ctxprefix | equivalence test passes; `bench mldr-200` and `eval` rows for each |
| P2 | late chunking: bge-m3, jina v3 (pinned, remote code); Qwen3-0.6B experimental | `eval` on MLDR dev: late vs independent vs ctxprefix, same chunk spans |
| P3 | CDE (cde-small-v2): minicorpus stage, dataset embeddings in the run and in eval | reproducible from the manifest; `eval` rows |
| P4 | evaluation-subset models: Qwen3-4B (fp16), gte-Qwen2-1.5B, then the 7–8B group (Qwen3-8B, gte-Qwen2-7B, E5-Mistral, NV-Embed-v2, jina v4), subject to Q3 | `eval` rows on 200–1,000 documents |
| P5 | card profiles for the winners (spec and reference change) | profiles registered with digest sets |

P0–P2 can run on this box. P3 depends on CDE loading under
transformers 5. P4 depends on the answer to Q3.

# 6. Questions to settle before implementing

1. **Licences.** jina v3, jina v4 and NV-Embed-v2 are non-commercial,
   and CDE's licence is unconfirmed. Are ClawMARc cards meant for public
   or commercial redistribution? If so, should these models be limited
   to research runs and never get a card profile?
2. **Cards or vectors only?** Which models should get card profiles,
   which requires a spec change (draft-03)? Who assigns the profile ids
   (AK)? For MRL models, what is the card dimension: 1024 (768 bytes of
   text left), 768, or 512? Should models without MRL above 1024 dims
   (GTE-Qwen2, NV-Embed, E5-Mistral) stay vectors-only, or is our own
   projection to 1024 acceptable?
3. **7–8B models on a 16 GB card.** Options:
   - (a) int8/4-bit quantization: changes the vectors, adds a dependency
     (bitsandbytes), and makes byte reproducibility harder;
   - (b) a rented or bigger GPU, or AK's machine;
   - (c) the 4B/1.5B sizes only.

   Are they in scope for production minting at all, or only for
   evaluation subsets?
4. **What "conditioned on context" should mean first:** neighbouring
   text (late chunking / ctxprefix), document metadata (title/abstract),
   or the corpus (CDE)? This decides whether P2 or P3 comes first.
5. **Chunk length for long-context models.** Keep 480 body tokens so all
   models are comparable, with late chunking supplying the context? Or
   use the native length (8k/32k), where most MLDR documents become one
   chunk, i.e. a whole-document embedding?
6. **CDE minicorpus.** Sample one per run (the vector depends on the
   run's corpus) or publish one fixed minicorpus per profile (vectors
   comparable across corpora)? Which corpus should it come from?
7. **Which e5:** settled: `multilingual-e5-base` first (VS's
   experiment), then `multilingual-e5-large-instruct`.
8. **jina v3 or v4:** v3 first, with v4 as an evaluation-only model
   (recommended)?
9. **GTE-Qwen2 size:** 1.5B, 7B, or both? **NV-Embed:** v2, or
   NVIDIA's newer smaller model instead?
10. **Environment.** Remote-code models may need older transformers.
    Is a separate venv per model family acceptable, recorded in the
    manifest's software block? Or should models that don't load in the
    main env be dropped?
11. **Query instructions.** Use each model card's default retrieval
    instruction, recorded in the profile? Or one instruction wording of
    our own across models?
12. **Disk and download.** About 75 GB for the full list. Is that fine
    on this box? Should the model files also be minted as cards, as the
    identity proposal suggests?

## 6.1 Answers from VS (2026-11-25)

- **Q1 licences:** university project, no commercial use. jina v3/v4,
  NV-Embed and CDE are fine to use and may get card profiles.
- **Q2 card dimension:** 768 for every card profile, like the existing
  ones; Matryoshka (MRL) models are preferred because they truncate to
  768 cleanly. Consequences:
  - 768 via MRL: jina v3, jina v4, Qwen3-Embedding (0.6B/4B).
  - 768 natively: multilingual-e5-base, e5-base-v2, CDE-small-v2.
  - bge-m3 (1024, not MRL-trained): VS's earlier retrieval experiment
    (Table I: multilingual-e5-base, BGE-M3 at 1024/768/512/256 dims)
    shows plain truncation + renormalisation is nearly free at 768
    (MRR@20 0.849 → 0.847, Hit@1 0.776 → 0.773) and still usable at 512
    (0.837) and 256 (0.802). So bge-m3 gets a 768 card by truncation.
    The same experiment had multilingual-e5-base (768, native) ahead of
    bge-m3 (MRR@20 0.874), so it joins P1.
  - multilingual-e5-large(-instruct) (1024): truncation untested; run the
    same truncation check before deciding.
  - Two checks that hold for all of this: truncated vectors are
    re-normalised before scoring (§4 item 6), and e5 is always run with
    its `passage: ` / `query: ` prefixes (§3).
  - 1536+ without MRL (gte-Qwen2-1.5B): vectors-only.
- **Q3 large models:** drop the 7–8B checkpoints (gte-Qwen2-7B,
  NV-Embed-v2, E5-Mistral-7B, Qwen3-8B). Smaller stand-ins:
  gte-Qwen2-1.5B, Qwen3-Embedding-0.6B/4B, multilingual-e5-large-instruct
  (E5-Mistral's small sibling). NV-Embed has no small version and is
  dropped. jina v4 (3.8B) fits at fp16 and stays as evaluation-only.
- **Q4, Q6:** explained to VS in chat; answers pending.
- **Q5 chunk length:** leaning to bigger chunks; open.
- **Q7/Q10 environment:** goal is one transformers version for all
  models. P0 gains a step: load every pinned checkpoint in `myenv`
  (transformers 5.19), compare against the model card's reference
  vectors, and for remote-code models that break, vendor the pinned
  modeling file into mintkit with minimal patches (digests recorded).
  Separate venvs only as a last resort.

# 7. Idea (VS): a distribution per document instead of one mean

Store the chunk mean *and* a covariance describing the spread of the
chunk vectors; retrieve top-x by mean, then rerank by how well the query
fits each document's distribution. Related work: Gaussian embeddings
(Vilnis & McCallum 2015), probabilistic embeddings (PCME), and, in
retrieval, multi-vector representations (ColBERT, chunk sets).

- A full covariance at 768 dims is ~295k values: impossible on a card.
  Feasible forms: diagonal (d values) or low-rank (mean + k principal
  directions with their variances).
- Budget at f16 (2816-byte arena): 512 mean + 512 diagonal = 2048 bytes;
  768 mean + rank-1 = 3072 bytes, does not fit; 384 mean + rank-2 =
  2304 bytes.
- The query is a point, so the rerank score is a point-to-distribution
  score (e.g. Mahalanobis distance or log-likelihood), not a
  distribution distance.
- Short documents have 1–3 chunks, so their covariance is undefined or
  noise; bigger chunks (Q5) make that worse. Needs shrinkage toward a
  global covariance.
- Cheap to test offline: `--keep-chunk-vectors` already stores every
  chunk vector, so the rerank can be evaluated on MLDR without changing
  cards. Baseline to beat: max-sim over the stored chunk vectors.

# Sources

- jina-embeddings-v4: https://jina.ai/en-US/models/jina-embeddings-v4/ and arXiv 2506.18902
- Qdrant Jina docs (late chunking in v3 and v4): https://qdrant.tech/documentation/embeddings/jina-embeddings/index.md
- cde-small-v2: https://huggingface.co/jxm/cde-small-v2, paper arXiv 2410.02525
- Qwen3-Embedding: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B, https://qwenlm.github.io/blog/qwen3-embedding, arXiv 2506.05176
- NV-Embed-v2: https://huggingface.co/nvidia/NV-Embed-v2, compatibility thread https://huggingface.co/nvidia/NV-Embed-v2/discussions/15
- Other licences, dimensions and context lengths are from memory and must be checked on each model card when pinning the revision.
