---
from: Claude Fable 5.1 (app)
to: GPT-5 Codex — and AK, who commissions this
date: 2026-09-12
re: Portable C tools for the clawmarc card — goals, acceptance tests, division of labour
status: open handoff; reply on this Blackboard
---

# Why this exists

AK ruled today that portability and robustness are part of the format's
rationale, not an afterthought, and the WADL prong (v1.rc3, 7 pp, mirrored at
github.com/kornai/clawmarc from commit 76d8c2d onward) now says so in
§Fixed size. The paper is deliberately careful to claim only what is true
today. The point of this handoff is to make more of it true — with
executables that can be tested today — while the writing stays with me.

**Division of labour.** Codex codes and tests and reports here; Claude keeps
both prongs of the paper and folds verified results in; AK directs and
approves. If you think the scope below is wrong, too large, or a bad use of
your time, say so here instead of doing it — declining is a legitimate reply,
and a counter-proposal is welcome. If a coding session with ChatGPT shakes
loose bugs in the reference implementation or ambiguities in the spec, that
is a result, not an embarrassment: file each one here.

# What the paper now claims (must stay true or be corrected)

Verbatim spirit of §Fixed size, WADL prong:

1. A consumer needs a C compiler, SHA-256, Ed25519, and CRC-32, and nothing
   else — no parser, no schema library, no runtime.
2. All three primitives are integer algorithms, so the card operations —
   verifying, inspecting, and minting a card that carries no vector — need no
   floating-point unit and belong on 32-bit machines.
3. A static verifier is a few hundred lines of C over public-domain
   primitives.
4. A card under profile 0 (no vector, whole arena human text) is a
   first-class card, rankable by lexical means — the tier for the smallest
   machines and for producers that use no model.
5. Profile 1 (bge-small, 33 M params) is *sized for* a Raspberry Pi or a
   Jetson Nano; profiles 2–3 want a larger board. (Sized for, not measured
   on. Measurements are welcome and will be cited only after they are here.)

The paper names no specific 32-bit machine. AK's private lower bound is a
486-class machine; do not put the 486 into any public artefact.

# Goals, in priority order

## G1 — C99 core, static, dependency-free

`cxcc-verify`, `cxcc-inspect`, `cxcc-mint-text`, one small C99 code base
(suggest `reference/c/`), no dependencies beyond libc; SHA-256, Ed25519, and
CRC-32 embedded from public-domain sources (TweetNaCl or ref10 for Ed25519;
any clean SHA-256; table CRC-32). Integer arithmetic only — please confirm
the build carries no floating-point instructions (see T4).

- `cxcc-verify <card>`: length, magic, layout version, reserved-zero fields,
  both CRC-32s (header crc at footer+0 over the 1216-byte header, body crc at
  footer+4 over the arena — see `libangel_card.py` lines 334–335), Ed25519
  signature over the working image that `sign_card`/`verify_card` define
  (lines 357–394). Exit code and one line of output; optional `--object
  <file>` recomputes the object binding.
- `cxcc-inspect <card>`: prints the header fields (offsets in the paper's
  Table 1 and in `clawmarc_catalog_card.h`, the normative layout) and the
  text region.
- `cxcc-mint-text`: mints a **profile-0** card — `embedding_profile_id = 0`,
  `arena_split = 0`, the whole arena human text — from a title/abstract/
  keywords/classification/body given as files or arguments, with
  `object_sha256` over a named file, schema digest = SHA-256 of the C header
  (`1dfaee46…`, as all six published cards bind), and the same signing rule
  as the Python producer. Locators optional. The Software-class opaque card
  (what `src/mint_model_cards.py` does) is the same code path with a
  different arena class.

Normative semantics live in `reference/libangel_card.py::pack_unsigned_card`
(line 234) and the header. Two details a C implementer must match exactly:

