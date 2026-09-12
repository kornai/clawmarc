# CXCC Independent Submission — homologized plan (AK rulings applied)

Status: converging plan for AK; for Codex to review/converge. 2026-06-23.
Supersedes the separate Claude and Codex plans on the points AK ruled.

## Decisions ruled by AK (settled)

- **Stream / category**: RFC-Editor Independent Submission, **Informational**.
- **IANA**: **request registries** for the extensible enums, with generous free
  space (Section 3 below).
- **Authorship**: this venue takes LLM coauthorship. **A. Kornai senior
  author; Claude Opus 4.8 and GPT-5 Codex junior authors** (relative order TBD
  between the two — proposed: order of first contribution to the catalog-card
  spec, i.e. Codex then Claude, since Codex drafted r1; Claude defers to
  Codex's preference). The human senior author performs AUTH48 and is the
  point of contact regardless of byline.

## 0. clawmarc bundle structure (AK)

A new ClawXiv bundle, **clawmarc** (ClawXiv MARC — machine-readable
cataloging), has two parts:

- **public-facing `clawmarc`** -> IANA Independent Submission + GitHub: the
  clean Internet-Draft, the reference card, and the reference implementation.
  No internal revision history.
- **provenance `rfc-clawhiv`** -> stays in the ClawXiv branch: the r1/r2/r3/rc1
  evolution, the differential tests, the AI-to-AI cross-reviews, the Blackboard
  exchanges, and AK's rulings — the full story, not for IANA.

This plan governs the public-facing `clawmarc` part. The on-wire 4-byte magic
remains `CXCC` (the frozen record type; renaming would churn the rc1 layout and
the already-minted reference cards) while the published format is named
clawmarc; a wire magic distinct from the format name is ordinary. (AK to confirm
keep-`CXCC` vs rename before IANA.)

## 1. Document identity and toolchain

- Internet-Draft `draft-kornai-clawmarc-00`; the RFC number is assigned only at
  publication. Drop the internal "RFC CXCC-0001" styling.
- Authored in **kramdown-rfc** (markdown -> xml2rfc v3 + txt).
- Boilerplate: ISE "Status of This Memo" (`submissionType="independent"`,
  `category="info"`); RFC 2119 + 8174 conventions; standard IPR/copyright.

## 2. Scope statement (front matter)

In scope: the 4096-byte card byte layout, field semantics, artefact
representation, signing/verification, the producer's deterministic obligations,
and the IANA registries below. Out of scope (stated explicitly): catalog
governance, the long-body embedding *reduction* (a profile/future-work matter,
compared by cosine not byte-identity), and any one storage backend — IPFS,
Swarm, HTTP mirrors are informative and interchangeable.

## 3. IANA Considerations (concrete; generous free space)

This document requests a new "ClawXiv Catalog Card (CXCC)" registry group. All
registries use registration policy **Specification Required** (RFC 8126), each
with a Private Use / Experimental range IANA does not manage. Assignments by
this document are a small fraction of each space, by design.

**3.1 CXCC Arena Class** (`arena_class`, 0-255)
    0-2     catalog-card indirection: 0 DIRECT, 1 INDIRECT, 2 DOUBLY-INDIRECT  [this doc]
    3-15    Reserved (structural/indirection extensions)
    16-28   artefact types: ARTICLE..ARCHIVE                                    [this doc]
    29-223  Unassigned (Specification Required)
    224-254 Private Use / Experimental (unmanaged)
    255     Reserved
    -> 16 of ~240 type slots used; ~195 open + 31 private.

**3.2 CXCC Size Class** (`size_class`, 0-255)
    0-9     magnitude ladder (0 empty .. 9 YB-range)                            [this doc]
    10-239  Unassigned (Specification Required; finer or larger buckets)
    240-255 Reserved
    -> 10 of 256 used.

**3.3 CXCC Embedding Profile** (`embedding_profile_id`, uint16, 0-65535)
    0          none                                                            [this doc]
    1          clawxiv-embed-v1 (bge-small-en-v1.5, 384-d, L2, f16)            [this doc]
    2-65023    Unassigned (Specification Required)
    65024-65535 Private Use / Experimental (unmanaged)
    -> 2 of 65536 used; effectively unlimited room.

**3.4 CXCC Encryption Profile** (`enc_profile`, 0-255)
    0       none; 1 AES-256-GCM; 2 age/X25519                                  [this doc]
    3-223   Unassigned (Specification Required)
    224-254 Private Use / Experimental (unmanaged)
    255     Reserved

**3.5 CXCC Flag Bits** (`flags`, uint32 bit positions)
    bits 0-10   assigned                                                        [this doc]
    bits 11-31  Unassigned (Specification Required)

The Private Use ranges let independent deployments experiment without
collision with registered values; the large Unassigned ranges keep the format
extensible for decades without a layout change.

## 4. Editorial scrub (agreed Claude+Codex)

Present as one clean v1: remove the r1/r2/r3/rc1 internal history, every
`~/Proj` path and Doit pointer, and provisional-embedding language beyond a
one-paragraph out-of-scope note. The reference header ships as an appendix
(per the bundle-hashing rule), so `schema_sha256` covers prose + layout.

## 5. Conflict-review safety (agreed)

State explicitly: CXCC defines a data format, allocates no IETF protocol code
points, modifies no Internet protocol, and creates IANA registries only in its
own new CXCC namespaces — no overlap with any IETF working-group protocol work.

## 6. References

Normative: RFC 2119, 8174, 8126 (IANA policies), 8032 (Ed25519), FIPS 180-4
(SHA-256), Unicode UAX #15 (NFC). Informative: IPFS, Ethereum Swarm,
OpenTimestamps, the bge embedding model.

## 7. Remaining issue list for AK

- Confirm junior-author order (Codex-then-Claude proposed) and the exact
  author block (names, affiliations, addresses required by the I-D).
- Confirm `draft-kornai-clawxiv-catalog-card` as the draft name stem.
- The still-open spec items (independent of submission): freeze the RFC so
  `schema_sha256` stabilizes; rule the `object_sha256` container question;
  Codex's body-append (Finding B). Submission conversion should start from the
  frozen text.
