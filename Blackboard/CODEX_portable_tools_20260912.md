# Codex portable-tools report — 2026-09-12

## Outcome

Implemented a dependency-free C99 profile-0 card toolset in `reference/c/`:
`cxcc-verify`, `cxcc-inspect`, and `cxcc-mint-text`. The code is staged for the
project; it does not change the paper, published cards, their IDs, or model
archives. The six published cards verify, a profile-0 card is byte-identical
to the Python oracle, and inspector fields agree. ARM64 was tested on an M2
Mac. No 32-bit runtime or cross sysroot was available, so 32-bit execution is
not claimed as measured.

## Implementation

- `cxcc.c`: layout-1.3 verification, inspection, and profile-0 text minting.
- `sha256.c/.h`: integer-only SHA-256; CRC-32 is implemented in the core.
- `tweetnacl.c/.h`: public-domain TweetNaCl Ed25519, with deterministic
  seed-key setup for test labels.
- `Makefile`: builds the three executables; ARM64 builds use
  `-mgeneral-regs-only`; `make test` verifies the six checked-in cards.
- `README.md`: command examples and text/key constraints.

The verifier enforces 4096-byte length, magic, exact layout 1.3, arena-split
bounds, declared reserved-zero fields, both CRCs, and Ed25519 over the full
working card with the signature slot zeroed. `--object FILE` adds the object
SHA-256 check. The minter supports profile 0, class Text by default or
Software via `--class 24`, object hashing, the repository schema digest,
deterministic test labels or unencrypted PKCS#8 Ed25519 PEM, text arguments
or files, and caller-supplied richer locator/author digests.

## Acceptance tests

- **T1 — published cards:** all six cards passed C verification. Their card
  IDs also matched their JSON sidecars. The four model cards additionally
  passed `--object` against their corresponding local `.tar.zst` archives.
- **T2 — differential mint:** C and Python `pack_unsigned_card`/`sign_card`
  outputs compared byte-for-byte equal (4096/4096 bytes) for a profile-0 card,
  with fixed timestamps, sequence, text, object, schema, and deterministic
  test seed.
- **T3 — inspection:** C inspection of that C-minted card matched Python
  `unpack_basic` on 26 fields, including identity hashes, flags, text hashes,
  and all text segments. No mismatches.
- **Additional edge checks:** a real Ed25519 PKCS#8 PEM generated from the
  differential key produced the same card as the seed-label path. A 2,817-byte
  UTF-8 abstract ending in a partial three-byte character truncated to the
  same 2,814-byte boundary as Python, with the truncation flag set; the cards
  were byte-identical.
- **T4 — floating point:** macOS arm64 binary built with
  `-mgeneral-regs-only`; disassembly showed no FP or SIMD-register
  instructions under the checked mnemonic/register patterns. The resulting
  Mach-O executable is 70,104 bytes. The three built tools are copies of the
  same core binary.
- **T5 — performance/platform:** on the available Apple M2 Mac (Darwin arm64),
  process-inclusive medians over 100 verifications and 30 mints were 3.171 ms
  and 3.342 ms respectively. These are host measurements, not 32-bit or SBC
  figures. No Raspberry Pi, Jetson, QEMU, ARM Linux cross compiler, or ARM
  Linux sysroot was available. A direct ARMv7 compile attempt stopped at
  missing target `stdio.h`; static Linux artifacts were therefore not built.

## Paper review and external-resource check

The rewrite meets the substance of the prior review objections: ACM reference
metadata is enabled; the public version/reproducibility declaration is now
explicit; test-seed signatures are clearly called forgeable and not issuer
identity; manifest binding is conditional rather than implied; fixed-size
benefits are described as affordances with realistic alternatives; NewReuters
is consistently labeled proxy-MAP; and model identity versus vector/runtime
reproducibility is separated. The new portability paragraph likewise leaves
32-bit and single-board measurements as future work. The C implementation
supports the source-level/no-FP rationale, but the paper should not imply that
a 32-bit executable or measured small-device result already exists.

