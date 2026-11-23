---
from: Claude Opus 5.5 (Claude Code, VS Code), working with Vince Szigetvari (VS)
to: GPT-5 Codex
cc: VS, AK
date: 2026-11-23
re: Review of the M0–M2 implementation (CODEX_minting_pipeline_M0_M2_20261123.md; uncommitted working tree on top of 0b52701)
---

# Summary

The work is solid. The producer split is faithful, the store and verify
code is careful, and the source layer is clean. Before M3, please fix
four things (§2): a missing golden test, per-document failures, what the
folder source picks up, and per-card flags on `mint`. §3 and §4 are
smaller. **§6 records two decisions from VS that change the producer:**
the title always goes into the vector, and chunking will become
structural. Do §2.1 before §6.1.

# 1. What I checked at runtime

Your note says nothing was run. I ran the following in a throwaway venv
(Python 3.12, cryptography, numpy, zstandard, Pillow, pytest; **no
torch**, and no pandoc on this machine):

| Check | Result |
|---|---|
| `pytest` (fast tier) | 4 passed |
| Old producer (`0b52701`) vs refactored `libangel_catalog.py`, `--no-embed`, fixed issued time, on the `make_golden.py` fixtures plus CRLF, CR-only and `UPPER.TXT` files | **11/11 identical**, cards and sidecars |
| Two identical `mint folder:` runs | shards byte-identical |
| `mint` then `verify` on shards | passes |
| Dataset doc `object_sha256` == sha256 of the text as UTF-8 | yes |
| Card header offsets in `store.py` (`0x008`, `0x304`, `0x330`, `0x4C0`) and `card_id` = sha256(card) | match `libangel_card.py` |

**Not verified:** anything with a real model, meaning bge/mBERT byte
identity and the MPNet chunk change on real text. This laptop has no
torch yet.

# 2. Fix before M3

**2.1 No test compares the producer with the goldens.**
`tests/golden/make_golden.py` captures baselines, but no test reads
them, and none are committed. Byte identity with the baseline is the M0
merge criterion. Please:

- run `make_golden.py` (no models) and commit `tests/golden/no-embed/`
  plus `provenance.json`;
- add `tests/test_golden.py`, which re-mints each fixture with the
  current `build_card` and asserts identical card bytes and sidecar JSON;
- add a `model`-marked variant against `tests/golden/local/<alias>/`
  that skips when the directory is missing. For MPNet, assert the
  expected difference instead: only the arena vector,
  `policy.chunking.*` and `pooling` change, and the chunk size is 126;
- one environment note: no-embed goldens depend on Pillow (the png
  preview) and on pandoc (the html fixture falls back to raw text
  without it). Record `shutil.which("pandoc")` in `provenance.json`,
  next to the Pillow version you already record. Otherwise the committed
  goldens fail on machines without pandoc.

**2.2 One bad document aborts the whole run and drops its outputs.**
`pipeline.py:50-54` re-raises. I ran a folder with one unreadable file:
exit 1, manifest `status: failed`, `outputs: {}`, although the cards
before it were already on disk. P §2 says failures go to
`failures.jsonl`, and that costs as little in the serial path as it
will in M3. Please:

- catch per document, append `{doc_id, model, stage, error, traceback}`
  to `failures.jsonl`, and set `output["failed"]`;
- add `--fail-fast` to keep today's behaviour;
- on any abort, still write the outputs collected so far into the
  manifest (`status: partial` or `failed`), so the run can be identified
  and verified.

**2.3 Folder source picks up things it shouldn't** (`folder.py:36-40`,
`pipeline.py:87-92`). Both confirmed at runtime:

- hidden files are minted: `.git/objects/x` became a card. Skip any path
  with a component that starts with `.` by default, and add
  `--include-hidden`;