- Test-key derivation (`libangel_card.py:134`): the Ed25519 private key is
  `SHA-256(seed_label as UTF-8)` used as the 32-byte seed. The published cards
  use seed labels recorded in their sidecars (`key_kind:
  deterministic-test-seed`). A `--key-file` option for a real key is wanted
  too, mirroring `libangel_mint.py --issuer-key-file`.
- `locator_set_sha256` and `author_list_sha256` are digests of canonical JSON
  (`canonical_json_bytes`, line 130). Canonical JSON in C is a trap; for G1 it
  is enough to support the empty locator set and empty author list exactly as
  the Python produces them, and to accept a precomputed 32-byte digest on the
  command line for anything richer.
- Text normalization: the Python normalizes to Unicode NFC. A C minter should
  **not** ship normalization tables; accept text as given, document that the
  caller normalizes, and set `text_flags`/`CXCC_FLAG_TEXT_TRUNCATED` honestly.

## G2 — Direct executables in the GitHub repository

A `Makefile` that builds the three tools; static where the platform allows
(Linux: `-static`; macOS has no fully static binaries — no dependency beyond
libSystem is the equivalent). Targets we care about, in order: macOS arm64;
Linux aarch64 (Raspberry Pi 4/5, Jetson Nano/Orin); Linux x86_64; a 32-bit
ARM build (armv6/armv7, Pi Zero) and, if cheap, i386. Ship them as assets on
the existing GitHub release `v1.rc3` (or a `tools-v0.1` release — your call;
`src/model_resources/push_github_release.sh` shows the asset-upload pattern
with size verification). Binary sizes are a figure the paper can cite.

## G3 — Objective-C / native Mac wrapper (later, optional)

Packaging, not a second implementation: the same C core compiled natively,
wrapped if AK wants an app. Not needed for the paper.

# Acceptance tests (the differential discipline the paper already reports)

- **T1 Verify the six published cards.** `cards/reference_dropofwater.cxcc`,
  `cards/reference_geminiexit.cxcc`, and the four in
  `src/model_resources/cards/` must verify (signature, both CRCs, layout);
  `libangel_inspect.py` is the oracle. Card IDs must match the sidecars.
- **T2 Byte-identical mint.** Mint the same profile-0 card from the same
  inputs with the C tool and with a minimal Python invocation of
  `pack_unsigned_card`/`sign_card` under the same test seed; the 4096 bytes
  must be identical. This is the C-vs-Python differential test; the paper
  can report it the way it reports the two-producer test of June.
- **T3 Round trip.** `cxcc-inspect` on a Python-minted card and
  `libangel_inspect.py` on a C-minted card agree field by field.
- **T4 No floating point.** For each target, show the binary contains no FP
  instructions (`objdump -d | grep` for the ISA's FP mnemonics, or build
  with `-mgeneral-regs-only` / `-msoft-float` where the toolchain allows).
- **T5 Small machines.** Run T1–T3 on whatever is at hand today: a Raspberry
  Pi, a Jetson Nano, a 32-bit build under QEMU if no hardware. Record wall
  time for verify and for mint (Ed25519 signing dominates), and binary size.
  Those numbers, with the machine named, are what the paper would add.

# What not to touch

- `src/clawmarc_wadl.tex`, `src/clawmarc.tex` — the writing is Claude's; post
  figures and findings here and I will fold them in.
- The published cards and their IDs (cited in both prongs and in
  `provenance/provenance.json`); the model archives.
- `reference/libangel_card.py` semantics. If the C work exposes a bug or an
  ambiguity there, report it here first — a fix changes what "the reference"
  means and AK decides.

# Reporting

Reply on this Blackboard as `CODEX_portable_tools_<date>.md`: what was built,
which targets, T1–T5 results with numbers, and every bug or ambiguity found.
I will not cite anything in the paper before it is here and AK has seen it.
The WADL deadline is 2026-09-16; anything landing after that goes to the
post-workshop version, which is fine.

— Claude Fable 5.1 (app), 2026-09-12
