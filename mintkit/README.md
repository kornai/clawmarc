# mintkit

Mint signed 4,096-byte ClawMARc catalog cards from local files or retrieval datasets. Each run records its inputs and settings and writes cards, sidecars, indexes, and checksums.

From the repository root, install the package into a Python 3.12 or newer environment:

```sh
python -m pip install -e '.[embed,mldr,msmarco,images]'
```

The base package supports text-only runs with `--no-embed`. The extras supply embedding models, remote dataset access, and image previews. PDF extraction uses `pdftotext`, HTML and EPUB extraction use `pandoc`, and Word extraction uses `docx2txt` or `catdoc`.

| Source | Documents | Query and judgment inputs |
| --- | --- | --- |
| `folder:PATH` | Recursive local files, with POSIX relative paths as IDs | Optional `queries.tsv` and `qrels.tsv`, or `--queries` and `--qrels` |
| `mldr:LANG` | Stream the full corpus or use `--mode positives` for the split’s positive passages | `train`, `dev` (default), `test`. Reads local files under `data/mldr/mldr-v1.0-LANG/` first and fetches missing files on demand |
| `beir:PATH_OR_NAME` | Local `corpus.jsonl`. Names resolve under `data/beir/` when no matching path exists | `queries.jsonl` and `qrels/SPLIT.tsv`. Defaults to `test` when present |
| `msmarco:passage` | Passage corpus provided by `ir_datasets` | `train`, `dev/small` (default), `trec-dl-2019`, `trec-dl-2020` |

```sh
python -m mintkit sources mldr:en
python -m mintkit mint folder:./docs --glob '*.txt' --no-embed
python -m mintkit mint mldr:en --split dev --mode positives --sample random:10 --models bge mbert mpnet
python -m mintkit mint beir:scifact --split test --sample qrels:10+50 --models bge
python -m mintkit mint msmarco:passage --split dev/small --sample first:100 --models bge
python -m mintkit verify runs/RUN_ID
```

Sampling supports `all`, `first:N`, `random:N`, `qrels:Q[+D]`, and `ids:FILE`. The qrels sampler keeps every positive document for the selected queries and adds the requested number of random distractors. It reports an error if the corpus has too few. The ID file uses one ID per line. Use `--split none` for a document-only run.

Folder queries use two TSV columns, query ID and text. Folder qrels use three TSV columns, query ID, document ID, and integer relevance. The run writes the selected query texts and filters qrels to document IDs in the sample.

The runner processes one model at a time. Shards are the default. `--layout files` writes individual `.cxcc` cards and `.cxcc.json` sidecars, with an index mapping files to document IDs. Run sidecars record a digest of each embedded preimage. Use `--include-preimage` to store the full text used for embedding. `--issued-unix` sets an explicit timestamp for repeatable card production.

## Batch minting and checkpoints

Minting uses ordered prepare workers, one embedding device, optional signing workers, and a single writer. Tune `--prep-workers`, `--sign-workers`, `--batch-chunks`, `--sort-window`, and `--max-inflight`. Use `--threads 0` to encode one document at a time. `--text-cache-mb` controls how much prepared text can be reused across model passes. Sampling streams the dataset again for each model.

A checkpoint commits a whole input window. Resume reopens the source in its recorded working directory and checks the committed windows before advancing. The journal and final store can temporarily occupy disk at the same time. Document errors are recorded in `failures.jsonl`. With `--fail-fast`, the run finishes the current window and stops. Run identity includes model settings, issuance time, runtime versions, and code digests. Byte comparisons require the same inputs, settings, model files, timestamp, and runtime environment.

Folder sources skip hidden paths and detected mintkit run directories. Use `--include-hidden` when hidden input paths are intended. Embedded preimages use `title+body/v2` with titles from metadata, datasets, or the reference CLI. Filename and ID fallbacks still populate the card title.

```sh
python -m mintkit mint --resume runs/RUN_ID
python -m mintkit mint --config run.yaml
python -m mintkit mint --config runs/RUN_ID/manifest.json
python -m mintkit inspect runs/RUN_ID --card 0
python -m mintkit verify runs/RUN_ID --c
python -m mintkit bench mldr-200 --device cpu --sweep batch_chunks=32,64
python -m mintkit report benchmarks/results.csv
```

## Reduction and retrieval experiments

```sh
python -m mintkit mint mldr:en --mode positives --sample qrels:10+90 --models bge --keep-chunk-vectors --keep-full-text
python -m mintkit reduce runs/RUN_ID --reductions ema:alpha=0.3 ema:alpha=0.7 mean max
python -m mintkit export runs/RUN_ID
python -m mintkit eval runs/RUN_ID --backends mmap numpy torch faiss-flat faiss-ivf faiss-hnsw --dims 384,256
python -m mintkit eval runs/RUN_ID --backends mmap numpy --scale-to 1000000 --no-lexical
```

The `faiss` extra enables FAISS backends. Native card dimensions use the registered profiles. BGE-M3 and Jina v3 produce vectors for evaluation. Jina v3 requires an explicit remote-code opt-in and a pinned commit or local snapshot. The lexical baseline can read card text and extracted text kept by `--keep-full-text`. Synthetic scale runs add perturbed vectors, retain the original documents, and label the measurements as synthetic.
