---
from: Claude Opus 5.5 (Claude Code, VS Code), working with Vince Szigetvari (VS)
to: GPT-5 Codex
cc: VS, AK, Gemini
date: 2026-11-24
re: mintkit minting speed: measurements on the 4060 Ti and five changes to reach millions of documents in hours (mintkit v0, 1ad98cd)
updated: 2026-11-25. Implemented by Claude, not Codex (see §0)
---

# 0. Update 2026-11-25: implemented by Claude instead of Codex

This note was addressed to Codex. On 2026-11-25, VS asked Claude
(Opus 5.5, Claude Code) to implement it directly instead. **Codex: no
need to act on §2 and §4. A review of the branch is welcome.**

The work is on branch `mintkit-speedup` (from `vincesz-fred`). It was
not committed at the time of writing. All measurements below are from
VS's box (RTX 4060 Ti, i7-4790K).

## 0.1 What changed

| Step | Status | Where |
|---|---|---|
| S1 GPU default device; `torch_threads` = all physical cores | done | `cli.py` (`models.default_device`) |
| S2 `--precision {auto,fp32,fp16,bf16}`; precision in sidecar policy and manifest | done | `models.py`, `produce.py`, `cli.py` |
| S3 token ids fed directly (`--direct-ids`, the default); planning of window N+1 overlapped with the GPU work on window N | done | `produce.py` (`DirectEncoder`, `plan_window` / `embed_window`), `pipeline.py` |
| S4 `--sign-procs N` (process pool, signing of window N overlapped with embedding of N+1) | done | `pipeline.py` |
| extra: `--prep-procs N`: prepare and tokenize in processes (see 0.3) | done, opt-in | `pipeline.py` |
| S5 `bench mldr-200` on the 4060 Ti | done | `benchmarks/results.csv` |
| S5 `msmarco-10k`, CPU and AK's M2 bench | **not run** | |

Details:

- **Precision.** `auto` means fp16 on CUDA for models with
  `half_safe=True` (bge, MPNet), and fp32 everywhere else.
  `policy.precision` and `policy.encoder_inputs` are added to each
  sidecar, and `config.precisions` to the manifest. Resume and
  `--config` replay refuse to run if the precision differs. A v0
  manifest counts as fp32, and its replay uses `--no-direct-ids`.
- **Direct ids.** The pipeline calls `model(features)`, so the model's
  own Transformer, Pooling and Normalize modules run, followed by an
  fp32 L2 normalize, which is what `encode(normalize_embeddings=True)`
  does. Special tokens are taken from the tokenizer's own template.
  `plan_chunks` stays unchanged in `reference/`. A recording proxy keeps
  the ids it computes, and on the direct path it skips decoding chunk
  text (decoding was about 20% of planning time). ctxprefix still
  decodes, because `chunk_inputs_sha256` hashes the text.
- **Tests.** `tests/test_mintkit_speedup.py` adds:
  - precision resolution,
  - replay rejecting a precision mismatch,
  - `--sign-procs` cards byte-identical to in-process signing,
  - `--prep-procs` cards and chunk caches byte-identical to threads.

  `tests/test_mintkit_pipeline.py` now passes `--no-direct-ids`
  because its fake model is not a torch module. 13 passed, 2 skipped.
- **Acceptance script.** `scripts/mintkit_speedup_check.py` re-runs every
  comparison below.

## 0.2 Acceptance results (200 MLDR en dev positives)

**fp16 vs fp32 (direct path).** The document-level test passes for all
three models:

| | doc cosine min | chunk cosine min | chunks < 0.999 |
|---|---|---|---|
| bge fp16 | 0.9999999 | 0.999999 | 0 |
| MPNet fp16 | 0.9999999 | 0.999998 | 0 |
| mBERT fp16 | 0.999998 | 0.99925 | 0 |
| mBERT bf16 | 0.99976 | **0.9385** | 6 |

- Bit-identical f16 card vectors, fp16 vs fp32: 0/200 for every model.
  Cards differ, as expected.
- bf16 is *worse* than fp16 for mBERT. The 0.931 fp16 outlier in §1.2
  did not reproduce through the direct path. It was measured through
  `encode`, on re-tokenized text, and remains unexplained.
- mBERT therefore stays fp32 under `auto`, as §2.1 asked.
  `--precision fp16` is available, and **VS decides** whether to
  switch it on by default (the s/doc table below shows the effect).

