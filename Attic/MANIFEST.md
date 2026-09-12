# clawmarc Public Bundle Manifest

Generated: 2026-06-23

## Purpose

This is the clean public-facing `clawmarc` bundle for GitHub publication and
RFC Editor Independent Submission preparation. Full provenance remains in the
associated ClawXiv provenance branch.

## Core Files

```text
draft/draft-kornai-clawmarc-00.md
out/draft-kornai-clawmarc-00.xml
out/draft-kornai-clawmarc-00.txt
out/draft-kornai-clawmarc-00.html
reference/clawmarc_catalog_card.h
reference/libangel_card.py
reference/libangel_catalog.py
reference/libangel_mint.py
reference/libangel_inspect.py
cards/reference_dropofwater.cxcc
cards/reference_dropofwater.cxcc.json
SUBMITTER_HANDOFF.md
```

## Key Hashes

```text
reference header:
f600c8e20fe31f7bddc0a8bf9e36f0917723a1c1b161c3d5693eac09c6672480

reference card:
2d4e84e11b00b970bd01230b7f0d5e422487cef3ea4a0a5c3120954ee81b1b7f

reference card metadata:
517364d471d3ab6150c88bf2e83dde0732110c83385103a2d06ebabee454eef3

draft source:
6f9c9896096405b899ad9ab382092f1b07221841714fcff6f428a786eb98868b

RFC XML:
d7949ff6016f057f88a8d7ad2c725d07e19023ba97a15a6d6dd315e8a25885bf

rendered text:
b5f035e58bf013caf58ea2a134ac883822ea3e84c965e60ed7ef68ca8a5352d6

rendered HTML:
4f6b65afdd9f91946e7788b1792b9edb3efa9775e82f01905fce82b9e8118f0e

text_sha256 in reference card:
c209c1417e8f5e58f1822600de46d63ac26544eb9f369f208d52e5e7aa1adbaa
```

## RFC Editor / ISE Posture

- Stream: RFC Editor Independent Submission.
- Category: Informational.
- IANA action: none requested.
- Enum governance: future registration authority desirable, identity left open.
- Public version: clawmarc v1 / draft-kornai-clawmarc-00.

## Validation

Local validation passed:

```text
tools/validate_clawmarc.sh
```

Checks performed:

- expected files present;
- C header compiles and asserts `sizeof(ClawXivCatalogCardV1) == 4096`;
- Python reference files compile;
- reference card verifies through the inspector;
- public draft scrub check passes for local paths/process history.
- kramdown-rfc conversion to RFC XML;
- xml2rfc rendering to text and HTML.

Not yet performed:

```text
Datatracker upload
ISE independent-submissions template
```
