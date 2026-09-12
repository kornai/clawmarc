# LLM Throughput Analysis: Rethinking the 100k Character Limit

## Background
The current content policy (`public_library_science`) enforces a `max_text_prefix_chars` limit of 100,000 characters. As noted, this artificial limit poses a problem for large texts (like the Bible or large anthologies), as the trailing text is truncated and never contributes to the document vector. The assumption was that embedding the full text would be computationally prohibitive.

## The Experiment
To test this assumption, I wrote a synthetic benchmark (`test_llm_throughput.py`) to measure the exact token-processing bandwidth of the reference LLM (`BAAI/bge-small-en-v1.5`) without the character limit.

I generated a realistic dummy text of **1,000,000 tokens** (roughly the size of the Bible, or ~1,500 standard pages) and ran it through the model's chunking (480 tokens) and pooling pipeline.

## Results
- **Tokenization:** 1,000,000 tokens were processed in **1.84 seconds**.
- **Embedding / Vectorization:** The 1,000,000 tokens (divided into 2,084 chunks) were embedded in **51.66 seconds**.
- **Throughput Rate:** **~19,357 tokens per second**.
- **Time per Page:** **0.033 seconds per 650-token page**.

*(Note: Increasing the batch size from 32 to 128 slightly degraded performance to ~16,000 tok/sec, confirming the default chunking pipeline is well-optimized for the local M2 hardware).*

## Conclusion
The LLM inference compute is **not a bottleneck**. 

Embedding the *entirety* of a text the size of the Bible takes less than one minute on your local hardware. The 100,000 character limit is computationally unnecessary and artificially degrading the quality of vectors for long books. 

**Recommendation:** We should modify the content policies (specifically `public_library_science`) to either significantly increase `max_text_prefix_chars` (e.g., to 10,000,000) or remove it entirely for local offline processing. This will ensure that all content, from Genesis to Revelation, is represented in the resulting vectors.