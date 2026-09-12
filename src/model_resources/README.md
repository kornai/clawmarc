# Clawmarc model resources

These are the four model directories used in the Clawmarc retrieval
experiments, packaged as opaque `.tar.zst` artefacts. Each archive has a
separate 4096-byte signed Clawmarc card in `cards/`. The card's
`object_sha256` is the SHA-256 of the complete compressed archive; the
card is therefore the authoritative integrity binding. `SHA256SUMS` is a
convenience manifest for download verification.

The cards deliberately contain no document vectors. Their arena contains a
human-readable model description, while the artefacts themselves are opaque
binary model resources. These are the **root cards** for the four models:
each carries three locators for the identical bytes — an HTTPS hint, an IPFS
CIDv1, and a Swarm reference — in both the signed card and its `.cxcc.json`
sidecar. `CARD_INDEX.md` tabulates the card IDs and all three locators.

The sole authentic HTTPS source is `https://lebadus.ai/Resources/Models/`.
An earlier mirror on `kornai.homeip.net` was dropped (unreliable storage);
it is no longer listed as an authentic source in the cards.

Files to publish in the Models directory are the four `.tar.zst` archives,
`SHA256SUMS`, and the four `.cxcc` cards with their `.cxcc.json` sidecars.
`IPFS_CIDS.tsv` and `SWARM_REFS.tsv` record the network locators folded into
the cards at mint time.

To add and pin all four archives to a running local Kubo node in one operation:

```sh
./push_ipfs.sh
```

This writes `IPFS_CIDS.tsv`, which should be sent back to the card minting
workflow. The script uses CIDv1, raw UnixFS leaves, and a 1-MiB chunker.