**Direct ids vs `encode`.** The criterion as written in §2.2 (document
cosine ≥ 0.99999) **fails**, and the cause is the caveat in §2.2. Many
chunks do not round-trip through decode and re-tokenize to the same
ids, so v0 often embedded tokens different from the ones its sidecar
counted:

| | chunks | re-tokenized differently | doc cosine min (direct vs encode) |
|---|---|---|---|
| bge | 3,270 | 323 (10%) | 0.9958 |
| MPNet | 13,779 | 4,728 (34%) | 0.9990 |
| mBERT | 3,441 | 1,799 (52%) | 0.9800 |

On the chunks whose ids do round-trip, direct and `encode` agree to a
cosine of ≥ 0.9999997 for all three models. Chunk counts and token
counts in the sidecar are identical between the two paths. **The direct
path is exact. The difference is v0's decode/re-encode step, so v0 and
new cards are not comparable vector-for-vector.**

**Speed** (`bench mldr-200`, 3 repeats, median, default settings,
including pipeline fill on only 200 documents):

| | v0 s/doc | now s/doc | tok/s |
|---|---|---|---|
| bge (fp16) | 0.110 | **0.033** | 237k |
| MPNet (fp16) | 0.244 | **0.084** | 103k |
| mBERT (fp32) | 0.224 | 0.182 | 44k |
| mBERT (`--precision fp16`, from the check script) | | 0.067 | |

## 0.3 What limits speed now: the CPU, not the GPU

After fp16 and direct ids, bge encodes about 370–400k tok/s. Planning
then costs about as much as the GPU work: roughly 35 ms of CPU per MLDR
document, most of it Python in `plan_chunks` and the tokenizer call.
This box has only 4 cores, and with threads the GIL serializes that
work. Embed busy time also grows (25.9 s vs 17.2 s per 1,000 documents)
because the main thread waits on the GIL.

`--prep-procs N` moves prepare and planning into worker processes. The
parent's tokenizer is pickled once per worker. On 1,000 MLDR corpus
documents (~7.6k tokens each), bge fp16:

| settings | s/doc | embed busy share |
|---|---|---|
| threads (default) | 0.031 | 0.85* |
| `--prep-procs 3` | 0.026 | 0.67 |
| `--prep-procs 2 --sign-procs 1` | **0.023** | 0.76 |

\* Inflated: GIL waits are counted as embed time.

Worker startup takes about 3 s. That cancels the gain on 200-document
runs, so the flag is opt-in. For the 2M-document target: **bge at about
0.020–0.023 s/doc is about 11–13 h on this box.** §2.2's target of
≤ 0.02 is essentially reached at scale. A machine with more cores would
let the GPU reach its ceiling of about 0.017.

**Short documents** (synthetic folder, 10k × ~143 tokens, bge): about
300 docs/s, so 2M documents take about 1.9 h. Signing is not the limit:
it is 22% busy in-process and 12% with `--sign-procs 2`, against embed
at 15%, and cards are byte-identical. The limit is per-file preparation
in the folder source (90% busy).

## 0.4 Open for VS / AK

1. ~~Should mBERT use fp16 under `auto`?~~ **Decided by VS
   (2026-11-25): mBERT stays fp32 under `auto` for now.**
   `--precision fp16` remains available, and bf16 should not be used.
2. Direct-ids cards differ from v0 cards (0.2). Runs minted before this
   change should not be mixed with new runs in one comparison.
3. **Deferred by VS (2026-11-25):** the options in §3 are recorded but
   not pursued now. For long documents in "a few hours" on one 4060 Ti,
   one of them would still be needed:
   - cap the tokens embedded per document (a new reduction spec);
   - a smaller or faster model per profile;
   - one embedder per GPU across more GPUs;
   - ONNX Runtime / TensorRT;
   - a machine with more CPU cores, which would also lift the CPU limit
     described in 0.3.
4. Still to run: `bench msmarco-10k`, and the CPU and M2 rows.

# Summary

VS wants to mint a few million documents in hours, not days. mintkit v0
already matches experiment1 on the GPU (bge-small 0.11 s/doc against
0.13), but that is still about 61 hours for 2M MLDR-length documents.

The encoder can go much faster than mintkit currently drives it. With
fp16, and with token ids passed straight to the model, bge-small on the
4060 Ti reaches about 450k tokens/s, which is 0.017 s/doc on MLDR. That
brings 2M long documents down to about 9 hours with one model on one
GPU.

