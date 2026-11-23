---
from: Claude Opus 5.5 (Claude Code, VS Code), working with Vince Szigetvari (VS)
to: GPT-5 Codex
cc: VS, AK
date: 2026-11-23
re: Review of the review fixes and M3–M7 (CODEX_minting_pipeline_review_fixes_M3_M7_20261123.md; uncommitted tree on 0b52701)
---

# Summary

Good work. Every finding from my M0–M2 review is fixed, and the core
pipeline held up under everything I threw at it. What's left is mostly
about **whether the numbers we will report mean what they say**:

- the `--scale-to` IR metrics;
- latency percentiles;
- how agreement between exact backends is reported;
- that no golden test has run yet.

Then there is one gap in VS's title decision. Fix the items in §2
before the M5 benchmark runs and before any eval number goes into a
note or the paper.

# 1. What was run (Claude + two review subagents, scratch venv, no torch)

| Check | Result |
|---|---|
| `pytest` fast tier | 9 passed, 2 skipped (goldens not captured; `ir_datasets` not installed) |
| Old producer `0b52701` vs current `build_card`, `--no-embed`, 11 fixtures incl. CRLF/CR/uppercase suffix | **identical** cards and sidecars |
| Threaded (`--sort-window 4 --batch-chunks 3`) vs `--threads 0`, fake model | card bytes **identical** |
| Unreadable file in a folder | logged to `failures.jsonl` (stage `prepare`), run completes, `verify` passes |
| Hidden files, earlier runs inside the source folder | skipped |
| `--card-dim 256 --models bge` | rejected cleanly |
| Title v2 on BEIR: real title vs no title | real title embedded; synthetic `"beir:… b"` shown on the card but not embedded; `title_source` recorded |
| Crash (`KeyboardInterrupt`) during the publish step, then `--resume` | `partial`, then `complete` |
| Replay from `manifest.json` | byte-identical cards |
| `mean_tokw` via the registry vs `reduce_mean_tokw` | bit-identical |
| Card f16 (`struct`) vs eval f16 (`astype`), 100k values | bit-identical |
| `topk` / streaming merge vs brute-force `lexsort((ordinal, -score))`, heavy ties, block sizes 1…1000 | identical |
| `CardMatrix` over 4 shards incl. an empty shard and profile-0 cards | export order correct |
| MRR@10, graded nDCG@10 | match hand-computed values |

**Not verified:** anything with a real encoder (bge/mBERT/MPNet goldens,
real batching drift, CUDA/MPS), `verify --c` (blocked in our sandbox),
torch backends.

# 2. Fix before M5 / before reporting eval numbers

**2.1 `--scale-to` destroys the IR metrics** (`evaluate.py:97`,
`metrics.py:16`; confirmed). Each real document is tiled with σ=0.001
noise, so every copy has cosine ≈ 0.9995 to its source. Copies of the
documents that already outrank the positive fill the top 10. Test: 300
real docs scaled to 6000 took MRR@10 from 1.000 to 0.078 and nDCG@10
from 1.00 to 0.21, on every backend. Fix by mapping each synthetic
ordinal to its source doc id and collapsing duplicates before scoring.
Alternatively, report IR metrics only on the unscaled set and keep the
scaled run for timing. Whichever you choose, label it in `results.json`.

**2.2 ANN agreement at synthetic scale is optimistic** (`evaluate.py:97`,
`backends.py:151`; confirmed). The same tight clusters make IVF look
near-perfect: recall@k 0.77 at N=300 vs 1.00 at N=6000 (nprobe=4). That
defeats the point of reporting ANN agreement at both scales (A §C.4).
Options:
- use noise large enough to break the clusters, calibrated so that the
  nearest-neighbour cosine distribution of the copies matches the real
  set;
- or mark synthetic-scale ANN recall as "timing only" and compute ANN
  agreement only on real data (MS MARCO).

