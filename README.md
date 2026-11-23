# clawmarc — the 4096-byte catalog card

ClawXiv bundle for the clawmarc catalog-card format: the specification (an
Internet-Draft), its reference implementation, reference cards, and the
human-readable paper that presents the format to the digital-library
community. Created 2026-09-07 by splitting the format off from the ClawXiv
software tree (`~/Proj/SW/ClawXiv/clawmarc*`), which is left in place until AK
retires it.

This directory is both the working tree and the bundle layout; released
bundles are tarball snapshots of it (recipe below), never a staging copy.

## Layout

- `src/clawmarc_wadl.tex` — reviewer-facing prong: short paper for WADL 2026
  (Web Archiving and Digital Libraries Workshop, with JCDL, Dallas,
  2026-10-16; deadline 2026-09-16). ACM sigconf, AK sole author, AI
  assistance and Eliot Lear in the acknowledgments.
- `src/clawmarc.tex` — clawxiv-ready prong, joint authorship, clawxiv.sty
  provenance boxing. Maintained in parallel with the WADL prong, synced by
  hand; never refactored into shared `\input` bodies.
- `src/clawmarc.bib` — bibliography (local subset; every entry also in
  `~/paper/Common/Bib/ml.bib` under the same key).
- `spec/` — draft-kornai-clawmarc-00 (uploaded to the IETF Datatracker
  2026-06-24, declined for the Independent stream by the ISE; still an active
  I-D, expires 2026-12-25) in md/xml/txt/html; draft -01 (staged, never
  uploaded: adds producer-authority and publication-posture language);
  **draft -02 = layout 1.3**: `arena_class` 16-27 are the twelve DCMI Type
  Vocabulary terms in alphabetical order, 0 = no class, 1-2 structural,
  3-15 reserved, 28-255 unassigned (AK ruling 2026-09-07). The code and the
  reference cards follow -02; -00/-01 are historical. -02's embedding-profile
  registry lists profiles 1-3 (bge-small / mBERT / mpnet-multilingual) with
  informative references, added 2026-09-11; kramdown-rfc is not installed
  here, so the `.md` and `.xml` were edited in parallel by hand and the
  `.txt`/`.html` re-rendered with xml2rfc 3.34.0.
- `reference/` — `clawmarc_catalog_card.h` (normative layout, compile-time
  size and offset assertions), Python producer/inspector/cataloger (now with
  PDF and EPUB extraction), `content_policy.py` + three policy profiles,
  batch collection scripts, `scripts/pilot_other_ir.py` (the pilot in the
  paper). `libangel_mint.py` signs with a deterministic **test** seed unless
  `--issuer-key-file` supplies a release key; the sidecar's `key_kind` says
  which. `scripts/validate_clawmarc_repo.sh`, which assumed the old GitHub
  checkout layout, was retired to `Attic/scripts_historical/` on 2026-09-11.
- [`mintkit/`](mintkit/README.md) — dataset readers and serial catalog-card minting.
- `cards/` — two reference cards (`.cxcc` + `.cxcc.json`), layout 1.3;
  layout 1.2 originals in `Attic/cards_layout_1.2/`. Test-seed signatures.
- `src/model_resources/` — the four embedding-model archives (`archives/`),
  their **root cards** (`cards/`, schema digest = the C header, test-seed
  signatures), `SHA256SUMS`, `IPFS_CIDS.tsv`, `SWARM_REFS.tsv`,
  `CARD_INDEX.md`, and `PUBLISH_MANIFEST.md` (what to serve at
  `https://lebadus.ai/Resources/Models/`). Minted by `src/mint_model_cards.py`.
- `src/run_ir_experiments.py`, `src/run_cranfield_experiment.py` and their
  result files `cranfield_experiment_results.json`,
  `newreuters5000_results.json` — the collection experiments in the paper
  (seed 20260910); `Blackboard/pilot_run_20260907_mbert_fulltext.json` and
  `Blackboard/model_compare_20260908.json` — the demonstration and model
  comparison (seed 20260907). `src/transport_probe/` — card-only Linux probe.
- `bench/legacy/test_mint_and_ir.py` — Gemini's first pilot pass (2026-09-07), kept as it
  was written; its results are superseded (see `Blackboard/pilot_run_20260907.md`).
- `Blackboard/` — Lear exchange record, CFP record, session handoffs.
- `Attic/` — ISE-era submission notes and handoffs (historical).
- `project.yaml` — canonical metadata and change log.
- `provenance/` — machine-readable provenance summary.

The full design history (r1/r2/r3/rc1 evolution, differential tests, AI-to-AI
cross-reviews) stays in the ClawXiv and LibAngel Blackboards; the GitHub
mirror is https://github.com/kornai/clawmarc.

## Building the WADL paper

```sh
cd src && pdflatex clawmarc_wadl && bibtex clawmarc_wadl && pdflatex clawmarc_wadl && pdflatex clawmarc_wadl
```

acmart requires BibTeX with `ACM-Reference-Format`; the clawxiv prong uses
biblatex/biber as usual.

## Bundling

```sh
V=v1
B=clawmarc_$V && mkdir /tmp/$B
rsync -a --exclude '*.aux' --exclude '*.log' --exclude '*.bbl' --exclude '*.blg' \
      --exclude '*.out' --exclude '*.bcf' --exclude '*.run.xml' --exclude '__pycache__' \
      ./ /tmp/$B/
(cd /tmp/$B && find . -type f ! -name MANIFEST.sha256 | sed 's|^\./||' \
  | sort | xargs shasum -a 256 > MANIFEST.sha256)
tar -czf $B.tgz -C /tmp $B
```

`Blackboard/lear_exchange_20260907.md` is private correspondence: strip it
from any public release.
