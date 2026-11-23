---
from: Claude Opus 5.5 (Claude Code, VS Code), working with Vince Szigetvari (VS)
to: AK, GPT-5 Codex, Gemini
date: 2026-11-23
re: Addendum to the minting pipeline plan (2026-11-17): pluggable reductions, conditional (sequential / hierarchical) chunk embedders, retrieval backends and their comparison
---

# Why

`CLAUDE_minting_pipeline_plan_20261117.md` hard-wires one reduction:
independent chunks, a token-weighted mean, then L2 normalisation. It also
leaves retrieval out of scope. VS needs three more things:

1. **Several chunk-pooling strategies.** Some of them need chunk
   embeddings created in order, not in one batch.
2. **Conditional embedders.** These embed a chunk given the embedding (or
   context) of another chunk, either as a chain (chunk 2 given 1, chunk 3
   given the state after 2, …) or hierarchically (paragraphs within
   sections within the document). The methods come from
   `contextual-embedding-methods-brief.md` (2026-11-19), §2.1–2.6.
3. **Retrieval over the minted vectors through several backends**: the
   mmap-the-cards path that the fixed 4096 B card exists for, plus plain
   numpy, torch, FAISS flat, FAISS IVF and FAISS HNSW. The point is to
   compare speed and to check that the rankings agree.

Section numbers like §2 refer to the 2026-11-17 plan. Everything here
fits into that plan's package layout (`mintkit/`). Milestones M0–M5 stay
as they are; this addendum adds M6–M10.

# A. Reductions as a pluggable stage

## A.1 Three execution families

How a reduction runs depends on what it needs from the encoder, so the
embed stage (§2) becomes a scheduler with three modes:

| Family | What one model call sees | Batching across documents | Methods (brief §) |
|---|---|---|---|
| **independent** | one chunk | free: any chunks from any documents (the §2 design) | baseline token-weighted mean; plain mean; head-weighted mean; max; **EMA (2.3)**; **context prefix A (2.2)**, where only the chunk text changes in `prepare` |
| **joint** | a macro-window of many chunks (up to 8192 tokens), pooled per chunk span | batch macro-windows; sort them by length | **late chunking (2.1)**: span mean-pool, or the CLS-like separator variant for bge-m3 |
| **sequential** | chunk *t* plus the state after chunk *t−1* | **step-synchronous**: at step *t*, batch the *t*-th chunk of every active document; a document leaves the batch when it runs out of chunks | **soft-prefix projector (2.4)**, **KV-cache prefix (2.6)**, hierarchical chains (B.3) |

Notes:

- EMA is order-dependent only in the reduction, not in the encoder. Its
  chunk vectors are independent, so it runs in the batched family, and
  any number of α values cost nothing extra (see A.3).
- **Step-synchronous batching.** The scheduler keeps a pool of active
  documents, grouped into buckets by chunk count so that batches stay
  full as short documents finish. Each step gathers `(doc, chunk_t,
  state_{t−1})` for up to `--batch-chunks` documents, runs one forward
  pass and scatters the new states back. Memory is bounded by the pool
  size (`--active-docs`, default 256), not by document length.
- KV-cache states don't batch well: caches have ragged lengths, and
  left-padding a decoder changes its results. The first version runs the
  KV-cache conditioner **one document per call**, with documents spread
  across a small worker pool on the GPU, and records `batch=1` in the
  sidecar. Batched caches can come later if the numbers matter.
- The equivalence test from §2 (batched vs single-document, cosine ≥
  0.9999) applies to every family, and to sequential reductions per step.

## A.2 Reduction spec and sidecar

A reduction is named by a spec string and resolved through a registry,
like sources:

```
mean_tokw                                   # current baseline (default)
mean | max | head:decay=0.9                 # independent
ema:alpha=0.5,order=forward|reverse         # independent chunks, ordered reduce
ctxprefix:prev_tokens=64,title=1            # brief 2.2 variant A
late:window=8192,overlap=512,pool=span_mean|sep_cls
chain:cond=softprefix,k=4,weights=<sha256>,out=last|mean
chain:cond=kvcache,window_chunks=4,out=last|mean
hier:<yaml file>                            # B.3; too nested for one string
```

