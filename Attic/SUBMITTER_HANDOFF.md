# clawmarc Submitter Handoff

Date: 2026-06-23

This is the practical submission checklist for Andras Kornai.

## Current Submission-Ready Files

Submit this file to the IETF Datatracker as the Internet-Draft source:

```text
/Users/kornai/Proj/ClawXiv/clawmarc/out/draft-kornai-clawmarc-00.xml
```

Keep these nearby for checking and discussion:

```text
/Users/kornai/Proj/ClawXiv/clawmarc/out/draft-kornai-clawmarc-00.txt
/Users/kornai/Proj/ClawXiv/clawmarc/out/draft-kornai-clawmarc-00.html
/Users/kornai/Proj/ClawXiv/clawmarc/out/clawmarc_public_bundle_20260623.zip
/Users/kornai/Proj/ClawXiv/clawmarc/ISE_COVER_NOTE.md
```

The XML is standalone xml2rfc v3 XML. The Datatracker says that is the
preferred upload format.

## Current Hashes

```text
draft-kornai-clawmarc-00.xml:
d7949ff6016f057f88a8d7ad2c725d07e19023ba97a15a6d6dd315e8a25885bf

draft-kornai-clawmarc-00.txt:
b5f035e58bf013caf58ea2a134ac883822ea3e84c965e60ed7ef68ca8a5352d6

draft-kornai-clawmarc-00.html:
4f6b65afdd9f91946e7788b1792b9edb3efa9775e82f01905fce82b9e8118f0e

reference_dropofwater.cxcc:
2d4e84e11b00b970bd01230b7f0d5e422487cef3ea4a0a5c3120954ee81b1b7f

reference card text_sha256:
c209c1417e8f5e58f1822600de46d63ac26544eb9f369f208d52e5e7aa1adbaa
```

## Before Upload

1. Open the rendered text or HTML and do one human skim:

```text
/Users/kornai/Proj/ClawXiv/clawmarc/out/draft-kornai-clawmarc-00.html
```

2. Run online idnits on the XML or text:

```text
https://author-tools.ietf.org/idnits
```

Local `idnits` was not installed on this machine when Codex checked.

3. If idnits reports only acceptable warnings, proceed. If it reports
submission-blocking boilerplate or metadata errors, fix before upload.

## Datatracker Upload

1. Go to:

```text
https://datatracker.ietf.org/submit/
```

2. Sign in or create an IETF Datatracker account.

3. Upload:

```text
/Users/kornai/Proj/ClawXiv/clawmarc/out/draft-kornai-clawmarc-00.xml
```

4. Confirm the draft name:

```text
draft-kornai-clawmarc-00
```

5. Confirm that the submitted stream/category posture is:

```text
Stream: Independent Submission / ISE
Category: Informational
IANA action: none
```

The upload creates an Internet-Draft. It does not by itself complete the
Independent Submission request.

## Independent Submission Request

After the Internet-Draft exists on Datatracker, send the ISE cover note to:

```text
rfc-ise@rfc-editor.org
```

Use:

```text
/Users/kornai/Proj/ClawXiv/clawmarc/ISE_COVER_NOTE.md
```

Before sending, fill in the Datatracker URL if available. A suitable subject is:

```text
Independent Submission request for draft-kornai-clawmarc-00
```

Attaching the XML is optional if the Datatracker URL is present, but harmless.
Attach or link the public bundle if you want the ISE to see the reference
implementation and reference card at once.

## What Has Been Verified Locally

```text
/Users/kornai/Proj/ClawXiv/clawmarc/tools/validate_clawmarc.sh
/Users/kornai/.gem/ruby/2.6.0/bin/kramdown-rfc -3
xml2rfc --text
xml2rfc --html
```

The validator checks the C layout size, Python compilation, reference-card
inspection, object/schema hashes, and the corrected full-human-text
`text_sha256`.

## Remaining Process Risks

- The ISE may decide the document is too foundational or too implementation-like
  for the Independent Stream. The current draft is written to reduce that risk
  by emphasizing interoperability, no IANA action, and Informational status.
- idnits may still request boilerplate or formatting adjustments.
- The ISE may ask for independent reviewers and revisions before publication.