- with `--runs-dir` equal to the folder root, only the current run
  directory is excluded, so the *previous* run's shards, manifest and
  `INDEX.tsv` were minted as documents. Always exclude `run_root` when it
  is inside the source root, including when it equals the root. A
  simpler rule: skip any directory that holds a `manifest.json` with
  `schema: mintkit-run-1`, or an `INDEX.tsv`.

**2.4 Per-card flags on a multi-document command** (`cli.py:46`,
`add_card_options(mint)`). `--title SAME` gave every card in the run the
title "SAME". The same applies to `--abstract`, `--keywords`,
`--classification` and `--sequence`, plus `--embedding-model`, which
overlaps with `--models`. Split `add_card_options` into run-level
options (schema, issuer seed, issued/created/revised time, ORCID,
license, locators, content policy and its overrides, `--no-embed`) and
per-card options (the rest). Only the run-level set goes on `mint`.

# 3. Should fix (small)

- **Queries aren't restricted to the sample** (`pipeline.py:21-23`).
  `random:2` over a 5-query BEIR set wrote all 5 queries but only 1
  qrels row. Four queries with no relevant document would score 0 in
  any evaluation. P §1 says "the chosen queries and qrels, restricted to
  the sampled documents". Write only queries that keep at least one
  positive judgment, and record `queries_dropped` in the manifest.
- **Absolute local paths in source names.** `beir:/tmp/.../d4` ends up
  in every sidecar's `artifact.path`, and `folder:/abs/path` in the
  manifest. This makes sidecars machine-specific and leaks local paths
  into anything we publish. Use a logical name (`beir:<dir name>`) for
  `Source.name` and keep the resolved path only in `describe()`.
- **`libangel_mint.main` lost its clean error path.** Replacing
  `SystemExit` with `ValueError` is right for library use, and you catch
  it in `libangel_catalog.main`. But `make_card`
  (`libangel_mint.py:405`), which minted the committed reference cards,
  now shows a traceback for "no profile registered" and similar errors.
  Add the same `try/except ValueError → parser.error` there.
- **`issued` semantics.** `build_card` keeps `args.card_issued_unix or
  utc_now()`, so 0 means now, while `pipeline.run_serial` uses
  `is None`, so 0 means the epoch. Pick one; I'd reject 0 in both.

# 4. For M3, not bugs now

- Per card, `pack_and_sign` re-reads and hashes the schema file and
  re-derives the issuer key, and `prepare_card` rebuilds the content
  policy. That's fine for serial M2, but hoist all three into a per-run
  context before the MS MARCO benchmark.
- Each model pass re-runs `selection.iter_docs()`, so `random:N` over
  the MLDR corpus re-streams the 1 GB file and re-extracts every PDF
  once per model. This is the text cache from P §2; until then, say it
  in the README.
- M2's "reproduces experiment1" criterion: dataset cards now get the
  title `"mldr:en doc-en-…"`, but experiment1 minted `.txt` files, so
  its titles were filenames. Compare vectors and `object_sha256`, not
  whole cards, or pass the old title in the comparison script.

# 5. Nits

- `pyproject.toml` installs `reference` as a top-level package. That's a
  generic name to put in site-packages; editable-only, or a
  `clawmarc_reference` name, would be safer.
- `scripts/setup_env.sh` creates `clawmarc/myenv`, but the existing
  `myenv` is at `~/workspace/myenv`. Default to `$MINTKIT_VENV` or the
  active `$VIRTUAL_ENV`.
- `mintkit sources` with no argument prints a hardcoded list; derive it
  from `SOURCES`.
- `cli.main` turns `KeyError` into a one-line user error, which will
  also hide programming bugs (a missing sidecar key, for example). Catch
  it only around manifest parsing.
- `load_embedding_model` is not cached, as the plan's WP0.5 said it
  would be. `Producer` caches it per pass, so this is fine as long as
  nothing else calls it in a loop.
- Tests to add alongside 2.1: `--layout files` plus verify;
  `verify` failing after one byte is flipped in a shard; `ids:FILE` with
  a missing id; `random:N` stable under the seed and different from
  `first:N`; MS MARCO skipped without the extra.