- The sidecar's `embedding` block gets `"reduction": {canonical JSON of
  the resolved spec}` and `"reduction_sha256"`. It replaces the free-text
  `pooling` string for new cards. The old string stays for the baseline,
  so the existing cards keep validating.
- Any trained weights (projector, LoRA) are named by digest and loaded
  from `models/<sha256>/`, never from a mutable path. Brief §0 requires
  this: a profile's model includes its trained parts.
- `--reductions a b c` mints one card set per reduction. The layout is
  `cards/<model>/<reduction_label>/shard-*.cxcc`, where the label is a
  short slug plus 6 hex characters of `reduction_sha256`.

## A.3 Chunk-vector cache (keeps sweeps cheap)

Most independent reductions differ only after the encoder. With
`--keep-chunk-vectors`, the embed stage writes:

```
runs/<id>/chunks/<model>/<chunking_label>/
  chunks.f32.npy        # N_chunks × D, full dim, row order = (doc ordinal, chunk index)
  chunks.index.tsv      # doc_ordinal, chunk_idx, token_start, token_end, tokens, section_path
```

`mintkit reduce RUN_DIR --reductions ema:alpha=0.3 ema:alpha=0.7 head:...`
then mints new card sets from the cache without touching the model. Joint
and sequential reductions still need the model, but the cache doubles as
the "independent" control for them.

## A.4 Matryoshka dimensions

Following brief §0:

- Chains and hierarchies always carry **full-dimension** state. Truncation
  happens only when a vector is written out.
- A run stores the **full-dimension document vector** once, in
  `vectors/<model>/<reduction>/docs.f32.npy` plus `docs.ids.tsv`. The
  evaluation truncates to `--dims 1024,768,512,384,256`, renormalises and
  rounds to binary16 itself. This avoids minting five card sets.
- Cards are minted at one `--card-dim` per model, truncated and then
  renormalised. The sidecar records `"mrl": {"native_dim": 1024,
  "card_dim": 768, "mrl_trained": true|false}`, so a truncated bge-m3
  vector is never mistaken for a Matryoshka-trained one.

# B. Conditional embedders

## B.1 Interface

```python
class Conditioner(ABC):
    family: Literal["independent", "joint", "sequential"]
    def init_state(self, doc: Prepared) -> State: ...
    def step(self, states: list[State], chunks: list[Chunk]) -> tuple[np.ndarray, list[State]]:
        """Batch of (state_{t-1}, chunk_t) -> (chunk vectors in context, state_t)."""
    def finalize(self, state: State, chunk_vecs: np.ndarray, weights: np.ndarray) -> np.ndarray: ...
    def describe(self) -> dict: ...                  # goes into the sidecar's "reduction" block
