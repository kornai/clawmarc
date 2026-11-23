---
from: Claude Opus 5.5 (Claude Code, VS Code), working with Vince Szigetvari (VS)
to: AK, GPT-5 Codex, Gemini
date: 2026-11-17
re: Plan — dataset loaders, multi-threaded card-minting pipeline, local card store, run manifests, benchmark timing
---

# Goal

Replace the one-off minting scripts (`experiments/experiment1.py`, root
`test_mint_*.py`) with one reusable tool that:

1. loads documents from a folder of files or from a benchmark (MLDR,
   MS MARCO, any BEIR-format set), together with the benchmark's queries
   and qrels;
2. mints cards with a multi-threaded, batched pipeline;
3. stores the cards locally in a layout that the query side can mmap;
4. writes a manifest for every run: what was minted, when, on which
   machine, with which code and settings, and optionally which documents;
5. reports timings that can be compared across machines (RTX 4060 Ti,
   CPU only, AK's M2);
6. comes with a README and short commands to run it.

The plan builds on `CLAUDE_mldr_experiment1_20261015.md` (batched
embedding design, producer bugs) and `CLAUDE_repo_queries_20261026.md`
(shard layout for querying).

# Where it lives

A new top-level package, **`mintkit/`**. `reference/` holds the format
implementation and `src/` holds the paper, so the pipeline should not live
in either. `mintkit` imports from `reference/`; nothing imports from
`mintkit` in the other direction. Runs are written to `runs/`
(git-ignored). Benchmark summaries go to `benchmarks/results.csv`, which
is committed so that numbers from different machines end up in one file.

```
mintkit/
  __init__.py
  __main__.py          # python -m mintkit ...
  cli.py               # subcommands: sources, mint, bench, report, inspect, verify
  sources/
    base.py            # Doc, Query, Qrels, Source, registry, sampling
    folder.py          # FolderSource
    mldr.py            # MLDRSource
    msmarco.py         # MSMarcoSource (passage, document)
    beir.py            # BEIRSource (corpus.jsonl / queries.jsonl / qrels/*.tsv)
  produce.py           # phase-split producer: prepare / embed / pack_sign
  pipeline.py          # threaded stages, queues, batching
  store.py             # shard writer, index, sidecars, resume
  manifest.py          # machine fingerprint, run manifest
  timing.py            # stage timers, resource sampler, summary
scripts/
  mint_folder.sh  mint_mldr.sh  mint_msmarco.sh  bench_device.sh
benchmarks/results.csv
tests/                 # pytest; root test_* benchmarks move to experiments/bench_*
```

# 0. Prerequisites in `reference/` (must be done first)

The pipeline uses the reference producer, so its known bugs have to be
fixed first, or every card it mints will have them.

1. **MPNet truncation fix**: chunk size `min(480, model.max_seq_length - 2)`
   (`libangel_mint.py:184`). The chunk size used goes into the sidecar
   (it already records `max_body_tokens_per_chunk`).
2. **`DEFAULT_SCHEMA` path fix** (`libangel_catalog.py:53`, and the
   `sys.path.insert` at L18).
3. **Split `build_card` into phases**, keeping the CLI behaviour unchanged:
   - `prepare_card(data: bytes, name: str, mime: str | None, args) -> Prepared`:
     hashing, extraction, classification, segments, policy clamp, and the
     embedding preimage. It takes **bytes**, not a path, so dataset
     documents do not have to be written to disk first.
   - `embed_prepared(...)`: done by the pipeline's batched embedder. The
     existing `document_embedding_f16le` stays as the single-document path
     and takes an optional preloaded `model`, so the model is not reloaded
     on every call (bug 4).
   - `pack_and_sign(prepared, embedding, embedding_policy) -> (card, meta)`.
   - `build_card(args)` becomes these three calls in sequence.
4. **Canonical bytes for dataset documents.** A dataset document has no
   file of its own, so its "object" is the UTF-8 encoding of its text,
   with MIME `text/plain`. `object_sha256` is the hash of those bytes, and
   it is the same value that writing the document to a `.txt` file would
   give (as experiment1 did). The title comes from the dataset title if
   one exists, otherwise from `"<dataset> <doc_id>"`.
5. **Equivalence tests**: for a handful of documents, compare
   `build_card` before and after the refactor byte for byte (bge and mBERT
   cards from experiment1 are the golden files; MPNet cards change because
   of fix 1, as intended).

# 1. Data sources

```python
@dataclass(frozen=True)
class Doc:
    doc_id: str
    text: str | None = None          # dataset docs
    path: Path | None = None         # folder docs (bytes read lazily in a worker)
    title: str | None = None
    meta: dict = field(default_factory=dict)

@dataclass(frozen=True)
class Query:
    qid: str
    text: str

Qrels = dict[str, dict[str, int]]    # qid -> doc_id -> relevance grade

class Source(ABC):
    name: str                        # "mldr:en", "msmarco:passage", "folder:/data/books"
    def iter_docs(self) -> Iterator[Doc]: ...            # streaming, never loads all into RAM
    def get_docs(self, ids: Iterable[str]) -> Iterator[Doc]: ...
    def splits(self) -> list[str]: ...                   # [] if the source has no queries
    def queries(self, split: str) -> list[Query]: ...
    def qrels(self, split: str) -> Qrels: ...
    def count(self) -> int | None: ...                   # for progress bars, if cheap
    def describe(self) -> dict: ...                      # goes into the manifest (version, files, sha256)
```

Sources are chosen with a short spec string, and `load_source(spec)`
resolves it through a registry:

| Spec | Class | Backend | Notes |
|---|---|---|---|
| `folder:PATH` | `FolderSource` | filesystem | recursive; `--glob '*.pdf'`; doc_id = relative path; queries/qrels from optional `queries.tsv` / `qrels.tsv` in the folder or passed with `--queries` / `--qrels` |
| `mldr:en` (`de`, `fr`, …) | `MLDRSource` | local `data/mldr/...jsonl.gz`, HF `Shitao/MLDR` when missing | corpus from `corpus.jsonl.gz`; queries/qrels from `train`/`dev`/`test`; `positives` mode (corpus = positive passages of the split) reproduces experiment1 without downloading the 1 GB corpus |
| `msmarco:passage` | `MSMarcoSource` | `ir_datasets` (optional dependency) | 8.8M passages, ~60 tokens each; splits `train`, `dev/small`, `trec-dl-2019`, `trec-dl-2020` |
| `msmarco:document` | `MSMarcoSource` | `ir_datasets` | 3.2M docs, long; title + body |
| `beir:PATH` or `beir:NAME` | `BEIRSource` | BEIR files on disk | covers SciFact, NFCorpus, TREC-COVID, … with no extra code |

`ir_datasets` is the only new dependency for the loaders, and it is
optional (installed with `pip install -e .[msmarco]`). It handles the
MS MARCO download, checksums and lookup of documents by id.

**Sampling** is separate from the source classes (`sources/base.py`), so
every source supports the same options:

- `all`, `first:N`
- `random:N` — reservoir sampling over the stream with a seed (default
  20260910). The first lines of the MLDR corpus are the dev/test documents,
  so taking the first N is not random.
- `qrels:Q[+D]` — Q queries from the split, all of their relevant
  documents, plus D random distractors. This is the collection design from
  the MLDR test plan; for example `qrels:100+900` gives 1000 documents.
- `ids:FILE` — an explicit list of doc_ids.

The chosen queries and qrels, restricted to the sampled documents, are
written into the run directory (`queries.jsonl`, `qrels.tsv`), so a later
evaluation needs only the run directory.

# 2. Pipeline

Per model, the documents pass through five stages connected by bounded
queues. The bounds keep memory flat and make the slowest stage visible.

```
source reader ─▶ prepare ×P ─▶ embed ×G ─▶ pack+sign ×S ─▶ writer ×1
 (1 thread)      (threads)     (1/device)   (threads or procs)  (1 thread)
```

| Stage | Work | Concurrency | GIL note |
|---|---|---|---|
| Reader | iterate the source, apply sampling, skip ids already done (resume) | 1 thread | I/O bound |
| Prepare | read bytes, extract text (`pdftotext`, `pandoc` subprocesses), segments, policy, preimage, tokenize, chunk | `--prep-workers` threads (default: cores / 2) | subprocesses and the HF fast tokenizer release the GIL, so threads work |
| Embed | cross-document batching: collect chunks from many docs into batches of `--batch-chunks` (default 64), sort a window of chunks by length to cut padding, `model.encode`, scatter results back; a doc is done when all its chunks are in → token-weighted mean, L2 normalise, f16le | one thread per device (`--devices cuda:0 cuda:1`, or `cpu`) | torch releases the GIL; on CPU set `--torch-threads` so it does not compete with the prepare workers |
| Pack+sign | `pack_and_sign`, then `verify_card` (on by default, `--no-verify` to skip) | `--sign-workers`, threads by default, `--sign-procs` for a process pool | packing is pure Python (~15 ms per card in experiment1), so a process pool may be needed once the embedder is fast; measure before deciding |
| Writer | append to the shard, write the index row and the sidecar line, checkpoint | 1 thread | serial, so the shard order is deterministic per run |

Design points:

- **Load each model once per run**, with a warm-up encode before timing
  starts. Models run one after another (`--models bge mbert mpnet`), so
  only one model is in GPU memory at a time. Extracted text is cached
  between models when it fits in `--text-cache-mb`, so PDFs are extracted
  only once.
- **Batching changes the floats slightly** (padding). Test: for 200
  MLDR documents, compare the batched vector with the single-document
  `document_embedding_f16le` result. Expect cosine ≥ 0.9999. Report the
  share of f16 vectors that are bit-identical. The sidecar records
  `"embedding_batching": {"batch_chunks": 64, "length_sorted": true}`.
- **Deterministic cards.** `card_issued_unix` is fixed once per run (run
  start, or `--issued-unix`). Card bytes then depend only on the input,
  the model and the batching settings, not on thread scheduling.
- **Failures do not stop the run.** A document that fails goes to
  `failures.jsonl` with the stage and the traceback. `--fail-fast`
  stops the run instead.
- **Resume.** The writer checkpoints `(shard, ordinal)` every
  `--checkpoint-every` cards (default 1000). `mintkit mint --resume RUN_DIR`
  skips doc_ids that are already in the index.
- **Short documents** (MS MARCO passages are 1 chunk) make embedding
  cheap, and pack/sign becomes the bottleneck. This is the case
  `--sign-procs` exists for, and the MS MARCO benchmark will show it.

# 3. Local card store

```
runs/<run_id>/                       # run_id = 20261117T142305Z-<host>-<4 hex>
  manifest.json                      # §4
  timing.json                        # §5
  queries.jsonl  qrels.tsv           # if the source has them
  docs.tsv                           # optional (--record-docs, on by default): doc_id, source checksum
  failures.jsonl
  cards/<model_alias>/
    shard-00000.cxcc                 # concatenated 4096 B cards, fixed stride
    shard-00000.index.tsv            # ordinal, doc_id, card_id, object_sha256, tokens, chunks
    shard-00000.meta.jsonl.zst       # one sidecar per line, same order
    SHA256SUMS
```

- Fixed 4096 B stride: card *i* starts at `i × 4096`. This is the layout
  the query note recommends: mmap the shard, read the vector at
  `+0x4c0`, and it can feed a packed f16 matrix or an ANN index later.
- A shard holds up to `--shard-size` cards (default 100k = 400 MB).
- `--layout files` writes one `.cxcc` + `.cxcc.json` per document instead,
  in the same form as the CLI and experiment1. Useful for small folders
  and for the existing tools (`libangel_inspect.py`, `cxcc-verify`).
- `mintkit verify RUN_DIR` rereads every card and checks the signature,
  the profile, the vector norm and `SHA256SUMS`. With `--c`, it also runs
  `reference/c/cxcc-verify` as an independent check.

# 4. Run manifest

`manifest.json` records what was minted, when, where and how:

```jsonc
{
  "schema": "mintkit-run-1",
  "run_id": "20261117T142305Z-vsz-4060ti-a3f9",
  "started_utc": "...", "finished_utc": "...", "status": "complete",  // or partial / failed
  "command": ["python", "-m", "mintkit", "mint", "..."],
  "machine": {
    "hostname": "...",                     // --anonymize-host stores a salted hash instead
    "os": "Linux 6.8.0-90-generic", "cpu": "model name from /proc/cpuinfo or sysctl",
    "cores_physical": 8, "cores_logical": 16, "ram_gb": 31,
    "gpus": [{"name": "RTX 4060 Ti", "vram_gb": 16, "driver": "580.95", "cuda": "12.8"}],
    "mps": false, "torch_threads": 8
  },
  "software": {"python": "3.12.3", "torch": "2.11.0+cu128", "sentence_transformers": "6.1.0",
               "transformers": "5.19.0", "cryptography": "50.0.2",
               "git_commit": "ccf1a1b", "git_dirty": false,
               "reference_sha256": {"libangel_catalog.py": "...", "libangel_mint.py": "...",
                                    "clawmarc_catalog_card.h": "1dfaee46..."}},
  "source": {"spec": "mldr:en", "describe": {...}, "sampling": "qrels:100+900", "seed": 20260910,
             "split": "train", "doc_count": 1000, "docs_file": "docs.tsv"},
  "config": {"models": [...], "devices": [...], "batch_chunks": 64, "prep_workers": 4,
             "sign_workers": 4, "content_policy": "public_library_science", "issued_unix": ...},
  "outputs": {"bge": {"profile": 1, "cards": 1000, "failed": 0,
                      "shards": [{"path": "...", "sha256": "...", "cards": 1000}]}}
}
```

- The manifest is written at the start with `status: "running"` and
  rewritten at the end, so a run that crashes can still be identified.
- `docs.tsv` is the optional list of which documents were minted
  (`--no-record-docs` turns it off). The doc_ids are also in the shard
  indexes, so this file matters mainly for runs where cards failed or
  were skipped.
- `runs/INDEX.tsv` gets one line per run (run_id, date, host, source,
  models, card count, status), so `mintkit report` can list past runs.
- Optional, later: mint a card for the manifest itself (it is a JSON
  document, so the Text class applies). That matches what the repo does
  for its own releases.

# 5. Timing and benchmarking

Each stage records busy time and item counts. A sampler thread records
resource use every second.

- **Phases, kept separate**: source load and sampling, model load (first
  load including download, reported separately), warm-up, steady-state
  minting, final flush. CUDA is synchronised before every timestamp that
  includes GPU work.
- **Per stage**: busy seconds, items, items/s, and utilisation
  (busy / wall time). The stage with the highest utilisation is the
  bottleneck, and the summary names it.
- **Per card**: latency from reader to writer, reported as p50/p90/p99.
- **Throughput**: cards/s, tokens/s, chunks/s, and MB of source text per
  second. Steady state only, so warm-up and the tail do not skew it.
- **Resources** (sampled every second): CPU % and RSS (`psutil`, already
  installed); GPU utilisation and memory through `nvidia-ml-py` (optional);
  `torch.cuda.max_memory_allocated`; queue depths. A queue that stays full
  sits in front of the bottleneck.
- **Output**: `timing.json` (all of the above plus the raw samples), and a
  table printed at the end:

```
model  prof  device  load s  cards  cards/s  tok/s    p50 s  p99 s  bottleneck
bge    1     cuda:0  1.8     1000   41.2     612,000  0.21   0.55   pack+sign (0.93)
```

**Comparing devices.** `mintkit bench` runs fixed presets, so every
machine mints exactly the same documents:

| Preset | Documents | What it tests |
|---|---|---|
| `mldr-200` | 200 MLDR en dev positives, seed 20260910 (local files, no download) | long documents, embedding-bound |
| `msmarco-10k` | first 10,000 MS MARCO passages | short documents, pack/sign-bound |
| `folder-pdf` | user folder of PDFs | extraction-bound |

`bench` runs the preset `--repeat 3` times (default) after one discarded
warm-up run, reports the median and the spread, and appends one row per
model to `benchmarks/results.csv` (date, host label, CPU, GPU, device,
versions, preset, settings, cards/s, tok/s, p50/p99, bottleneck).
`mintkit report benchmarks/results.csv` prints it as a comparison table.
`--sweep batch_chunks=16,32,64,128 prep_workers=2,4,8` tries each setting
to find the best one for a machine.

# 6. CLI, scripts and README

```bash
python -m mintkit sources                                   # list registered sources and local availability
python -m mintkit mint folder:~/books --glob '*.pdf' --models mbert
python -m mintkit mint mldr:en --sample qrels:100+900 --split train --models bge mbert mpnet --device cuda
python -m mintkit mint msmarco:passage --sample random:100000 --models bge --sign-procs 6
python -m mintkit mint --resume runs/20261117T142305Z-...
python -m mintkit bench mldr-200 --device cpu
python -m mintkit report runs/ | benchmarks/results.csv
python -m mintkit inspect runs/<id> [--card 17]
python -m mintkit verify runs/<id> [--c]
```

- Every option can also be given in a YAML file (`--config run.yaml`).
  The resolved config is stored in the manifest, so any run can be
  repeated with `--config runs/<id>/manifest.json`.
- `scripts/*.sh` are short wrappers that activate `myenv` and run one
  typical command each. `scripts/bench_device.sh` runs the whole
  benchmark suite on a new machine in one command.
- A progress bar shows documents/s and the bottleneck stage; `--quiet`
  turns it off.
- **README** (`mintkit/README.md`, linked from the root README): what it
  does in 5 lines; install (`pip install -e .[gpu,msmarco]`, the system
  tools for PDF/EPUB extraction); a quickstart for each source; the
  run-directory layout; how to read `timing.json`; how to benchmark a new
  machine and add its row; how to add a new source (one subclass and one
  registry line); known limitations (no OCR; signing key forgeable by
  design).

# 7. Order of work

| Step | Content | Done when |
|---|---|---|
| M0 | §0 producer fixes and phase split | equivalence tests pass; experiment1 bge/mBERT cards byte-identical |
| M1 | `sources/` + sampling + tests (folder, MLDR, BEIR; MS MARCO behind optional dep) | each source yields docs, queries and qrels on a small fixture |
| M2 | single-threaded pipeline + store + manifest | `mintkit mint mldr:en --sample random:10` reproduces experiment1 (with the MPNet fix) |
| M3 | threads, batched embedder, timing | batched-vs-single cosine test passes; throughput reported; bottleneck named |
| M4 | CLI polish, scripts, README, `bench` / `report` | a new user can mint and benchmark from the README alone |
| M5 | benchmarks: 4060 Ti CUDA, same box CPU, AK's M2 (MPS and CPU) | four machine/device rows in `benchmarks/results.csv` |

After M5, the MLDR 1000-document / 100-query evaluation from the
2026-10-12 plan can run directly on a `qrels:100+900` run directory.
Retrieval and evaluation themselves are out of scope for this plan.

**Update 2026-11-23:** pluggable reductions, conditional (sequential and
hierarchical) chunk embedders, and retrieval/evaluation across several
backends (mmap, numpy, torch, FAISS flat/IVF/HNSW) are now planned in
`CLAUDE_minting_pipeline_addendum_20261123.md` (milestones M6–M10). That
note replaces the line above and the single-reduction embed stage in §2.

# Open questions for VS / AK

1. Package name and place: `mintkit/` at the top level, or under `reference/`?
2. Default store layout: shards (scales, needed for MS MARCO) or per-file
   cards (compatible with existing tools)? The plan proposes shards by
   default and `--layout files` as an option.
3. MS MARCO: passage, document, or both? Passage is the standard benchmark
   and the cheaper download; document is closer to the long-text cards the
   paper describes.
4. Should `benchmarks/results.csv` store hostnames, or only a hardware
   label such as "RTX 4060 Ti / Ryzen 8c"?
5. Is multi-GPU needed now, or is one embedder per process enough for the
   machines we have?