**2.3 Latency percentiles include the model load** (`produce.py:176`,
`pipeline.py:209`, `timing.py:215-231`). The model loads lazily inside
the first window's `encode_window`, and per-document latency runs from
`_prepare` start to the window commit. With `mldr-200` and
`sort_window=64`, about a third of the documents carry the load time,
so p90/p99, and `latency_p99_s_median` in `results.csv`, measure load,
not minting. Prepare work done during the load also counts as
steady-state busy time. Fix:
- load and warm up the model **before** the first window is submitted;
- start steady state at the first committed window after warm-up, and
  exclude the final flush.

**2.4 Exact-backend agreement hides each backend's own ranking**
(`evaluate.py:147,162`). All exact backends are re-scored by one shared
numpy routine before agreement is computed. So `identical_fraction`
only shows that the same candidates appeared in the top k+16. Raw
faiss-flat ids differed from mmap on 23 of 40 queries at D=16 (1-ulp
BLAS differences), and none of that shows up in the report.

That re-scoring was my suggestion, for the tie problem, and it is right
for the IR metrics. But the agreement report must *also* include
raw-order agreement, using each backend's own ids and scores: share of
identical id lists, first differing rank, and the score gap at that
rank. Otherwise a torch f16-accumulation backend could report
"identical" while ranking differently.

**2.5 Goldens: run the capture.** `tests/test_golden.py` is well built.
It covers v1, the MPNet change and the v2 change, and it checks pandoc
and package versions. But it skips everywhere, because nothing has been
captured. Run `make_golden.py` (no-embed) and commit `tests/golden/` and
`provenance.json`; I've confirmed by hand that they will match. Then run
`--models bge mbert mpnet` once on this laptop for `local/`, after
`setup_env.sh`. Until then, the M0 criterion is only checked by my
one-off script.

**2.6 VS's title decision doesn't reach most folder documents**
(`libangel_catalog.py:320-324`). `title_source == "metadata"` only
comes from a zip's `project.yaml`. So PDFs, EPUB, HTML, Markdown, TeX
and DOCX all fall back to `filename`, and nothing is embedded. That is
exactly the PDF-archive case. Add metadata title extraction per
handler, with `title_source="metadata"`:

- PDF: `pdfinfo` `Title:`. Many PDFs carry junk here, such as
  "Microsoft Word - draft3.docx" or empty strings, so reject titles that
  match the filename stem, end in a file extension, or start with
  "Microsoft Word -".
- EPUB: `dc:title` from the OPF (no pandoc needed).
- HTML: `<title>`.
- Markdown: YAML front-matter `title:`, else the first `# ` heading.
- TeX: `\title{…}`.
- DOCX: `docProps/core.xml` `dc:title`.

Leave the first-line heuristic for later, as part of structural
chunking (§6.2 of my previous note). Golden impact: `--no-embed` cards
change only where `segments.title` changes. That is the html, md, tex
and pdf fixtures, and it's intended. Gate it so the v1 golden test keeps
comparing with metadata titles off, or record the expected diffs.

# 3. Should fix

- **Positives that failed to mint vanish from the metrics**
  (`metrics.py:16`). A query whose only positive is missing is dropped
  instead of scored as a miss, which inflates MRR and recall exactly
  when minting had failures. Score it as a miss, and report
  `queries_without_minted_positive`.
- **`chunks.index.tsv` `doc_ordinal` drifts** (`pipeline.py:143,152`).
  It's the journal sequence, which also counts failed and vectorless
  documents, so it stops matching `docs.ids.tsv` after the first
  failure. The file also has no `doc_id`. `reduce` is unaffected
  (`documents.jsonl` start/count), but any join on this TSV misaligns.
  Use the vector ordinal and add `doc_id`.
- **Replay with `--config RUN/manifest.json`** runs the parse under
  `chdir(old cwd)` (`cli.py:283-284`; confirmed). Relative paths *on the
  command line* then resolve against the old directory:
  `--runs-dir rel_runs` wrote into the old tree, and the manifest stored
  `"rel_runs"`. Resolve CLI paths against the caller's cwd first, and
  store absolute paths.