```

`State` is opaque to the scheduler. It can be a full-dimension vector
(EMA, soft-prefix), a token window (context prefix), or a KV cache
(Qwen3). The scheduler only moves states between steps.

## B.2 Implementations (order of value, as in the brief)

| Conditioner | State | Base models | Needs training | Notes |
|---|---|---|---|---|
| `ctxprefix` | last *k* tokens of the previous chunk plus the title | any profile model | no | deterministic; overlapping text is counted twice in the mean (brief 2.2) |
| `ema` | vector | any | no | control for `softprefix`; also run reverse order and head-weighted |
| `late` (joint) | none | jina-v3 (mean-pooled), bge-m3 (CLS; test both pool modes) | no | needs `output_hidden_states` / the raw `last_hidden_state`, not `SentenceTransformer.encode` |
| `softprefix` | vector (1024) | bge-m3 (+ projector, optional LoRA) | yes (M10) | injects through `inputs_embeds` *via* the embeddings module so XLM-R positions stay correct (brief 2.4 step 2) |
| `kvcache` | KV cache, window of *n* chunks | Qwen3-Embedding 0.6B / 4B | no | last-token pooling; `out=span_mean` is an off-distribution variant to test |
| `llmctx` (2.2 B) | none | any, plus an LLM | no | **not a pipeline conditioner.** It is a `prepare`-stage text transform whose generated context is cached by digest and stored in the sidecar. Run it on a subset only, as an upper bound |

The 2026-11-17 plan's model list (bge-small, mBERT, MPNet) has no entry
for the brief's models. New registry entries: `BAAI/bge-m3`,
`jinaai/jina-embeddings-v3` (needs `trust_remote_code`, CC BY-NC, task
LoRA `retrieval.passage` / `retrieval.query`),
`Qwen/Qwen3-Embedding-0.6B` / `-4B` (query instruction prefix), and
`jxm/cde-small-v2` (needs a pinned minicorpus). `voyage-context-3` is
**eval-only**: its weights can't be archived, so it produces vectors in
`vectors/` but never cards. See open question 1 about profile ids.

## B.3 Hierarchical embedding

This needs a **segmenter** that turns extracted text into a tree, which
also goes into `Prepared`:

```
doc ─ section* ─ paragraph* ─ chunk*        (chunk = paragraph cut to the model window)
```

Segmenter strategies (`--segmenter`): `flat` (the current behaviour, one
level of fixed token chunks), `para` (split on blank lines, merge
paragraphs shorter than `min_tokens`), `heading` (markdown `#`, numbered
headings like `2.3 Foo`, and all-caps lines in `pdftotext -layout`
output), `fixed:N`. MLDR is Wikipedia plain text with the headings
flattened, so `para` is the realistic choice there, and `heading` matters
for the PDF archive. The segmenter version and the tree's spans
(character and token offsets) go into the sidecar, so the hierarchy can
be rebuilt.

A hierarchy is configured per level in YAML:

```yaml
hier:
  paragraph: {conditioner: chain:cond=softprefix,k=4, reset: per_section}   # chunks within a paragraph/section in order
  section:   {reduce: mean_tokw, condition_on: doc_title}                     # optional top-down condition
  doc:       {reduce: mean_tokw}                                              # or chain over section vectors
```

- **Bottom-up**: the vectors at each level are reduced into their parent.
  The reducer can differ per level.
- **Chain within a level**: chunk *t* given the state after *t−1*. With
  `reset: per_section`, the state restarts at each section, or carries
  across sections with `reset: never`.
- **Top-down condition**: the parent's state (the document title vector,
  or the section heading vector) is the initial state of the child chain.
- The sequential scheduler (A.1) runs a hierarchy as nested step loops.
  Levels are processed bottom-up, and each level's chains are
  step-batched across all sections of all active documents.

## B.4 Training lives outside the minting path

`mintkit/train/` (M10) trains the soft-prefix projector, and later LoRA.
It follows brief 2.4: freeze the base, use a teacher (late-chunked bge-m3,
Qwen3-4B KV-cache, or voyage-context-3), cosine/MSE plus InfoNCE plus the
Matryoshka loss at 1024/768/512/384/256, and unroll 2–4 chunks with
truncated BPTT. Its output is a weights directory named by sha256, with a
model card stub. The pipeline only loads weights.

# C. Retrieval and evaluation

The 2026-11-17 plan said retrieval was out of scope. It is in scope now,
as a new subcommand:

```bash
python -m mintkit eval runs/<id> --backends mmap numpy torch faiss-flat faiss-ivf faiss-hnsw \
       --dims 1024 768 512 384 256 --k 10 100 --device cpu cuda
python -m mintkit eval runs/<id> --scale-to 1000000          # timing on a synthetic-scaled matrix (C.4)
```

## C.1 Shared steps

1. **Export.** `mintkit export runs/<id>` writes, from the shards, a packed
   `docs.f16.npy` (N × D at card dimension) and `docs.ordinal.tsv`
   (ordinal → doc_id, card_id). It also writes columnar header fields
   (profile id, arena class, flags), as recommended in
   `CLAUDE_repo_queries_20261026.md` §4. The full-dimension store from A.4
   is used for the dimension sweep.
