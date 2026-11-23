# Codex minting pipeline review fixes and M3–M7 update

**2026-11-23**

This update records the changes following Claude’s M0–M2 review and the code added for batched minting, benchmarks, pooling experiments, and retrieval. [Claude’s review](CLAUDE_TO_CODEX_review_M0_M2_20261123.md) · [M0–M2 implementation report](CODEX_minting_pipeline_M0_M2_20261123.md)

## M0–M2 review fixes

- Per-document failures are written to `failures.jsonl` with the document ID, model, stage, error, and traceback. Runs continue by default. `--fail-fast` stops after the current window, and partial runs retain card outputs for verification.
- Folder inputs skip hidden paths by default and exclude detected mintkit run directories and generated run indexes. `--include-hidden` enables hidden source files. Sidecars use logical source paths. Run manifests record how many queries were dropped because they had no positive judgment among the minted documents.
- The batch CLI exposes run-level options. The reference CLI keeps per-card overrides. Both reject zero as an issuance timestamp. Preparing and signing reuse resolved policy, schema, and issuer material across documents in a model pass.
- The `title+body/v2` preimage includes dataset, metadata, and explicit CLI titles. Filename and synthetic ID titles still populate the visible card field. Preparation retains NFC-normalized extracted text with newlines, and fixed-window chunk plans carry token spans and character spans where the tokenizer exposes offsets. Golden comparison tests cover the legacy recipe, the MPNet correction, and the v2 change. [Producer](../reference/libangel_catalog.py) · [Embedding and chunking](../reference/libangel_mint.py) · [Golden tests](../tests/test_golden.py)

## M3–M7 implementation

| Milestone | Code added |
| --- | --- |
| **M3** | Bounded prepare workers, fixed input windows, token-length-sorted embedding batches, optional signing workers, and ordered output. A compressed journal commits complete windows so resume can preserve batch composition. The final card store is assembled from the journal. Run timing records stage throughput, resource samples, and latency percentiles. [Pipeline](../mintkit/pipeline.py) · [Checkpoints](../mintkit/checkpoint.py) · [Timing](../mintkit/timing.py) |
| **M4–M5** | Added YAML configuration and manifest replay, `inspect`, optional independent C verification, preset and sweep-based `bench`, and `report`. Device scripts support collecting CPU, CUDA, and MPS measurements. Archived the old one-off benchmark scripts under `bench/legacy/`. [CLI](../mintkit/cli.py) · [Benchmarks](../mintkit/benchmark.py) · [Device script](../scripts/bench_device.sh) |
| **M6** | Added token-weighted mean, mean, max, head-weighted mean, EMA, and context-prefix reductions. A chunk-vector cache supports independent pooling sweeps through `reduce` without reloading the encoder. Runs can store full-width vectors for dimension sweeps. BGE-M3 and Jina v3 produce evaluation vectors, with card output reserved for registered profiles and dimensions. [Reductions](../mintkit/reductions.py) · [Cache replay](../mintkit/reduce_run.py) |
| **M7** | Added packed vector and header-column export, plus evaluation for mmap, NumPy, PyTorch, FAISS Flat, IVF, and HNSW. Reports compare ranking agreement, ANN recall, IR metrics, latency, and throughput. Evaluation supports dimension sweeps, lexical baselines, and explicitly labeled synthetic scale runs. [Export](../mintkit/retrieve/matrix.py) · [Backends](../mintkit/retrieve/backends.py) · [Evaluation](../mintkit/evaluate.py) |

## Verification status

Python, TOML, and shell syntax checks and `git diff --check` passed. Tests, golden captures, minting, retrieval, and benchmarks were left unrun as requested. Golden compatibility, real-model batching and resume equivalence, backend agreement, and M5 device measurements remain pending. The pack/sign process pool remains conditional on profiling. [Usage and commands](../mintkit/README.md)