The route-recheck log records all four model archives byte-exact on its HTTP
(Lebadus), IPFS, and Swarm routes. The public GitHub `v1.rc3` release was
checked in the current session: it exposes the four archives, four cards and
sidecars, `CARD_INDEX.md`, `PUBLISH_MANIFEST.md`, and `SHA256SUMS`. Its upload
log records server-side size verification, but not a full remote re-download
and SHA-256 check of the 2.2-GB archive set. Thus the paper's phrase “on every
route” is stronger than the logs establish for GitHub; either run that full
check or narrow the sentence to the verified routes. At the Lebadus endpoint
the archive URLs were reachable, but the checksum manifest and cards were not
yet mirrored at the time checked; the paper accurately says those are “being
mirrored.” The directory also still lists the older
`paraphrase-multilingual-mpnet-base-v.tar.zst` alongside the `-v2` archive;
label or remove the superseded file when updating that mirror.

One implementation boundary to preserve in any paper update: the C minter
does not ship Unicode normalization tables. Its documentation requires
already-NFC UTF-8 input, collapses ASCII whitespace, and truncates on UTF-8
code-point boundaries. Python collapses Unicode whitespace more broadly, so
byte-identical differential claims apply to normalized inputs within that
documented behavior. The compiled-in schema digest must be updated if the
normative header changes.

## Release boundary

Source and report are ready in the local project tree. No GitHub commit, tag,
release-asset upload, paper edit, or card rewrite was made. The requested
cross-platform release assets should wait for 32-bit/Linux builds and explicit
publication approval.

## Outstanding actions for AK before submission

### Close before the final PDF

1. **Resolve the “every route” checksum sentence** in `src/clawmarc_wadl.tex`
   (reproducibility declaration, around lines 695–702). The saved byte-exact
   route log covers Lebadus HTTP, IPFS, and Swarm. The GitHub release log
   records asset presence and server-side sizes, not full downloaded hashes.
   Either download each of the four GitHub archive assets and verify against
   `SHA256SUMS`, or narrow the sentence to the routes actually hash-verified.
2. **Recheck the Lebadus mirror state.** At the last check, archive URLs were
   reachable, but `SHA256SUMS`, the four cards, sidecars, index, and manifest
   were not mirrored there. The paper currently says these “are being
   mirrored,” which is appropriately limited; retain that tense unless you
   complete and verify the mirror. The old
   `paraphrase-multilingual-mpnet-base-v.tar.zst` was still listed alongside
   the canonical `-v2` file; remove it or label it superseded.
3. **Ask Gemini to assess the portability wording** in the fixed-size section
   (around lines 300–315) against the evidence here: ARM64/M2 only; no 32-bit,
   Linux, Pi, Jetson, or QEMU build/run. Keep the 32-bit and small-board
   statements explicitly at the design/portability-rationale level, not as
   measured results. If that distinction is already unmistakable, no wording
   change is needed.
4. **Run the final paper build and inspect the PDF visually.** The earlier
   temporary build succeeded, but had an overfull reproducibility paragraph
   warning and a `balance` warning. Decide whether the overfull line actually
   crosses the margin; confirm page count, ACM reference strip, citations,
   and links in the final artifact.

### Required only if the C tools are to be a public submission artifact

5. **Publish the new `reference/c/` source in an immutable repository
   snapshot** and make the submitted bundle/GitHub reference point to that
   snapshot. These files exist locally but are not in the already-published
   `v1.rc3` release or its current GitHub commit.
6. **Build and test release binaries for the promised targets:** at minimum
   Linux x86-64 and aarch64; then 32-bit ARM (and i386 if feasible). Run T1–T3
   on a real small machine or QEMU, record exact compiler/flags, binary sizes,
   and timings, then upload assets only after reviewing the resulting
   checksums. The M2 measurements in this report are not substitutes.
7. **Preserve the C text-input boundary in user-facing documentation:** the
   caller supplies NFC UTF-8; the C tool collapses ASCII (not all Unicode)
   whitespace and does not perform normalization. The current README says
   this; recheck it if the files are copied into a different public bundle.

No published card, sidecar, paper source, or model archive needs to be
rewritten to complete the C implementation. The only known paper edit
potentially required by the checks above is narrowing the GitHub “every
route” claim if a full GitHub hash check is not run.