2. **Query encoding.** Queries are embedded with the same model and the
   model's query instruction or prefix, at full dimension. They are
   cached in `queries/<model>.f32.npy`. Query encoding time is reported
   separately and doesn't count towards backend latency.
3. **Truncate, renormalise, then binary16**, per dimension and identical
   for every backend. All backends see the same document matrix, so any
   difference comes from the backend, not the data.

## C.2 Backends (one interface)

```python
class Backend(ABC):
    name: str
    def build(self, X: np.ndarray | CardShards) -> BuildStats: ...      # time, bytes in RAM/VRAM, bytes on disk
    def search(self, Q: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]: ...   # scores, ordinals
    def params(self) -> dict: ...
```

| Backend | What it does | Exact? | Sweep |
|---|---|---|---|
| `mmap` (**reference**) | `np.memmap` over the shard. A strided view at `+0x4c0` of length `arena_split`. Streams blocks of 64k cards: f16→f32, `Q @ B.T`, merges a running top-k | exact (f32 accumulation) | block size |
| `numpy` | packed contiguous matrix in RAM, `Q @ X.T`, `argpartition` + sort | exact | f16 vs f32 storage |
| `torch` | same on a tensor, `torch.topk`. CPU, and CUDA if present | exact | f16 / f32, device |
| `faiss-flat` | `IndexFlatIP` | exact | — |
| `faiss-ivf` | `IndexIVFFlat` (IP), `nlist ≈ 4√N`, trained on min(N, 256·nlist) vectors with seed 20260910; optional `IndexIVFPQ` | approximate | `nprobe` 1, 4, 16, 64 |
| `faiss-hnsw` | `IndexHNSWFlat` (IP), M=32, efConstruction=200 | approximate | `efSearch` 16, 64, 256 |

- `faiss-cpu` becomes an optional dependency
  (`pip install -e .[faiss]`). FAISS on the GPU (`faiss-gpu-cu12`) is
  optional and only enabled if its wheels install cleanly on the 4060 Ti
  box.
- **Ties.** Every exact backend breaks ties by ascending ordinal (a stable
  sort on `(−score, ordinal)`). Without that, "the same results" can't be
  checked.
- Both phases are timed. Build time covers index construction or export.
  Load time is measured cold and warm: for `mmap`, cold means the page
  cache is dropped first, which needs `sudo` and is skipped with a note
  if not available. Query time is reported as single-query p50/p99 and
  as batched QPS.

## C.3 Do the backends agree?

Every backend is compared with `mmap` at the same dimension and k:

- **Exact backends** (numpy, torch, faiss-flat): the share of queries with
  an identical top-k id list; max |Δscore|; the first rank where the lists
  differ. Expected result: identical, apart from near-ties under f16 vs
  f32 accumulation. Any query that disagrees is logged with its two
  scores.
- **ANN backends**: recall@k against the exact top-k (the standard ANN
  measure), and the Spearman rank correlation over the shared ids.
- **Does it change the evaluation?** MRR@10, nDCG@10 and R@10/100 for every
  backend, next to the exact ones. The number that matters is "IVF
  nprobe=4 loses x nDCG@10 and is y× faster".
- Output: `runs/<id>/eval/<model>/<reduction>/results.json` and one row per
  (model, reduction, dim, backend, params) appended to
  `benchmarks/retrieval.csv`, with the same machine fields as
  `results.csv`.

## C.4 Scale caveat

A 1000-document MLDR collection runs in milliseconds on every backend, so
the timings say nothing. Two ways to time at scale:

- Real data: MS MARCO passage, at 100k and 1M cards (the
  `msmarco:passage` source already exists in §1).
- `--scale-to N`: tile the real document vectors and add small Gaussian
  noise, then renormalise. This gives representative speed (and memory
  layout, for mmap the shards are written out), and the real documents
  stay inside the set, so IR metrics on them can still be computed. It's
  marked synthetic in the results.

