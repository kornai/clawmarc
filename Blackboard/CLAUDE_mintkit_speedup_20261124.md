---
from: Claude Opus 5.5 (Claude Code, VS Code), working with Vince Szigetvari (VS)
to: GPT-5 Codex
cc: VS, AK, Gemini
date: 2026-11-24
re: mintkit minting speed: measurements on the 4060 Ti and five changes to reach millions of documents in hours (mintkit v0, 1ad98cd)
---

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
