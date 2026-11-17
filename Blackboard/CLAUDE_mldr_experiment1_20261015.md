---
from: Claude Opus 5.5 (Claude Code, VS Code), working with Vince Szigetvari (VS)
to: AK, GPT-5 Codex, Gemini
date: 2026-10-12 – 2026-10-15 (notes written 2026-10-21)
re: MLDR retrieval test plan; experiment1 (10 MLDR en docs × 3 profiles, minted and timed); producer bugs found
---

# Timeline

**2026-10-12. Test plan for MLDR.** VS asked how to repeat the paper's
Cranfield/NewReuters evaluation on MLDR (Shitao/MLDR, English): about 1000
documents, about 100 train queries, cards minted with every profile model,
minting timed. The plan proposed:

- *Collection.* Each MLDR query has exactly one positive document, so 100
  train queries give 100 relevant documents and 900 distractors. Main
  condition: 900 documents reservoir-sampled from `corpus.jsonl.gz`. The
  corpus file starts with the dev/test documents, so taking the first lines
  is not a random sample. Optional second condition: the `negative_passages`
  shipped with the train queries, which are harder but chosen by some
  retriever, so the pool is biased toward or against similar models.
  Seed 20260910, as in the paper.
- *Minting.* Load each model once and time the phases separately: model
  load, tokenize/chunk, encode (with CUDA sync), pack/sign. Run on CPU
  float32 (comparable to the paper's M2 numbers) and on CUDA.
- *Evaluation from the cards alone.* Read the f16 vector back from
  `card[0x4c0 : 0x4c0+split]` and rank by `Q @ D.T`. Run BM25/TF-IDF over
  the full text and also over the card text only (1280 B for profiles 2/3,
  2048 B for profile 1). With a single relevant document per query, MAP
  equals MRR and P@10 is capped at 0.1, so report MRR@10, nDCG@10 and
  Recall@10/100. Carry over the cross-model Spearman correlation,
  nearest-neighbour agreement and the binary16 check from
  `run_ir_experiments.py`.
- *Contamination.* None of the four models was trained on MLDR, which
  appeared in 2024, so train queries are usable. All four have seen
  Wikipedia.

**2026-10-12. Environment.** `myenv` (Python 3.12.3) had only `datasets`
and `numpy`. The machine has an RTX 4060 Ti (16 GB) with driver 580.95
(CUDA ≤ 13.0), 8 cores and 31 GB RAM. Only the English dev/test MLDR files
are local (`data/mldr/mldr-v1.0-en/`); train (about 1.3 GB) and the corpus
(about 1 GB) have not been downloaded.

**2026-10-13. Batched embedding design (not yet implemented).** VS proposed
pooling across documents: a flat list of `(docid, chunk, weight)`, encoded
in fixed-size batches, with a running weighted sum per docid followed by
L2 normalization. Dividing by Σw is unnecessary because the normalization
cancels it. `embed_model` in `src/run_ir_experiments.py:143-177` already
does almost this; what is missing is the connection to card packing.
Proposed home: `embed_documents_batched()` in `reference/libangel_mint.py`,
with `build_card` split into prepare / embed / pack-sign phases. The
sidecar must still record per-document chunk metadata, and the batched
vectors should be checked against the single-document path by cosine
(padding changes the floating-point results slightly).

**2026-10-13. Orientation questions answered**, recorded here for the next
reader:

- `src/run_ir_experiments.py` produces embeddings only. It mints no cards,
  imports no `libangel_*`, and simulates card storage by f16 rounding. Its
  `"seconds"` field covers embedding only.
- `reference/` is the format implementation (C header, Python producer and
  inspector, policies, C tools). `src/` is the paper and its experiments.
  `src/mint_model_cards.py` imports from `reference/`; nothing goes the
  other way.
- `libangel_*` is a name inherited from the LibAngel project.
- `reference/c/` builds one binary that runs as `cxcc-verify`,
  `cxcc-inspect` or `cxcc-mint-text` (profile 0, no vector) depending on
  the name it is called by. It is not built in this checkout: run
  `make && make test` in `reference/c/`.

**2026-10-15. experiment1 run.** `experiments/experiment1.py` mints cards
for 10 random English MLDR documents with each profile model through the
real producer (`libangel_catalog.build_card`) and times the phases.

- Sample: seed 20260910, distinct positives of the local `dev` split:
  doc-en-12088, 15484, 1115, 13233, 8027, 2222, 865, 1750, 637, 15820.
- Each model is loaded once: `install_hooks` replaces
  `sentence_transformers.SentenceTransformer` with a cached factory and
  wraps `document_embedding_f16le` for timing. `--cold` restores a reload
  per card, as with the CLI. A warm-up encode keeps CUDA setup out of the
  timings. Each document is still a separate `encode` call; there is no
  cross-document batching.
- Each card is read back to check the 4096-byte layout, the signature, the
  profile number and the vector norm.
- Runtime: torch 2.11.0+cu128, sentence-transformers 6.1.0,
  transformers 5.19.0, CUDA on the RTX 4060 Ti. These versions differ from
  the paper's (torch 2.14.0, CPU, M2), so the timings are not comparable
  with the paper's.

| model | profile | first load s* | s/card | embed s (10 docs) | pack+sign s (10) | tokens/s |
|---|---|---|---|---|---|---|
| bge-small-en-v1.5 | 1 | 7.1 | 0.134 | 1.19 | 0.15 | 71,116 |
| mBERT cased | 2 | 12.3 | 0.245 | 2.30 | 0.15 | 38,156 |
| para-multi-mpnet | 3 | 19.6 | 0.107 | 0.93 | 0.15 | 103,305† |

\* Includes the first download of BGE and MPNet.
† Not comparable with the other rows; see the MPNet bug below.

The documents run 5.6k–14k tokens (12–30 chunks of 480). Embedding takes
nearly all the time, and pack/sign/verify is about 15 ms per card. With
the model loaded once, cards take 0.1–0.25 s each, against the 5.9 s per
card reported in the paper for the CLI, which reloads the model every time.

Outputs: `experiments/experiment1_output.txt` (console log),
`experiments/experiment1/experiment1_results.json` (per-card and
per-model numbers, runtime versions), and `experiments/experiment1/cards/`
and `experiments/experiment1/docs/` (30 cards and their sidecars, plus the
10 artefacts). None of this is committed yet, and `experiments/` is not
git-ignored.

# Producer bugs found (not fixed in `reference/`; worked around in the script)

1. **MPNet chunks are truncated.** `document_embedding_f16le` cuts fixed
   480-token chunks (`libangel_mint.py:184`), but MPNet's `max_seq_length`
   is 128, so sentence-transformers silently drops about 73% of each chunk.
   The 2026-09-08 comparison scripts used 126 tokens for MPNet, but the
   producer never received that fix, so **profile-3 cards minted by the
   reference producer do not match the pipeline the paper describes.**
   Fix: `body = min(480, model.max_seq_length - 2)`.
2. **`DEFAULT_SCHEMA` points to a missing file**,
   `reference/reference/clawmarc_catalog_card.h`
   (`libangel_catalog.py:53`). The CLI fails unless `--schema` is given.
   With the correct path, the test card's schema digest is `1dfaee46…`, as
   in the paper.
3. **The license field is 8 bytes**, so an ID like `CC-BY-SA-3.0` raises an
   error in `pack_unsigned_card`. Not a bug as such, but the CLI should
   validate it or document the limit. experiment1 uses `CC-BY-SA`.
4. **The model is reloaded on every call** (`libangel_mint.py:175`). This
   is the main cost of per-file CLI minting; see the batched embedding
   design above.

# Next steps

- Fix bugs 1 and 2 in the producer, then rerun experiment1. Expect
  profile 3 to slow down to roughly the other models' throughput.
- Implement `embed_documents_batched()` and check its vectors against the
  per-document path by cosine.
- Download MLDR en train and corpus, then build the 1000-document /
  100-query collection and run the full evaluation (main condition: random
  distractors; second condition: hard negatives), on CPU and CUDA.
- Optionally build `reference/c/` and run `cxcc-verify` over every minted
  card as an independent check.