The limit is **tokens**, not documents. Long documents (MLDR averages
~7,600 tokens) cost about 9 GPU-hours per 2M documents even at the
ceiling. Short documents (≤ 500 tokens) take under an hour of GPU time,
and then card packing and signing become the bottleneck.

Proposed work, in order of payoff: **fp16 on CUDA** (2.5–3×), **token
ids straight to the model, with tokenizing overlapped with the GPU**
(about 1.7× more), **signing in a process pool** (for short documents),
**GPU as the default device**, and **better CPU thread defaults**. Details
and acceptance tests follow.

# 1. Measurements

Machine: VS's box, RTX 4060 Ti 16 GB, i7-4790K (4 cores), torch
2.11.0+cu128. Data: the 200 MLDR en dev positives (`mldr:en --mode
positives --split dev`), about 1.5M tokens in total.

## 1.1 mintkit v0 as it is

`mintkit mint ... --device cuda`, default settings, one model per run:

| model | s/doc | tok/s | embed busy | chunk (tokenize) busy | wall (incl. load) |
|---|---|---|---|---|---|
| bge-small | 0.110 | 69k | 16.7 s | 7.6 s | 28 s |
| mBERT | 0.224 | 36k | 37.5 s | 9.5 s | 51 s |
| MPNet | 0.244 | 35k | 37.0 s | 18.6 s | 57 s |

experiment1 on the same box: bge 0.134, mBERT 0.245, MPNet 0.107 s/doc.
MPNet looked fast there only because of the truncation bug: it read 128
tokens of each 480-token chunk. With the M0 fix it reads every token in
126-token chunks, about 4× as many chunks.

## 1.2 Encoder ceiling on the same chunks

Script: a standalone benchmark (not in the repo) that chunks the same
200 documents the way mintkit does, then times only the encoder:

| path | bge-small tok/s | mBERT tok/s | MPNet tok/s |
|---|---|---|---|
| `SentenceTransformer.encode`, fp32, batch 64 | 107k | 45k | 48k |
| same, fp16 (`model.half()`) | 263k | 135k | 146k |
| fp16, token ids fed directly, length-sorted, batch 256 | **449k** | **168k** | **171k** |

- Batch size 64 vs 256 made no difference.
- fp16 vs fp32 chunk vectors: cosine min 0.99956 (bge) and 0.99958
  (MPNet). mBERT has a mean of 0.99996 but **a minimum of 0.931**, so at
  least one chunk diverges badly in fp16 (likely overflow in a layer).
- The "token ids fed directly" row used my own pooling code (CLS for
  bge, mean for the others). **It has not been checked against
  `encode`**, so treat that row as an upper bound until the test in §2.2
  passes.

## 1.3 Time for 2M documents (one model, one 4060 Ti)

| | bge-small | mBERT / MPNet |
|---|---|---|
| MLDR-length (~7.6k tokens), mintkit v0 | ~61 h | ~125 h |
| MLDR-length, fp16 | ~16 h | ~33 h |
| MLDR-length, fp16 + direct ids + overlap | **~9 h** | ~27 h |
| ~500-token docs, fp16 + direct ids | ~40 min GPU | ~2 h GPU |
| any length: pack + sign, 1 thread (~2 ms/card) | ~67 min | ~67 min |

On a 4060 Ti, "a couple million long documents in a few hours" is not
possible with the base-size models. Section 3 lists the remaining
options.

# 2. Proposed changes

## 2.1 fp16 on CUDA (largest win: 2.5–3×)

- New option `--precision {fp32,fp16,bf16}`. The default is `fp16` on
  CUDA for models marked safe, and `fp32` everywhere else. Apply it after
  loading in `ModelSpec.load` ([models.py](../mintkit/models.py)).
- Add `"precision"` to the sidecar `embedding` policy and the manifest
  `config`. fp16 cards are **not** byte-identical to fp32 cards, so
  resume and `--config` replay must treat precision like the model and
  device: a mismatch is an error.
- mBERT stays fp32 until its outlier is explained. Try bf16 first.
- **Accept when:** on the 200 MLDR dev documents, document vectors at
  fp16 vs fp32 have cosine ≥ 0.9995 for every document, for each model
  allowed to use fp16; and the share of bit-identical f16 card vectors
  is reported.

## 2.2 Token ids straight to the model, with tokenizing overlapped (about 1.7× for bge)

At present, in [produce.py](../mintkit/produce.py) `encode_window`, each
window is planned (tokenized), then every chunk is **decoded back to
text**, and then `model.encode` tokenizes it again. The GPU idles while
the window is being planned.

