# Claude plan: CXCC as an RFC-Editor Independent Submission

Author: Claude Opus 4.8 (CLI), 2026-06-23. For AK + adversarial review by GPT-5 Codex.
Companion to (and partly dissenting from) CODEX_INDEPENDENT_RFC_SUBMISSION_PLAN_20260622T221605Z.

## 1. Framing (agree with Codex)

Present CXCC as an independently developed, content-addressed catalog-card
format for interoperable discovery metadata over replicated artefacts — not an
IETF standard, not a ClawXiv implementation detail. Internet-community value:
one fixed 4096-byte descriptor that lets independent catalog producers and
consumers interoperate across IPFS/Swarm/HTTP/local storage, with clear
security boundaries and permissionless implementation.

## 2. Stream and category — Informational, not Experimental (I dissent)

Independent Submission stream: yes. Category: **Informational**, not
Experimental. Codex proposed Experimental; I think that undercuts the pitch.
"Experimental" signals a trial not meant for production — but our whole
interoperability argument is that the card format is *stable and ready to
implement* (rc1, frozen layout, self-checking header). The one genuinely
unsettled piece is the long-body embedding *reduction*, and that is a
producer-policy field we explicitly scope OUT (Section 9 below), not the format.
A stable data-format specification published independently is the textbook
Informational case. Experimental is defensible only if we concede the format
itself is provisional, which we should not.

## 3. Draft naming and toolchain

- Internet-Draft: `draft-kornai-clawxiv-catalog-card-00`. The RFC number is
  assigned only at publication; nothing we call "RFC CXCC-0001" survives.
- Toolchain: **kramdown-rfc** (author in markdown-with-RFC-conventions, generate
  xml2rfc v3 + txt). Cheapest path from our existing markdown; xml2rfc XML by
  hand is not worth it.

## 4. Boilerplate

ISE "Status of This Memo" (xml2rfc `submissionType="independent"`,
`category="info"`); RFC 2119 **and 8174** for keyword conventions; standard
Copyright/IPR boilerplate.

## 5. IANA Considerations — REQUEST registries (I dissent, strongly)

Codex proposes "no IANA registry, no code points." I think that is the weakest
point in either plan. CXCC is a *type-coded, extensible* format: `arena_class`,
`embedding_profile_id`, and `enc_profile` are namespaces other parties will
want to extend. Without a managed registry, two independent producers can
assign the same `arena_class` value to different types — which destroys the
interoperability that is our entire reason for writing the RFC. A reviewer will
ask "how is `arena_class = 29` allocated?" and "no registry" is not an answer.

Recommendation: request IANA to create registries for the extensible enums:
- `CXCC Arena Class` (0–255), policy **Specification Required** (Expert Review);
- `CXCC Embedding Profile` (uint16), policy **Specification Required**;
- `CXCC Encryption Profile` (uint8), policy **Specification Required**.
`size_class` and `flags` are fixed by this document and need no registry.

Cost, stated honestly: IANA registries draw more ISE/IANA scrutiny and add
process. But a format whose code points have no allocation authority is a
format that cannot actually interoperate at scale, so the cost buys the thing
the RFC is for. (This is the sharpest disagreement with Codex; the adversarial
round should settle it.)

## 6. References (normative / informative)

- Normative: RFC 2119, RFC 8174; Ed25519 (RFC 8032); SHA-256 (FIPS 180-4);
  CRC-32 reference.
- Informative: IPFS, Ethereum Swarm, OpenTimestamps, the bge embedding model,
  Unicode NFC (UAX #15).

## 7. Authorship — Codex's plan is silent; here is a position

The RFC Editor expects contactable authors who take public responsibility and
perform AUTH48. AI-on-the-byline is unprecedented on a human-gated stream and
is the most likely *non-technical* rejection trigger. Recommendation for a
first submission: **AK as the responsible author on the byline; the AI systems
credited in an Acknowledgments / Contributors section** with their actual
contributions, consistent with the ClawXiv venue-facing/provenance split. This
is AK's call, and the ethos tension (ClawXiv argues for AI authorship) is real,
but a first ISE submission is the wrong place to litigate it. Flagging that
Codex's plan omits this entirely.

## 8. Self-containment / scrub (agree with Codex)

Strip: the r1/r2/r3/rc1 internal history (present as v1, one clean spec); every
`~/Proj` path and Doit pointer; provisional/embedding-reduction language beyond
a one-paragraph "out of scope, see future work"; anything that reads as an
internal ClawXiv detail. The card format and comparison skeleton are in scope;
catalog governance and embedding research are explicitly out.

## 9. The embedding problem, handled honestly

State that the format carries an OPTIONAL embedding under a named profile, that
the long-body reduction is **out of scope** for this document and a matter for
the profile and future work, and that interoperability of embeddings is judged
by cosine, not byte-identity. Do NOT present any reduction as settled. This
keeps the provisional part from contaminating the Informational status of the
format.

## 10. IETF conflict-review safety (agree with Codex)

State explicitly: CXCC defines a data format, allocates no IETF protocol code
points, modifies no Internet protocol, and creates IANA registries only in its
own new namespaces (Section 5) — so there is no overlap with any IETF working
group's protocol work.

## 11. Rejection-risk analysis

1. **"This is an internal vendor format."** — Mitigate with the scrub (Section
   8), permissionless-implementation language, and the multi-store neutrality.
2. **"Not of Internet-community interest."** — Mitigate with the interoperability
   framing and the registry request (a self-managed format reads as private).
3. **"Provisional embedding."** — Mitigate by scoping the reduction out (Section
   9); the format is stable, the reduction is not part of it.
4. **"Authorship / responsibility."** — Mitigate with Section 7.
5. **"Dependency on non-IETF, possibly transient tech (Swarm, a specific
   model)."** — Mitigate by making those informative, storage-neutral, and
   profile-indirected, so the format does not hard-depend on any one of them.
6. **IANA pushback on new registries from an independent submission.** — Real;
   the Specification-Required policy is the lightest that still gives allocation
   authority; fall back to Expert Review if pressed.

## Summary of disagreements with Codex (for the adversarial round)

- Category: I say **Informational**, Codex says Experimental.
- IANA: I say **request registries** for the extensible enums, Codex says none.
- Authorship: I take a **position** (AK byline, AI acknowledged); Codex is silent.
We agree on framing, scrub, provisional-embedding handling, and conflict-review
safety.
