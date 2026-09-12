# clawmarc Release and Submission Handoff

Date: 2026-06-28

This handoff describes the safe order for refreshing GitHub and, later,
refreshing the RFC Editor / Datatracker submission.

## Current Stance

Do not submit `draft-kornai-clawmarc-01` to Datatracker until after at least one
large-scale deployment test of the LibAngel batching machinery.

Reason: `-01` adds producer-authority language and LibAngel policy hooks. The
text is coherent, but the operational mechanism should be exercised on the
nessie / volatile / hlt-bme chain before the public Internet-Draft is updated.

## What Changed Since -00

RFC draft:

- Added `draft-kornai-clawmarc-01.md`.
- Generated `draft-kornai-clawmarc-01.xml`, `.txt`, and `.html`.
- Added language on producer authority and derived representations.
- Reframed embeddings as publication-bearing descriptions, not leakage.
- Added publication-posture language.

LibAngel:

- Added `content_policy.py`.
- Added editable policy profiles in `content_policies/`.
- Default profile is `public_library_science`.
- Added policy recording to card metadata.
- Added CLI hooks for text prefix, document vector, image thumbnail, and OCR
  policy knobs.
- Limited image preview payloads to a small 32x32 bilevel representation under
  `max_image_preview_bytes`.
- Added batch deployment scripts under `scripts/`.
- Batch indirect cards bind a run manifest that hashes both the run config and
  content policy.

## Important Files

```text
draft-kornai-clawmarc-01.md
draft-kornai-clawmarc-01.xml
draft-kornai-clawmarc-01.txt
draft-kornai-clawmarc-01.html

content_policy.py
content_policies/public_library_science.json
content_policies/public_academic_text_firstpass.json
content_policies/private_ip_respecting.json

scripts/batch_gzip_firstpass.sh
scripts/batch_gzip_firstpass.conf.example
scripts/mint_collection_card.py
```

## Policy Profiles

The default profile is:

```text
public_library_science
```

It is maximally informative for public science-library contexts: text prefix,
document vectors, OCR, transcripts, archive listings, and full-decompress hashes
are allowed; image previews are limited by `max_image_preview_bytes`.

For the large gzip corpus first pass, use:

```text
public_academic_text_firstpass
```

This disables document vectors and rich media extraction, but allows a sampled
decompressed text prefix.

For private or mixed-rights directories such as an `Other` directory, start
from:

```text
private_ip_respecting
```

Copy the JSON file, edit the booleans and limits, and point a deployment config
at the edited file with `CONTENT_POLICY_TEMPLATE` or `CONTENT_POLICY_JSON`.

## Large-Scale Test Order

1. Copy or pull this GitHub checkout onto `nessie`.
2. Copy `scripts/batch_gzip_firstpass.conf.example` to a run-specific config.
3. Set source and destination:

```bash
SOURCE_HOST="volatile"
SOURCE_DIR="/path/on/volatile"
BATCH_DEST="hlt-bme:/path/to/BatchDir"
CARD_DEST="hlt-bme:/path/to/Cards"
WORK_ROOT="/data/clawmarc_work"
```

4. Keep first pass conservative:

```bash
BATCH_SIZE=450
DOCVEC="no"
CONTENT_POLICY_NAME="public_academic_text_firstpass"
CONTENT_POLICY_TEMPLATE="$CLAWMARC_DIR/content_policies/public_academic_text_firstpass.json"
```

5. Run inside tmux on `nessie`:

```bash
bash scripts/batch_gzip_firstpass.sh myrun.conf
```

6. Inspect at least:

```text
WORK_ROOT/logs/run.log
WORK_ROOT/Meta/run_manifest.json
WORK_ROOT/Meta/content_policy.json
one Batch_*/cards/*.cxcc.json
one Batch_*/cards/*.indirect.cxcc.json
CARD_DEST/Meta/root.doubly_indirect.cxcc.json
```

7. Confirm the hlt-bme destination contains the expected batch/card structure.

## Refresh GitHub

After local checks pass, from the GitHub checkout:

```bash
cd /Volumes/114/Proj/ClawXiv/clawmarc-github
git status
git diff --stat
git add .
git commit -m "Add LibAngel content policies and clawmarc draft 01"
git push origin main
```

If you want to avoid putting `-01` on `main` before the large-scale test, use a
branch:

```bash
git checkout -b libangel-policy-hooks
git add .
git commit -m "Add LibAngel content policies and clawmarc draft 01"
git push -u origin libangel-policy-hooks
```

## Refresh Datatracker Submission

Only after the large-scale test and GitHub refresh:

1. Open and skim:

```text
draft-kornai-clawmarc-01.html
```

2. Run idnits:

```text
https://author-tools.ietf.org/idnits
```

3. Upload the XML to Datatracker as the next version:

```text
draft-kornai-clawmarc-01.xml
```

4. Confirm the Datatracker page now shows `draft-kornai-clawmarc-01`.

5. If writing to the ISE, mention that `-01` adds producer-authority language
   and implementation policy hooks after operational testing.

## Version-Skew Rule

The safe order is:

```text
local implementation and draft -> large-scale test -> GitHub push -> Datatracker -01 -> ISE note/update
```

Avoid uploading `-01` before the GitHub repo contains the matching XML and
reference implementation. Avoid notifying the ISE about `-01` before
Datatracker shows it.