ANN agreement is reported at both scales, because HNSW and IVF behave
differently at 1k than at 1M.

## C.5 IR baselines

BM25 and TF-IDF over the full text and over the card text only, ported
from `src/run_ir_experiments.py` (`bm25_matrix`, `cran_metrics`). MLDR has
one positive per query, so the metrics are MRR@10, nDCG@10, R@10 and
R@100, as in the 2026-10-12 plan. The brief's collapse check (spread of
pairwise cosines on a sample) and the run-to-run cosine are added to every
eval.

# D. Changes to the 2026-11-17 plan

- §2 Embed stage: replaced by the scheduler in A.1. The "token-weighted
  mean, L2 normalise, f16le" step moves into `reductions/`.
- §3 Store: adds `chunks/`, `vectors/`, `queries/`, `eval/`, and
  `cards/<model>/<reduction>/`.
- §4 Manifest: `config` gains `reductions`, `segmenter`, `card_dim`,
  `dims`, and `weights` (sha256 of any trained parts). `software` gains
  `faiss` and `peft` versions.
- §5 Timing: per-reduction rows. Sequential reductions also report steps
  per second and average batch fill (active documents per step).
- §7 Order of work: the "Retrieval and evaluation … out of scope" line is
  replaced by C.

New layout additions:

```
mintkit/
  reductions/  base.py independent.py late.py chain.py hier.py registry.py
  conditioners/ ctxprefix.py ema.py softprefix.py kvcache.py
  segment.py                 # flat / para / heading / fixed segmenters → tree
  scheduler.py               # independent / joint / sequential execution
  retrieve/   base.py mmap.py dense.py faiss_backends.py export.py
  evaluate.py                # IR metrics, agreement, collapse, CSV rows
  train/      projector.py   # M10
```

# E. Order of work (continues M0–M5)

| Step | Content | Done when |
|---|---|---|
| M6 | reduction registry and independent family (mean_tokw, mean, head, max, ema, ctxprefix); chunk-vector cache and `mintkit reduce`; full-dimension vector store and MRL truncation; new model entries for bge-m3 and jina-v3 | `mean_tokw` cards are byte-identical to M3's; an EMA sweep runs from the cache without loading the model |
| M7 | `export`, all six backends, `eval`, agreement report, `retrieval.csv`, `--scale-to` | the exact backends agree with `mmap` on MLDR 1k at every dim; ANN recall@10 is reported against them; one 1M-scale timing table |
| M8 | joint family: late chunking (span mean and sep-CLS) for bge-m3 and jina-v3; segmenter; bottom-up hierarchy | brief §4 step 2 go/no-go on MLDR (and ConTEB if it is loaded as a BEIR source) |
| M9 | sequential scheduler; `kvcache` with Qwen3-0.6B; hierarchical chains | step-batched results match one-document-at-a-time results (cosine ≥ 0.9999); Qwen3 ceiling numbers reported |
| M10 | `train/` projector (frozen base, MRL loss); `softprefix` inference; compared against EMA | the projector beats EMA, or the method is dropped (brief 2.3) |

M7 comes before M8–M10 on purpose. Every new reduction gets judged by the
eval harness, so it has to exist first.

# Open questions for VS / AK

1. **Profile ids for experimental models.** bge-m3, jina-v3, Qwen3 and the
   soft-prefix projector have no `embedding_profile_id`. Should there be
   an experimental range (cards marked non-canonical in the sidecar), or
   should these runs only write `vectors/` and skip minting cards until a
   profile is pinned?
2. jina-v3 is CC BY-NC. Is it acceptable for experiments if it can never
   become a public profile?
3. Is a hierarchy worth building for MLDR, given its flattened headings?
   Or should hierarchy be judged mainly on the PDF archive, which has no
   relevance judgments, using neighbour stability only?
4. For `--scale-to`, is synthetic tiling acceptable for the timing tables,
   or should the 1M number come only from MS MARCO passage?
5. Does the KV-cache variant need batching across documents, or is one
   document per call (with the throughput cost reported) enough?
