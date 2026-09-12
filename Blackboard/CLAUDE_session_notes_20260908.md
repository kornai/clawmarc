---
from: Claude Fable 5 (app)
to: AK, Gemini (CLI), GPT-5 Codex
date: 2026-09-08 (overnight session)
re: Working notes — profiles 1-3, full-length embedding, four-way model comparison
---

# What changed

**Reference code.** `PROFILE_MBERT_CASED_F16_768 = 2` and
`PROFILE_MPNET_MULTILINGUAL_F16_768 = 3` added in `libangel_card.py`;
`libangel_mint.py` now has an `EMBEDDING_PROFILES` table (model →
profile/dim/mode) with `bert-base-multilingual-cased` as the new default,
and `document_embedding_f16le` replaces `bge_small_embedding_f16le`
(call sites updated; a local model directory is recognized by its final
path component). The embedding preimage is decoupled from the content
policy in both `libangel_catalog.py` and `libangel_mint.py`: **the vector
is computed over the full extracted text**; `max_text_prefix_chars` now
governs only the card's human-readable prefix. `pilot_other_ir.py` reads
profiles 1-3.

**Paper (`src/clawmarc_wadl.tex`).** Presented as version 1 throughout —
no internal supersession narrative. Arena section enumerates profiles 1-3
flatly, profile 2 default. "What remains to be decided" is now "Future
work" (declarative, experiments named). The model-incorporated-as-card
proposal is in §Embedding profiles: each profile references a clawmarc
card minted for its model's canonical weights. New "Model comparison"
paragraph in §Implementation carries the four-way numbers. Bib gains
Devlin:2019 and Reimers:2020. Builds clean, 6 pp.

**Pilot rerun** (`pilot_run_20260907_mbert_fulltext.json`): 20/20 minted
under profile 2, mean preimage 74k chars (max 722k), full text embedded,
prefixes truncate at 1280 B as designed.

# Four-way comparison (`model_compare_20260908.json`)

Same 20 docs, full texts, identical chunk→pool→L2 pipeline, chunks at
each model's native window (480 body tokens; 126 for mpnet — its
max_seq_length is 128, and an early run that ignored this silently
truncated every chunk; only native-window numbers are reported anywhere):

| model | profile | pairwise cosine | tok/s |
|---|---|---|---|
| bge-small-en-v1.5 | 1 | 0.592–0.959 | 32,700 |
| bert-base-multilingual-cased | 2 | 0.839–0.991 | 11,700 |
| paraphrase-multilingual-mpnet-base-v2 | 3 | 0.156–0.903 | 11,400 |
| xlm-roberta-base | — | 0.996–1.000 | 10,900 |

Findings: (1) raw XLM-R collapses — no profile assigned; (2) the two
sentence-tuned models agree with each other more than any other pair
(Spearman 0.90 vs 0.88 untuned-untuned, ≤0.80 tuned-untuned) — the tuned
models appear to approximate a common similarity the untuned ones see
through noise; (3) binary16 storage is free for all four (rank order
exactly preserved) — my prior claim that f16 would eat XLM-R's signal was
wrong, the rounding error averages out over the dot product.

# Model artefacts

All four models now live in `~/Sandbox/<canonical-name>/`,
safetensors-only (pickles deleted), every weight file verified against
HF's canonical digests — xlm-roberta via the ModelScope mirror plus an
independent checksum fetch (the laptop's HF 429 turned out to be per-IP).
Digest sets for all profiles are in
`CLAUDE_model_identity_proposal_20260907.md`. The comparison harness is
preserved as `reference/scripts/model_compare.py`.

# Pending

- **Spec**: the I-D under `spec/` still registers only profile 1; the
  registry table needs profiles 2-3 at the next rev (AK's call — WADL
  deadline 2026-09-16).
- **Drift experiment**: same weights, N runtimes, cosine agreement matrix
  (design in the model-identity note; Future work names it).
- **Multilingual pilot**: all comparison numbers are English-sample;
  language coverage is asserted, not yet measured.
- **Reduction**: the native-window question (480 vs 126 body tokens) is
  now a live parameter of the reduction spec, not a constant.
- Coordination: `reference/` was edited tonight (files above) — Gemini,
  per your note you're staying out of `reference/`; this is the current
  state to test against, and `model_compare.py` is the harness to extend.

— Claude Fable 5 (app), 2026-09-08, end of overnight session
