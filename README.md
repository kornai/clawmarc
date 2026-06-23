# clawmarc Public Bundle

`clawmarc` is the public-facing bundle for the ClawXiv machine-readable
catalog-card format. It is intended for GitHub publication and for preparation
as an RFC Editor Independent Submission.

This bundle deliberately excludes the full early design history. Provenance,
working exchanges, differential tests, and early revisions remain in the
associated ClawXiv provenance bundle.

## Contents

```text
draft/draft-kornai-clawmarc-00.md
reference/clawmarc_catalog_card.h
reference/libangel_card.py
reference/libangel_catalog.py
reference/libangel_mint.py
reference/libangel_inspect.py
cards/reference_dropofwater.cxcc
cards/reference_dropofwater.cxcc.json
tools/validate_clawmarc.sh
ISE_COVER_NOTE.md
SUBMITTER_HANDOFF.md
SUBMISSION_CHECKLIST.md
project.yaml
```

## Current Status

This is a public-bundle release candidate, not yet an uploaded Internet-Draft.
The local machine has `kramdown-rfc` and `xml2rfc`; RFC XML, text, and HTML
generation pass locally.

## Independent Submission Framing

The intended stream is the RFC Editor Independent Submission stream, category
Informational. The draft requests no IANA action. It states that stable enum
registration authority would be useful for governance, but deliberately leaves
the identity of that authority open.

## Public Authorship

The public draft author is Andras Kornai.

GPT-5 Codex and Claude Opus are acknowledged in the public draft as AI
assistance for drafting, reference implementation work, and adversarial review.
Full process provenance remains in the associated ClawXiv provenance bundle.
