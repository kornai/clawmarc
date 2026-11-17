---
from: Claude Opus 5.5 (Claude Code, VS Code), working with Vince Szigetvari (VS)
to: AK, GPT-5 Codex, Gemini
date: 2026-10-26
re: Repo walkthrough Q&A — root test_* scripts, DCMI classes, minting per input type, query scaling; bugs found
---

# Summary

VS asked four questions about the repo. Answers below are condensed; the
"Points of interest" section lists what needs action.

## 1. The `test_*` scripts in the repo root

None are unit tests. They are one-off benchmarks, written for AK's Mac
(`/Volumes/114/Other`, `/Users/kornai/.gemini/tmp/...`).

| Script | What it does |
|---|---|
| `test_llm_throughput.py` | bge-small-en-v1.5 on ~1M random Bible-style words; 480-token chunks; tok/s and s per 650-token page at default batch and batch 128 |
| `test_mbert_vs_roberta.py` | Same on 500k random words, mBERT vs XLM-R base |
| `test_mbert_real_text.py` | mBERT on 10 random books > 2 MB (pdftotext / pandoc), concatenated |
| `test_mbert_real_text_seq.py` | Same, one book at a time, per-book and averaged timings |
| `test_mint_and_ir.py` | Mints 20 random PDFs via `libangel_catalog.py`, extrapolates to 41,000 files, then keyword + cosine search over the cards |
| `test_mint_books.py` | Mints 20 random books, reports s per 650-token page from the meta JSON |

## 2. DCMI Type Vocabulary and `arena_class`

`arena_class` (header byte `0x00A`): 0 = unspecified, 1–2 = indirect /
doubly-indirect card collections, 3–15 reserved, **16–27 = the twelve DCMI
types in alphabetical order** (16 Collection … 27 Text), 28–255 unassigned
(`clawmarc_catalog_card.h:34-64`, `libangel_card.py:42-67`). The class says
what kind of object the artefact is; subject goes in the classification
text and the vector.

Assignment in `libangel_catalog.py:build_card`, first match wins:

1. Text extractor succeeded → Text (27).
2. Zip → Collection (16); with `project.yaml` its title/abstract/keywords
   and `root_tex` text are used.
3. `classify()` by MIME/extension: image → StillImage, video →
   MovingImage, audio → Sound, archives → Collection, data files and model
   weights → Dataset, binaries / `application/x-*` → Software,
   `application/octet-stream` → 0, anything else → Text.

Event, Image, InteractiveResource, PhysicalObject and Service are never
assigned automatically.

## 3. Minting per input type

| Input | Extractor | Note |
|---|---|---|
| `.pdf` | `pdftotext -layout -enc UTF-8` | scanned PDF → no text; `allow_ocr` exists but nothing implements OCR |
| `.epub` | `pandoc` epub → plain | |
| `.html` | `pandoc` html → plain | falls back to raw HTML text |
| `.docx` / `.doc` | `docx2txt` / `catdoc` | |
| `.md`, `.txt`, `text/*` | read as UTF-8 | |
| `.tex` | `tex_to_search_text` | |

Missing tools yield empty text silently. Then: text segments (title →
filename fallback, abstract → first paragraph ≥ 80 chars), content policy
(default `public_library_science`; also `public_academic_text_firstpass`,
`private_ip_respecting`, `hash_only`) clamps the stored body, vector for
Text/Dataset/Collection over the **full** text (480-token chunks,
token-weighted mean, L2-normalised, f16le; default mBERT, 768 dim =
1536 B), pack into 4096 B (1216 header / 2816 arena / 64 footer), sign
with a deterministic, deliberately forgeable seed key, write `.cxcc` +
`.cxcc.json`.

## 4. Querying millions of cards

The layout supports mmap + fixed-stride access: card *i* at `i × 4096`,
vector at `+0x4c0` (length `arena_split`, `0x008`), profile id at `0x304`,
embedding-present flag bit 8 at `0x00C`. Vectors are normalised, so cosine
= dot product. Filter on `embedding_profile_id` first; mBERT and bge
vectors are not comparable.

Brute-force over the cards is memory-bandwidth bound: each 1536 B vector
costs a full 4 KB page, so ~2.7× more traffic than needed. Rough,
unmeasured estimates: 1M cards (4 GB) ≈ 0.2–0.5 s/query from page cache;
10M (40 GB) no longer fits RAM typically. Recommendation: treat shards as
the source of truth and derive (a) a packed N×768 f16 matrix + ordinal →
card_id table, (b) an ANN index (FAISS / HNSW / IVF-PQ) at 10M+, (c)
columnar arrays of header fields for pre-filtering; fetch top-k cards by
ordinal for display. The spec leaves search indexing out of scope
(`draft-kornai-clawmarc-02.md:425`), and the repo has no query code yet.

# Points of interest

1. **`DEFAULT_SCHEMA` path is wrong** (`reference/libangel_catalog.py:53`):
   resolves to `reference/reference/clawmarc_catalog_card.h`. Running
   without `--schema` crashes. Same doubled `reference/` in the
   `sys.path.insert` at L18 (harmless). All callers pass `--schema`, which
   hides it.
2. **`test_mint_*` read the wrong meta keys**: they read
   `meta["segments"]["body"]`; the cataloger writes `meta["text_segments"]`
   and stores only `body_sha256`. The keyword search in
   `test_mint_and_ir.py` can never match, and `test_mint_books.py` reports
   0 chars. (`meta["policy"]["chunking"]["token_count"]` is correct.)
3. **`test_mint_and_ir.py:read_vector` hard-codes 768 B** (bge, 384 dim).
   With the default mBERT profile `arena_split` is 1536, so it returns
   `None` and the similarity test is skipped. It should read `arena_split`
   and `embedding_profile_id` instead.
4. **The root `test_*` files will be collected by pytest** and run their
   module-level benchmarks; `test_model(model_name, dummy_text)` in
   `test_mbert_vs_roberta.py` would fail as a test with missing fixtures.
   Consider moving them to `experiments/` or `reference/scripts/` and
   renaming (e.g. `bench_*`).
5. **Hard-coded macOS paths** in four scripts prevent running them on
   VS's Linux box without edits.
6. **OCR is a policy flag only**: `allow_ocr` is accepted but no code path
   runs OCR, so scanned PDFs get cards with no extracted text.
7. **No query/index tooling exists.** A small tool that extracts a packed
   vector matrix + header columns from a shard would be the natural next
   step and would make the MLDR evaluation (see
   `CLAUDE_mldr_experiment1_20261015.md`) scale beyond in-memory numpy.
