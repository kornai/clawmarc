---
from: Claude Opus 5.5 (Claude Code, VS Code), working with Vince Szigetvari (VS)
to: VS, AK, GPT-5 Codex, Gemini
date: 2026-11-23
re: Implementation plan for the minting pipeline (2026-11-17 plan + 2026-11-23 addendum): repo reality check, decisions taken, PR-by-PR work packages
---

# Summary

The two design notes (`CLAUDE_minting_pipeline_plan_20261117.md`, called
**P** below, and `CLAUDE_minting_pipeline_addendum_20261123.md`, called
**A**) say *what* to build. This note says *in what order, in which files,
with which tests*. It also lists where the designs don't match the
current repo, and six design points the notes leave implicit that will
cause bugs if not settled up front (§3).

Work is cut into about 25 PR-sized packages. M0–M4 are about 3–4 weeks
of work, and all of it runs on this laptop (CPU only). M5 needs the
4060 Ti box and AK's M2. M6–M7 are about 2 more weeks. M8–M10 depend on
research results and are only sketched.

# 1. Reality check: plan assumptions vs. the repo (2026-11-23, HEAD `0b52701`)

| Plan assumes | Repo actually has | Consequence |
|---|---|---|
| `build_card` in `libangel_mint.py` (P §0.3) | `build_card` is in `reference/libangel_catalog.py:194`. `libangel_mint.py` has `document_embedding_f16le` (L159) and `make_card` (the project-zip minter used for the committed cards) | The phase split touches **both** files. `make_card` stays as it is |
| experiment1 bge/mBERT cards serve as golden files (P §0.5) | `experiments/` was **never committed**: `.gitignore` has `! experiments/experiment1.py` with a space after `!`, so the negation never matched. The commit "experiment 1 script" (`ccf1a1b`) changed only `.gitignore`. Script, cards and timings exist only on the 4060 Ti box | Goldens are regenerated from the pre-refactor commit (WP0.3). Fix the `.gitignore` line and commit `experiment1.py` from the 4060 Ti box |
| root `test_*.py` move to `experiments/bench_*` (P layout) | `experiments/` is git-ignored | Move them to `bench/legacy/` instead. They hardcode AK's macOS paths (`/Volumes/114/...`), so they are archives, not runnable benchmarks |
| `pip install -e .[gpu,msmarco]` | no `pyproject.toml`, `setup.py` or requirements file | WP0.1 creates the packaging |
| `myenv` has the stack | on this laptop, `myenv` has numpy, pandas, psutil, Jupyter. **No** torch, sentence-transformers, transformers, cryptography or datasets | WP0.1 installs it. Nothing in `reference/` imports here today |
| GPU available | this machine: Intel Raptor Lake, Iris Xe, 20 threads, 31 GB, **no CUDA**. The 4060 Ti is VS's other box | Everything up to M4 is developed and tested on CPU with small models. CUDA paths are tested on the 4060 Ti box |
| `data/mldr/...` local (P §1) | `data/` absent here | the MLDR loader downloads dev/test (small) on demand. Test fixtures are synthetic |
| `contextual-embedding-methods-brief.md` (A §B) | not found anywhere under `$HOME` | needed before M8–M10. Whoever has it should put it on the Blackboard |
| `sys.path.insert(... / "reference")` in both producer files | resolves to `reference/reference` (does not exist). Imports work only because Python puts the script's own directory on `sys.path` | fixed in WP0.2. `mintkit` imports `reference/` through one shim (§3.1) |

# 2. Defaults taken for the open questions

None of these block the work. Each is easy to reverse, and each is
marked in the code where it applies. VS/AK, overrule any of them.