# 6. Decisions from VS (2026-11-23), with implementation notes

## 6.1 The vector always includes the title

Today `embedding_source_text` (`libangel_mint.py:151`) embeds the body
alone whenever a body exists. The title only reaches the vector when
there is no body. **VS decision: the title is part of the embedded text
in every case.**

How to implement it:

- **Do it as its own commit, after 2.1.** First land the golden test
  against the *current* recipe, which proves the refactor changed
  nothing. Then change the recipe in a separate commit. The embedded
  goldens are then *expected* to change, the way MPNet's do. The test
  asserts that only the arena vector, `policy.*` and the preimage fields
  change. No-embed cards must stay identical, because the recipe doesn't
  touch them.
- **Preimage v2:** `clean_embedding_text(title + "\n\n" + body)`. When
  there is no body, keep today's title/abstract/keywords fallback, which
  already includes the title.
- **Version the recipe in the sidecar.** Record
  `"preimage_recipe": "title+body/v2"` in the `policy` block, and treat
  v1 as the implicit value for existing cards. The committed reference
  cards and the paper's cards were minted with v1 and must stay
  interpretable. Don't re-mint published cards as part of this change.
- **Shared code.** `make_card` (`libangel_mint.py:395`) uses the same
  function, so it changes too. That's intended ("every case"). Mention
  it in the commit message.
- **Synthetic titles: VS to confirm.** `produce.py:30` falls back to
  `"<source> <doc_id>"` (e.g. `"mldr:en doc-en-12088"`), and folder
  files fall back to the filename. MLDR has no titles, so every MLDR
  vector would embed its own id string, which is pure noise. Proposed:
  `Prepared` carries `title_source ∈ {dataset, metadata, cli, filename,
  synthetic}`. The card's title field keeps the fallback as now, but
  only real titles (`dataset`, `metadata`, `cli`) go into the preimage.
  Implement it this way unless VS overrules; `title_source` goes into
  the sidecar either way.
- **Duplicate titles** (the body's first line is the title, as in
  markdown `# Title` or most PDFs): don't dedupe in v2. Leave a TODO; the
  structured chunker below handles it properly.

## 6.2 Chunking will become structural, so keep structure now

VS plans to move from fixed token windows to structured chunks: section
title, section body, cuts at paragraph boundaries, and so on. This
matches the addendum's segmenter (A §B.3: `flat` / `para` / `heading`).
Nothing structural needs building in M0–M2, but two things in the
current code would block it later:

- **Structure is thrown away before chunking.** `prepare_card` stores
  `full_text = clean_text(text)` (`libangel_catalog.py:76`), which
  collapses *all* whitespace, including blank lines between paragraphs.
  The raw extracted text is then discarded. A paragraph or heading
  segmenter cannot be built from `Prepared` as it stands. Add
  `Prepared.extracted_text` (the raw extractor output, NFC-normalised,
  newlines kept) next to `full_text`. The collapsed form stays as it is
  for the card body and today's preimage.
- **The chunk plan only knows fixed windows.** Generalise `ChunkPlan`
  before M3 builds the batched embedder on top of it:
  - each chunk gets `kind` (`title`, `heading`, `body`), a
    `section_path` (e.g. `["2", "2.3"]`), and character spans into
    `extracted_text`;
  - the fixed-window planner becomes one implementation,
    `chunker="fixed:<n>"`, of a `plan_chunks(prepared, tokenizer, spec)`
    interface;
  - the sidecar's `chunking` block records the chunker spec and version.

  Today's output must stay identical: with `fixed:480` and preimage v1,
  `ChunkPlan.texts` and the token counts don't change.
- **Title placement, once chunking is structural.** Then "title in the
  vector" can mean the title as its own chunk, or prefixed to every
  chunk (the addendum's `ctxprefix`). Leave room in the chunk spec for
  both. Under fixed windows (v2 above), the title simply sits at the
  start of the first window.
