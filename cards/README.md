# Reference cards (layout 1.3)

Two cards minted by the reference producer, for checking an independent
implementation. Layout 1.2 versions of the same cards (draft -00/-01 class
numbers) are kept in `../Attic/cards_layout_1.2/` for the record.

- `reference_dropofwater.cxcc` — a ClawXiv bundle (`joint_bundle.zip`,
  Two Drops of Water v2) with a profile-1 document vector (arena_split 768)
  and a truncated body prefix. arena_class 27 (dcmitype:Text).
- `reference_geminiexit.cxcc` — a shell script cataloged as a general file,
  no vector (arena_split 0), text prefix only. arena_class 27.

What an independent implementation should reproduce, given the same
artefact bytes and the same content policy:

1. **Byte-identical** every field the specification pins: magic, layout,
   arena_class, arena_split, size_class, object_sha256, schema_sha256,
   embedding_profile_id, text lengths, and (with the deterministic issuer
   seed in `libangel_mint.py`) the issuer key and signature. That seed is
   public, so it is a **test key**: the signature proves that a card is
   reproducible, not who issued it (the sidecar says `key_kind:
   deterministic-test-seed`). Cards published for consumption are signed
   with a private key file (`libangel_mint.py --issuer-key-file`) whose
   public half is distributed through an authenticated channel.
2. **The human text** byte-identical when the same extractor and
   normalization (Unicode NFC, whitespace collapse) are used; otherwise
   `text_sha256` will differ and the JSON sidecar says which extractor ran.
3. **The document vector** compared by cosine, not bytes. Same preimage
   text through the same model gives cosine > 0.9999 (fp16 noise). A
   different extractor over the same artefact typically lands near 0.99.
   Values around 0.93 or below indicate a different preimage, not a
   different model; look at the text first. The 2026-06-22 differential
   test measured exactly these three levels (0.9999999999 / 0.989 / 0.932).

The `.cxcc.json` sidecars record extraction policy, chunking, and the
embedding preimage so that a divergence can be located.