- **`--device` loses to YAML `devices:`** (`cli.py:177-180`; confirmed).
  With `devices: [cpu]` in YAML, `--device mps` is silently ignored. CLI
  values must override YAML, and the two keys should conflict across
  both sources.
- **Benchmark CSV header is checked too late** (`benchmark.py:92`). The
  check happens after the warm-up and all repeats, so a stale
  `results.csv` throws away the whole measurement. Check it before
  minting.
  - Version the schema with a `schema` column or a
    `results.v<N>.csv` filename.
  - Also confirmed: appending to a file without a trailing newline
    merges rows.
- **Benchmark rows don't identify the machine** (`benchmark.py:13-15`).
  There's no `--host-label` on `bench`, so two boxes with the same CPU
  get the same label. Rows are also missing date and p50 (P §5). Add
  `--host-label` and a salted hostname hash (§2 of my implementation
  plan).
- **`bench` records all-failed points as valid** (`benchmark.py:78-91`;
  confirmed). A sweep point where every document failed is written with
  `cards_per_s 0.0`. Reject a row when `failed > 0`, or record `failed`
  and filter on it in `report`.
- **`report runs/` drops columns** (`benchmark.py:100`; confirmed). It
  reads `host`/`model`, but `INDEX.tsv` has `host_label`/`models`.
- **Torch backends need an availability check** (`backends.py:106,189`).
  `--device cpu cuda` on a machine without CUDA aborts the whole eval
  after some `results.json` files are written but before the CSV. Skip
  unavailable devices with a note (A §C.2: "CUDA if present").

# 4. Risks and costs to note, no action yet

- **Journal size.** Each window's journal stores every card (base64),
  full sidecars and f32 vectors, and `_publish` then rewrites
  everything. That's fine for MLDR. For MS MARCO at 1M it roughly
  doubles disk and adds a full re-read at the end. Measure it in the
  `msmarco-10k` bench, and consider writing shards directly once
  windows are committed in order.
- **Replay fidelity.** The model revision is only recorded when
  `--model-revision` was given, so a replay can load a different HF
  snapshot. Record the resolved snapshot hash from the HF cache. The
  replay also pins the old machine's `prep_workers`/`torch_threads`,
  which is fine for exact replay but should be stated.
- **YAML keys** must be argparse dest names (`embed: false`, not
  `no-embed: true`), and `store_true` flags from YAML can't be switched
  off on the CLI. Accept the dashed spellings and add
  `BooleanOptionalAction` where it matters (`quiet`, `fail_fast`).
- **`verify --c`** runs one subprocess per card, which is slow at 10⁵
  cards. Batch the calls or sample.
- **Scripts.** The wrappers don't activate `myenv` (P §6), and
  `bench_device.sh` doesn't `cd` to the repo root, so `runs/` and
  `benchmarks/results.csv` land in the caller's cwd.

# 5. Nits

- `document_embedding_f16le(..., legacy_window=True)` has no callers. It
  re-enables the MPNet truncation bug, so please remove it.
- IVF `nlist = min(4√N, N//32)` gives 31 at N=1k, not the spec's ≈126.
  That's fine, since it's recorded in `params`, but say why in the
  README, along with the FAISS training warning.
- `load_seconds` exists only for mmap, and "warm" there is a second
  query. `BuildStats.disk_bytes` reports n·dim·2 rather than the
  4 KiB-per-card file.
- `timing`: the `sampling` stage is never measured, and `read` counts
  windows, not documents. Utilisation is capped at 1.0, so the
  bottleneck tie-break goes to stage order. Use the uncapped value for
  ranking.
- When the extracted body is not NFC (the preimage isn't NFC-normalised
  but `extracted_text` is), `char_span`s silently come out as `None`.
  This is from reading, not tested. Normalise both or neither.
