# Codex minting pipeline M0–M2 report

**2026-11-23**

The serial `mintkit` pipeline is implemented. It loads documents, queries, and relevance judgments through a shared source interface and writes a local run of signed ClawMARc cards.

- **M0 — Producer and setup.** Split the reference producer into preparation, embedding, and packing/signing. Fixed the default schema path and made chunk size respect the model window, including MPNet’s 126 body tokens. Added package setup and a utility for capturing baseline cards from `0b52701`. [Reference producer](../reference/libangel_catalog.py) · [Embedding code](../reference/libangel_mint.py) · [Baseline capture](../tests/golden/make_golden.py)
- **M1 — Dataset loaders.** Implemented `Source`, `Doc`, `Query`, and `Qrels` before adding adapters for local folders, MLDR, BEIR, and MS MARCO Passage. Folder inputs accept optional query and judgment TSVs. MLDR supports the full corpus and split positives, with local files preferred and missing files fetched on demand. All adapters share `all`, `first:N`, `random:N`, `qrels:Q[+D]`, and `ids:FILE` sampling. [Source interface](../mintkit/sources/base.py) · [Source registry](../mintkit/sources/__init__.py)
- **M2 — Serial CLI and storage.** Added `sources`, `mint`, and `verify`. A run writes a manifest, signed 4,096-byte cards, indexes, sidecars, SHA-256 checksums, and query and judgment files when available. Judgments are filtered to sampled document IDs. Shards are the default, and `--layout files` writes individual cards. Run sidecars record the embedding preimage digest by default. `--include-preimage` saves the full text used for embedding. [Pipeline](../mintkit/pipeline.py) · [Storage and verification](../mintkit/store.py) · [Usage](../mintkit/README.md)

## Verification status

Static syntax and formatting checks passed. Tests, minting runs, and golden captures were left unrun as requested. Runtime verification and byte-for-byte comparison with the baseline are pending.