| Question (source) | Default used in this plan |
|---|---|
| Package location (P Q1) | `mintkit/` at the top level |
| Store layout (P Q2) | shards by default, `--layout files` as an option |
| MS MARCO variant (P Q3) | passage first (M1). Document later, which is one more registry line |
| Hostnames in `results.csv` (P Q4) | store a `host_label` (default: `"<GPU or 'cpu'> / <CPU model short>"`) plus a salted hash of the hostname. No raw hostnames in committed files |
| Multi-GPU (P Q5) | one embed device per process. `--devices` accepts a list, but more than one entry is an error until needed |
| Profile ids for experimental models (A Q1) | **vectors only**: bge-m3, jina-v3, Qwen3 and soft-prefix write `vectors/` and are evaluated, but no cards are minted until a profile id is pinned. This avoids touching the spec |
| jina-v3 CC BY-NC (A Q2) | eval-only, like voyage-context-3 |
| Hierarchy on MLDR (A Q3) | build the `para` segmenter. Judge hierarchy on MLDR by IR metrics and on the PDF archive by neighbour stability |
| `--scale-to` (A Q4) | both: synthetic tiling marked `synthetic: true`, plus real MS MARCO 1M when it's minted |
| KV-cache batching (A Q5) | batch=1 first, with the throughput cost reported |

# 3. Design points the notes leave implicit (settle these before coding)

## 3.1 Importing `reference/` from `mintkit`

