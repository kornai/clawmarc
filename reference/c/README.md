# Portable CXCC tools (layout 1.3)

`make` builds `cxcc-verify`, `cxcc-inspect`, and `cxcc-mint-text` with C99 and
libc only. On ARM64 hosts it adds `-mgeneral-regs-only` so the compiler emits
no FP/SIMD-register instructions. For other targets, select the toolchain's
integer-only option (for example `-msoft-float` on 32-bit ARM). `make test`
verifies the six checked-in cards. `make STATIC=1` requests a static link where the host toolchain
supports it (normally Linux; macOS uses libSystem). SHA-256, CRC-32, and
TweetNaCl Ed25519 are implemented in this source tree; there is no floating
point, parser, crypto-library, or runtime dependency.

Examples:

```
build/cxcc-verify cards/reference_dropofwater.cxcc --object bundle.zip
build/cxcc-inspect cards/reference_dropofwater.cxcc
build/cxcc-mint-text --object bundle.zip --out text.cxcc \
  --seed-label 'public deterministic test key' --issued 1782071790 \
  --work-created 1782071790 --work-revised 1782071790 --sequence 1 \
  --title 'A title' --abstract-file abstract.txt --class 27
```

Text options accept either `--title TEXT` (also abstract, keywords,
classification, body) or the corresponding `--*-file FILE`. The caller must
provide UTF-8 already normalized to NFC; this tool does not ship Unicode
normalization tables. It collapses ASCII whitespace, preserves UTF-8 bytes,
truncates only at UTF-8 code-point boundaries, and sets the NFC flag on that
caller assertion. Rich locator/author canonical-JSON digests can be supplied
with `--locator-sha256` and `--author-list-sha256`; otherwise the empty sets
are hashed in the same canonical shape used by the Python minting code. For
release signing, `--key-file` accepts a raw 32-byte Ed25519 seed or an
unencrypted PKCS#8 Ed25519 PEM key. `--seed-label` is deterministic and for
test use only. `--class 24` creates a Software-class opaque/profile-0 card;
the default class is Text (27).

The built-in schema digest binds the layout header as shipped in this
repository (`reference/clawmarc_catalog_card.h`, SHA-256
`1dfaee46853b9b3e4c2786ac7b730cc393967ac8444ecbf556967e73ef4d86f1`).

The vendored TweetNaCl source is the public-domain implementation by Daniel
J. Bernstein, Wesley Janssen, Tanja Lange, and Peter Schwabe, obtained from
`https://github.com/dominictarr/tweetnacl/blob/master/tweetnacl.c`; this tree
adds deterministic seed-key setup using TweetNaCl's existing Ed25519 core.
The SHA-256 implementation here is dedicated to the public domain.
