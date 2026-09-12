# Clawmarc/WADL restart handoff — 2026-09-10

This note is intended to let a fresh session resume the work without
reconstructing the conversation.

## Current paper state

- Reviewer-facing paper: `src/clawmarc_wadl.tex`.
- Original pre-edit backup: `src/clawmarc_old.tex`; preserve it.
- Compiled PDF: `src/clawmarc_wadl.pdf`; the latest edit compiles successfully
  with ordinary LaTeX warnings only.
- NewReuters5000 results **have been added** to the paper. The section reports
  5,000 documents, 100 topic-proxy queries, and proxy MAP: MPNet 0.520,
  BGE-small 0.500, mBERT 0.456, BM25 0.442, TF--IDF 0.440, XLM-R 0.369.
  It also reports mBERT P@10 0.579 versus BM25 0.736 and TF--IDF 0.711, and
  correctly treats the first-pass-selector interpretation as provisional.
- Cranfield results are also in the paper: BGE-small MAP 0.329, BM25 0.274,
  TF--IDF 0.259, MPNet 0.248, mBERT 0.073, XLM-R 0.019.
- The paper has been rewritten toward a scholarly, non-panacea claim: the
  contribution is a uniform, content-bound catalog substrate that permits
  future retrieval methods and later bitrot/availability audits.
- The AI substantive-work disclosure is in the acknowledgments and the
  provenance record; submission authorship remains András Kornai alone.

## Model archives and cards

`src/model_resources/` contains four `.tar.zst` archives (2.3 GB total),
`SHA256SUMS`, four signed text-only Software cards and JSON sidecars, a card
index, and the README. The card payloads have no document vectors. Each card's
signed `object_sha256` matches its complete archive byte stream.

The archive-to-IPFS mapping is in `src/model_resources/IPFS_CIDS.tsv`:

```text
bert-base-multilingual-cased.tar.zst bafybeifcdyij2s76mjyq4dz6ewhylshabirarix3hlpssm2az2ll6qdozy
bge-small-en-v1.5.tar.zst bafybeigayb3vbhwjzl7oegaq3o6rveczpqwepl3ujp6cwyfknpgdb3ajdq
paraphrase-multilingual-mpnet-base-v2.tar.zst bafybeiaj5xm2znmqajxzh76rpdvq76pdartldy3g64zmarcdyafgsen5ea
xlm-roberta-base.tar.zst bafybeie2yxjx476trpufwly63cxoav7yyem6knbcqj7iu4l3zynz652rlu
```

The user ran `push_ipfs.sh` on Kubo 0.43.0 and had 147 swarm peers. The
archives are locally pinned. Remaining IPFS work:

1. Run `ipfs cat CID | shasum -a 256` for all four and compare with
   `SHA256SUMS`.
2. Re-mint the four cards with the IPFS CIDs in the locator fields.
3. Publish the final cards/sidecars and archives at the two HTTPS locations.

Swarm has not been checked or uploaded. Determine whether an existing Bee
postage batch has sufficient capacity and duration for about 2.3 GB. If not,
the user must arrange a suitable funded stamp. After Swarm references exist,
re-mint the cards again so the final signed cards contain both IPFS and Swarm
locators. Do not treat the current HTTPS-only cards as the final locator-rich
release.

The two HTTPS hosts could not be resolved from the Codex environment, and a
read-only SSH inspection of `kornai.homeip.net` was aborted. The user will
perform the web upload.

## Transportability probe

`src/transport_probe/` is a complete card-only Linux probe with `Makefile`,
`probe.py`, `test_probe.py`, and `README.md`.

```sh
make test PYTHON=/path/to/python-with-cryptography
make install PREFIX="$HOME/.local"
```

The probe verifies card size, CRCs, Ed25519 signatures, embedding digests, and
ranking equivalence from transported binary16 vectors. It does not yet test
cross-machine neural inference. The current card-only probe was the intended
first arm; a later runtime arm may transfer all four model directories,
preimages, and reference vectors, then measure cross-machine cosine drift.

Before the Linux test, select a nontrivial same-profile card corpus and query
card, create an M1 reference JSON with `probe.py --write-reference`, and
transfer the probe source, cards, query, and reference JSON. The current
`cards/` directory contains a no-embedding reference card, so it is not a
suitable corpus for the ranking test without selecting or minting additional
same-profile cards.

## Other pending work

- Final scholarly pass over `clawmarc_wadl.tex`, especially page balance,
  citations, profile/specification synchronization, and whether the NewReuters
  proxy results deserve a table.
- Optionally add an explicit card-only transportability paragraph after the
  Linux run; add the runtime-drift experiment only if time permits.
- Prepare an arXiv version only after experiments and the WADL text stabilize;
  ask WADL organizers about simultaneous arXiv posting and the non-exclusive
  repository license.