`reference/` uses flat imports (`from content_policy import ...`). Turning
it into a package would change the CLI and the paper's command lines.
Instead, `mintkit/_ref.py` puts `reference/` on `sys.path` once and
re-exports what mintkit needs. Every other mintkit module imports
`reference/` only through `mintkit._ref`. The direction rule ("nothing in
`reference/` imports mintkit") gets a test (WP1.0).

## 3.2 Determinism actually requires a reorder buffer and deterministic batching

P §2 says the writer is serial, "so the shard order is deterministic per
run". With P prepare workers that is not true: documents finish in
scheduling order. There is a second, subtler problem. **Batch
composition changes the floats** (padding, P §2), so if batches are
formed in arrival order, the f16 vector bytes of the same document can
differ between two runs on the same machine.

Fix:

- The reader stamps every doc with a sequence number `seq`.
- **Reorder after prepare:** a small reorder buffer releases prepared docs
  to the embedder in `seq` order. This is cheap, because prepare is not
  the bottleneck for long documents.
- The embedder forms batches from **fixed windows** of consecutive docs
  (`--sort-window` docs, default 64), length-sorts chunks inside the
  window, and cuts batches of `--batch-chunks`. Batch composition is then
  a pure function of (input order, settings).
- The writer has a second reorder buffer, so shard ordinal = `seq` order
  (minus failures).
- Failed docs send a tombstone through the queues so that neither buffer
  stalls. `--max-inflight` bounds how much one slow document (a huge PDF)
  can hold up.

Guarantee to state in the README: *same input, settings, model and
device type → byte-identical shards.* Across device types (CPU vs CUDA vs
MPS), vectors agree to cosine ≥ 0.9999, not byte for byte.

## 3.3 `prepare` is model-independent; chunking is per model

P puts tokenize/chunk inside prepare and also caches extracted text
between models. These two conflict, because chunking depends on the
model's tokenizer and `max_seq_length`. Split them:

- `prepare_card(...) → Prepared`: extraction, segments, policy, preimage.
  Model-independent, and cached across models (`--text-cache-mb`, keyed
  by `object_sha256`).
- `chunk_for_model(preimage, tokenizer, max_body_tokens) → ChunkPlan`:
  runs in the prepare thread pool, once per model pass.

## 3.4 The batched path must re-tokenize exactly like the single path

`document_embedding_f16le` tokenizes, cuts token ids, **decodes each
chunk back to text**, and calls `model.encode(chunk_texts)`, which
tokenizes again. The batched embedder must feed the same decoded
`chunk_texts`, not the token ids. Otherwise its vectors differ from the
single-document path by more than padding noise, and the cosine ≥ 0.9999
test fails for a reason that has nothing to do with batching.

## 3.5 Signing in a process pool

`Ed25519PrivateKey` is not picklable. Process-pool workers derive the key
from `--issuer-seed` in the pool initializer. Workers receive a slim
`PackInput` (segments, hashes, classes, embedding bytes), not the full
`Prepared`, so that pickling the full text doesn't eat the gain. Whether
`--sign-procs` is needed at all is decided by the MS MARCO benchmark in
WP3.4.

## 3.6 Crash-safe sidecars and resume

A `.jsonl.zst` stream cut off by a crash is unreadable past its last
complete frame. The writer closes a zstd frame at every checkpoint and
records `(shard, ordinal, bytes_card, bytes_index, bytes_meta)` in
`checkpoint.json`. Resume truncates all three files to the checkpoint and
continues. Doc ids past the checkpoint are minted again, so no partial
state survives.

# 4. Work packages

Size: **S** ≈ ≤1 day, **M** ≈ 2–3 days, **L** ≈ 1 week. Each package is
one PR with its tests. "Done when" is the merge criterion.

## M0′ — Bootstrap (prerequisite to M0)

**WP0.1 Packaging and environment (S).**
- `pyproject.toml`: package `mintkit`, Python ≥ 3.12.
  - Core deps: numpy, cryptography, psutil, pyyaml, zstandard.
  - Extras: `embed` = torch, sentence-transformers, transformers;
    `mldr` = huggingface_hub; `msmarco` = ir_datasets; `faiss` = faiss-cpu;
    `gpu` = nvidia-ml-py; `dev` = pytest, pytest-timeout.
- `scripts/setup_env.sh`: creates or updates `myenv`. It installs the
  torch CPU wheel when `nvidia-smi` is missing, and the cu128 wheel
  otherwise.
- Fix the `.gitignore` negation (`!experiments/experiment1.py`) and add
  `runs/`, `models/`, `data/`.

*Done when:* `pip install -e .[embed,dev]` works in `myenv` on this
laptop, and `python reference/libangel_catalog.py --help` runs.

**WP0.2 Test skeleton and fake model (S).**
- `tests/conftest.py`, with markers `model` (downloads a real model; uses
  bge-small, 33M), `gpu`, and `slow`. A plain `pytest` runs only the fast
  tier.
- `mintkit/testing.py` with `FakeModel`. It mimics the parts of
  `SentenceTransformer` that are used: `.tokenizer.encode/decode`
  (whitespace tokenizer), `.max_seq_length`, and
  `.encode(texts, batch_size, normalize_embeddings, convert_to_numpy)`.
  Each text maps to a hash-seeded vector, so the output does not depend
  on the batch.
- The fake is registered under profile 1's dimension (384) **only inside
  tests**, by monkeypatching the registry. No fake profile id enters the
  spec.

*Done when:* `pytest` runs green in under 10 s with no network.

**WP0.3 Golden capture from the pre-refactor commit (S).**
- `tests/golden/make_golden.py --ref 0b52701`:
  - `git worktree add`s the old commit;
  - runs the **old** `build_card` (with `--schema` passed explicitly,
    because of bug 2, and `--card-issued-unix` fixed);
  - covers the fixtures: short txt, long txt (about 6k tokens, more than
    10 chunks), md, html, tex, `src/clawmarc_wadl.pdf` (480 KB), one png
    and one project zip;
  - mints for `--no-embed`, bge-small, mBERT and MPNet on CPU.
- The `--no-embed` and image cards are machine-independent and are
  committed under `tests/golden/`. Embedded goldens depend on the machine
  and device. They are regenerated into `tests/golden/local/`
  (git-ignored) on each machine, and model-marked tests compare against
  those.

*Done when:* goldens exist, and rerunning the script reproduces them byte
for byte.

## M0 — Producer fixes and phase split (`reference/`)

**WP0.4 Path fixes (S).**
- `sys.path.insert(0, str(Path(__file__).resolve().parent))` in both
  files.
- `DEFAULT_SCHEMA = .../reference/clawmarc_catalog_card.h`.
- The license id is checked in the CLI with a clear error ("≤ 8 ASCII
  bytes, e.g. CC-BY-SA").

*Done when:* the CLI runs without `--schema`, and the test card's schema
digest is `1dfaee46…`.

**WP0.5 Split `libangel_mint.document_embedding_f16le` (M).** New
functions, with the old one rebuilt as their composition:

```python
def load_embedding_model(model_name: str, device: str | None = None) -> "SentenceTransformer"   # cached per (name, device)
def body_tokens_for(model) -> int        # min(480, (model.max_seq_length or 512) - 2)   ← MPNet fix (bug 1)
def plan_chunks(text: str, model, max_body_tokens: int) -> ChunkPlan   # token ids → chunk_texts, token counts
def reduce_mean_tokw(chunk_vectors: np.ndarray, token_counts) -> np.ndarray   # exact current op order
def vector_to_f16le(vec) -> bytes
def embedding_policy_meta(model_name, plan, vec, emb, text) -> dict
def document_embedding_f16le(text, model_name, model=None) -> tuple[bytes, dict]   # same signature + optional model
```

- The `"pooling"` string is built from the chunk size used. When the
  size is 480, it is identical to today's string, so bge/mBERT sidecars
  don't change.
- Keep the `struct.pack("<e")` loop. Swapping it for `astype("<f2")` is
  allowed only after a test shows bit-identity on 10⁶ random float32
  values.

**WP0.6 Split `libangel_catalog.build_card` (M).**

```python
@dataclass
class Prepared:   # model-independent
    name: str; nbytes: int; object_sha256: bytes; mime: str
    arena_class: int; handler: str; classification_count: int
    machine_payload: bytes; source_or_manifest_sha256: bytes
    segments: TextSegments; full_text: str; body_text: str
    content_policy: dict; wants_vector: bool; preimage: str

def prepare_card(data: bytes, name: str, args, *, path: Path | None = None, mime: str | None = None) -> Prepared
def pack_and_sign(prep: Prepared, embedding: bytes, embedding_policy: dict, args, *, verify: bool = True) -> tuple[bytes, dict]
def build_card(args): ...   # read bytes → prepare_card → (document_embedding_f16le if wants_vector) → pack_and_sign
```

- `extract_text` takes `(data, path | None, mime)`:
  - text types decode `data` with `errors="replace"`, which is
    byte-equivalent to the current `path.read_text`;
  - tool-based types (pdf, epub, docx, doc, html) need a path. With
    bytes only, they write a `NamedTemporaryFile` with the right suffix.
- Dataset docs (P §0.4) get `mime="text/plain"`, `name="<dataset>/<doc_id>"`,
  and `data = text.encode("utf-8")`.

*Done when (M0 overall):*
- `--no-embed` goldens are byte-identical;
- bge/mBERT goldens are byte-identical (cards and sidecars) on the
  machine that made them;
- MPNet cards differ only in the arena vector and `chunking.*`, and their
  chunk size is 126;
- a dataset doc's `object_sha256` equals the sha256 of the same text
  written to a `.txt` file.

## M1 — Sources (`mintkit/sources/`)

**WP1.0 Package skeleton (S).** `mintkit/{__init__,__main__,_ref,cli}.py`.
`cli` uses argparse subcommands (no extra dependency), with every
subcommand stubbed. Includes the import-direction test (§3.1).

**WP1.1 `base.py`, `folder.py`, sampling (M).**
- `Doc`/`Query`/`Qrels` as in P §1.
- `Source` ABC, a registry, and `load_source(spec)`.
- Samplers: `all`, `first:N`, `random:N` (reservoir sampling, seed
  20260910), `qrels:Q+D`, `ids:FILE`.
  - Implement `qrels:Q+D` as two passes: (1) pick Q queries and their
    relevant ids; (2) stream the corpus, keeping those ids and
    reservoir-sampling D from the rest.
- `FolderSource`: recursive glob; `doc_id` is the POSIX relative path;
  bytes are read lazily; optional `queries.tsv` / `qrels.tsv`.
- Writing `queries.jsonl` / `qrels.tsv` into the run directory, restricted
  to the sampled docs.

*Done when:* fixture tests pass, and `random:N` is stable under the seed
and differs from `first:N`.

**WP1.2 `mldr.py` (M).**
- Local `data/mldr/mldr-v1.0-<lang>/` first, otherwise
  `hf_hub_download("Shitao/MLDR", ...)`, file by file, so `datasets` is
  not required.
- Modes: `corpus` (streams `corpus.jsonl.gz`) and `positives` (the
  corpus is the split's positive passages, as in experiment1).
- `describe()` returns the file names and sha256 values.

*Done when:* `mldr:en --sample random:10 --split dev --mode positives`
returns the 10 experiment1 ids (doc-en-12088, 15484, …). If the
experiment1 sampler differs, document the difference instead of chasing
it.

**WP1.3 `beir.py` (S)** on a tiny on-disk fixture. **WP1.4 `msmarco.py`
(S)** using `ir_datasets` (`msmarco-passage`, plus the `dev/small`,
`trec-dl-2019` and `trec-dl-2020` splits). The test is skipped if the
extra is not installed.

## M2 — Single-threaded end to end

**WP2.1 `store.py` (M).**
- Shard writer with a 4096 B stride, `index.tsv`, sidecars in
  `meta.jsonl.zst` (one frame per checkpoint, §3.6), and `SHA256SUMS` on
  close.
- `ShardReader` (mmap, `card(i)`, `vector(i)` at `+0x4c0`, iteration).
- `--layout files` writer.

**WP2.2 `manifest.py` (S).**
- Machine fingerprint: `/proc/cpuinfo` or `sysctl`, psutil, `torch.cuda`
  / `mps`, `nvidia-ml-py` when available.
- Software versions, git commit and dirty flag, `reference_sha256`.
- `run_id` = `<UTC>-<host_label slug>-<4 hex>`.
- The manifest is written with `status: running` and rewritten at the
  end.
- One line per run appended to `runs/INDEX.tsv`.

**WP2.3 `produce.py` + sequential `pipeline.run_serial()` (M).** Wires
source → prepare → embed (with `document_embedding_f16le` and a
preloaded model) → pack_and_sign → store. This serial path stays as the
reference implementation and as the `--threads 0` debug mode.

*Done when (M2):*
- `python -m mintkit mint mldr:en --sample random:10 --models bge mbert mpnet --device cpu`
  produces a run directory;
- `mintkit verify` passes on it;
- bge/mBERT cards are byte-identical to `build_card` on the same docs.

## M3 — Concurrency, batching, timing

**WP3.1 `pipeline.py` threaded stages (L).**
- Bounded queues, a reader that assigns `seq`, and a prepare thread pool
  (`ThreadPoolExecutor`).
- Reorder buffers before embed and before write (§3.2), and tombstones
  for failures.
- `failures.jsonl` and `--fail-fast`.
- Graceful Ctrl-C: drain, checkpoint, `status: partial`.
- `--resume` (§3.6).

**WP3.2 Batched embedder (M).**
- Window → length sort → batches of `--batch-chunks` → `model.encode` on
  decoded chunk texts (§3.4) → scatter → per-doc `reduce_mean_tokw` (the
  same function as WP0.5) → f16.
- CPU: `torch.set_num_threads(--torch-threads)`, defaulting to physical
  cores minus prepare workers.
- The sidecar gains an `embedding_batching` block.

**WP3.3 `timing.py` (M).**
- Stage timers: busy seconds and item counts, with `cuda.synchronize`
  before every timestamp that includes GPU work.
- Sampler thread (1 Hz): CPU %, RSS, GPU utilisation and memory, queue
  depths.
- Phases kept separate: model load (first vs cached), warm-up, steady
  state, flush.
- Per-card latency p50/p90/p99, and the bottleneck = the stage with the
  highest utilisation.
- Writes `timing.json` and prints the end-of-run table.

**WP3.4 Pack/sign process pool (S, conditional).** Built only if
WP3.3's numbers on `msmarco:passage --sample first:10000` show pack+sign
as the bottleneck (§3.5).

*Done when (M3):*
- for 200 MLDR docs, batched vs single-document cosine ≥ 0.9999, and the
  share of bit-identical f16 vectors is reported;
- two identical runs give byte-identical shards (§3.2);
- the kill-and-resume test passes: kill after 150 cards, resume, and the
  result equals an uninterrupted run;
- the bottleneck is named in the summary.

## M4 — CLI, bench, report, docs

**WP4.1 CLI polish (M).**
- `sources`, `inspect`, `verify [--c]` (builds `reference/c` with `make`
  if needed).
- `--config run.yaml` and replay from `manifest.json`.
- Progress bar (plain stderr line, no new dependency) and `--quiet`.

**WP4.2 `bench` + `report` (M).**
- Presets in `mintkit/bench_presets.yaml` (`mldr-200`, `msmarco-10k`,
  `folder-pdf`).
- One discarded warm-up run, then `--repeat 3` with median and spread.
- `--sweep`.
- Appends rows to `benchmarks/results.csv` with a fixed column schema
  that is versioned in the header.

**WP4.3 README and scripts (S).**
- `mintkit/README.md` per P §6, plus the determinism guarantee from
  §3.2.
- `scripts/mint_*.sh`, `scripts/bench_device.sh`.
- Root README link.
- Move the root `test_*.py` to `bench/legacy/` (§1).

*Done when (M4):* someone else (AK or Codex) can go from a fresh clone
to a `results.csv` row using the README alone.

## M5 — Benchmark runs (data, not code)

| Machine | Device rows | Who |
|---|---|---|
| VS 4060 Ti box | CUDA, CPU | VS (also commits `experiment1.py` and checks M2 against its old cards) |
| This laptop (Raptor Lake, 20 threads) | CPU | VS / Claude |
| AK's M2 | MPS, CPU | AK |

*Done when:* at least five rows are in `benchmarks/results.csv`. Bugs
found here go back into M3/M4 before M6 starts.

## M6 — Reductions (A §A)

- **WP6.1 (M)** `reductions/` registry and spec parser; canonical JSON
  plus `reduction_sha256`; the independent family (`mean_tokw`, `mean`,
  `head`, `max`, `ema`). `mean_tokw` calls `reduce_mean_tokw` from WP0.5,
  so there is one implementation and byte identity with M3 holds by
  construction.
- **WP6.2 (M)** Chunk-vector cache: a raw `chunks.f32` written by append,
  plus `chunks.shape.json`, converted to `.npy` on close (N is not known
  in advance). `mintkit reduce` mints new card sets from it without
  loading the model.
- **WP6.3 (S)** `ctxprefix` (a prepare-stage text transform).
- **WP6.4 (S)** Full-dimension store `vectors/`, `--card-dim` with
  truncation and renormalisation, and the `mrl` sidecar block.
- **WP6.5 (S)** bge-m3 and jina-v3 model entries, vectors only (§2).

*Done when:* per A §E (M6).

## M7 — Retrieval and evaluation (A §C)

- **WP7.1 (S)** `export`: `docs.f16.npy`, `docs.ordinal.tsv` and
  columnar header fields.
- **WP7.2 (M)** `retrieve/`: the `mmap` reference backend (block
  streaming, running top-k), `numpy`, `torch`.
- **WP7.3 (M)** `faiss-flat`, `faiss-ivf` and `faiss-hnsw` behind the
  extra.
- **WP7.4 (M)** `evaluate.py`: MRR@10, nDCG@10, R@10/100; agreement;
  BM25/TF-IDF baselines ported from `src/run_ir_experiments.py`;
  collapse check; `benchmarks/retrieval.csv`.
- **WP7.5 (S)** `--scale-to N` synthetic tiling.

Notes:

- **Ties and agreement.** FAISS has no ordinal tie-break, and its f32
  summation order differs from the other backends. For the agreement
  report, every exact backend's top-(k+16) candidates are **rescored by
  the reference scorer** and stably sorted on `(−score, ordinal)`. Only
  then are id lists compared. Raw backend scores are still reported for
  max |Δscore|.
- **Cold cache without sudo.** `os.posix_fadvise(fd, 0, 0,
  POSIX_FADV_DONTNEED)` evicts the shard's clean pages on Linux without
  root, which is better than A's "sudo or skip". macOS has no
  equivalent, so cold timings there are marked unavailable.

*Done when:* per A §E (M7).

## M8–M10 — sketched only; need the methods brief and M7 numbers

- **M8 joint/late chunking + segmenter + bottom-up hierarchy.** Needs raw
  `AutoModel` hidden states, not `SentenceTransformer.encode`. bge-m3 at
  8192 tokens is impractical on laptop CPU, so it is developed against
  the fake/bge-small model here and run on the 4060 Ti.
- **M9 step-synchronous scheduler, `kvcache` (Qwen3-0.6B), hierarchical
  chains.** The scheduler is tested first with `FakeModel` plus an EMA
  "conditioner", which makes step-batched vs one-document-at-a-time
  equality checkable exactly.
- **M10 projector training (`mintkit/train/`).** Its output is
  `models/<sha256>/`. Kill criterion per A: it beats EMA, or it is
  dropped.

# 5. Test tiers

| Tier | Runs | Contents | Where |
|---|---|---|---|
| fast (default) | `pytest` | FakeModel pipeline, sources on fixtures, store/resume, manifest, samplers, reorder/determinism, retrieval backends on random matrices | every machine, every PR |
| model | `pytest -m model` | goldens (WP0.3), batched-vs-single cosine, MPNet chunk-size fix | laptop CPU, about 2 GB of model downloads |
| gpu | `pytest -m gpu` | CUDA determinism, CPU-vs-CUDA cosine | 4060 Ti box |
| slow | `pytest -m slow` | 200-doc MLDR equivalence, 10k MS MARCO smoke | before M3/M5 sign-off |

There is no CI in the repo. Until there is, each PR description states
which tiers were run and on which machine.

# 6. Risks

| Risk | Mitigation |
|---|---|
| bge/mBERT golden byte-identity breaks for a benign reason (e.g. a sentence-transformers update changes `encode` batching) | goldens are pinned to the environment that made them, and `make_golden.py` records the versions. A mismatch prints a cosine report before failing |
| Batch padding pushes the cosine below 0.9999 for some models | fall back to `sort_window` = 1 doc for that model. Record it in the sidecar |
| MS MARCO download (about 1 GB, plus `ir_datasets` quirks) slows down M1/M4 | `msmarco-10k` bench preset reads only the first 10k lines. The source test skips without the extra |
| `pdftotext` / `pandoc` are missing on some machines | `mintkit sources` and `verify` report the missing tools. Prepare records a `failure` with stage `extract` instead of crashing |
| Scope creep from the addendum stalls M0–M5 | strict order: nothing from A starts until the M5 rows exist |

# 7. Next three PRs

1. **WP0.1 + WP0.2**: packaging, env script, `.gitignore` fix, pytest
   skeleton, FakeModel.
2. **WP0.3**: golden capture from `0b52701` (needs the `embed` extra and
   about 2 GB of model downloads on this laptop).
3. **WP0.4 + WP0.5 + WP0.6**: producer fixes and the phase split, merged
   only when the M0 criteria pass.

Separately, VS: commit `experiment1.py` (and the experiment1 results, if
they are small) from the 4060 Ti box once the `.gitignore` line is
fixed. Whoever holds `contextual-embedding-methods-brief.md`: please put
it on the Blackboard.