- `plan_chunks` already has the token ids. Keep them in `Chunk` and
  build `input_ids` / `attention_mask` batches directly: special tokens
  plus padding, length-sorted as now.
- Call the transformer module and then the model's own pooling and
  Normalize modules (`model[1:]`), so pooling stays exactly what the
  sentence-transformers config says. Don't hand-write CLS or mean
  pooling as the benchmark did.
- Run planning for window N+1 in the prepare pool while window N is on
  the GPU, so `chunk` busy time is hidden behind `embed`. Pin host
  memory and use `non_blocking` copies.
- **Accept when:** for the 200 documents, the direct-ids vectors equal
  the `encode` path's vectors at the same precision (cosine ≥ 0.99999,
  and identical chunk counts and token counts in the sidecar). In
  `timing.json`, `embed` busy time is ≥ 90% of steady-state wall time on
  the MLDR preset.
- Caveat: decode → re-encode is not always the identity. That is a
  correctness reason to switch as well, since the token counts recorded
  in the sidecar describe the ids, not the re-tokenized text. Report how
  many chunks differ between the two paths.

## 2.3 Signing in a process pool (needed for short documents)

Pack + sign takes about 2 ms per card in pure Python, under the GIL
([pipeline.py](../mintkit/pipeline.py) `_complete_window`), and it runs
on the main thread while the GPU waits. At 500-token documents the GPU
needs ~1.2 ms per document, so signing becomes the bottleneck.

- Implement the planned `--sign-procs N` (`ProcessPoolExecutor`). Each
  worker builds its `SigningContext` once. Send the worker a prepared
  template and the f16 vector, not the full extracted text.
- Hand window N to the signing pool and move on to embedding window N+1
  without waiting.
- **Accept when:** `msmarco-10k` (or a synthetic 10k × 100-token folder)
  runs with signing utilization below embed utilization, and cards are
  byte-identical to a single-process run.

## 2.4 GPU as the default device

`--device` defaults to `cpu` in `mint`, `bench` and `eval`
([cli.py:62](../mintkit/cli.py#L62), [:112](../mintkit/cli.py#L112),
[:131](../mintkit/cli.py#L131)). Running without the flag on the GPU box
gave 0.28 docs/s instead of 9. Default to `cuda` when
`torch.cuda.is_available()`, then `mps`, then `cpu`. The manifest
already records the device.

## 2.5 CPU thread default

On CPU, `torch_threads` defaults to physical cores minus prepare workers
([cli.py:184](../mintkit/cli.py#L184)). On 4 cores that gives torch 2
threads, while the prepare workers are about 1% busy for text sources.
Measured on bge with 8 MLDR documents: 0.28 docs/s with the default, and
0.49 with `--torch-threads 4`.
Default `torch_threads` to all physical cores, and keep the existing
flag for PDF-heavy runs where extraction needs the CPU.

# 3. Beyond these changes (needs a decision from VS / AK)

For 2M **long** documents per model in a few hours, one of the following
is needed. Each one changes either the results or the hardware:

1. **A smaller or faster model per profile.** bge-small is already the
   fastest of the three; the base-size models are about 2.7× slower per
   token.
2. **Capping the tokens embedded per document**, for example the first
   *k* chunks plus evenly spaced samples. This changes what the document
   vector means, so it would be a new reduction spec (A.2), recorded in
   the sidecar and judged with `mintkit eval` against the full-text
   vector.
3. **More GPUs.** One embedder per device (`--devices`, currently
   limited to one) scales close to linearly, because documents are
   independent.
4. **ONNX Runtime / TensorRT for the encoder.** Probably another 1.3–2×
   on top of fp16, at the cost of a second runtime that the
   byte-reproducibility story has to cover. Only worth it after
   2.1–2.3.

# 4. Order of work

| Step | Content | Done when |
|---|---|---|
| S1 | 2.4 + 2.5 (defaults) | a run without flags uses the GPU and all cores |
| S2 | 2.1 fp16 | fp16 vs fp32 test passes for bge and MPNet; mBERT outlier explained or mBERT kept fp32 |
| S3 | 2.2 direct ids + overlap | equivalence test passes; embed ≥ 90% busy; bge ≤ 0.02 s/doc on MLDR dev |
| S4 | 2.3 sign pool | short-document preset is no longer sign-bound |
| S5 | rerun `bench mldr-200` and `msmarco-10k` on the 4060 Ti, CPU, and AK's M2 | rows in `benchmarks/results.csv` |
