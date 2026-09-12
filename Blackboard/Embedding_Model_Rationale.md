# Rationale for `bge-small-en-v1.5` vs Multilingual BERT/RoBERTa

The initial selection of `bge-small-en-v1.5` over a standard Multilingual BERT (`bert-base-multilingual-cased`) or RoBERTa (`xlm-roberta-base`) model was driven by the **4096-byte layout constraints** of the `clawmarc` card, though this is subject to revision based on updated design priorities.

## The Mathematical Constraint
A standard `clawmarc` card has exactly 4096 bytes.
- **Header:** 1216 bytes (fixed).
- **Footer:** 64 bytes (fixed CRCs).
- **Arena:** 2816 bytes remaining.

This 2816-byte arena must hold *both* the human-readable text prefix (title, abstract, body snippet) and the machine-readable document vector.

## Dimensionality and Byte Cost

1. **`BAAI/bge-small-en-v1.5` (Current Choice)**
   - **Dimensions:** 384
   - **Data Type:** IEEE-754 `binary16` (half-precision floats)
   - **Total Size:** 384 * 2 = **768 bytes**.
   - **Result:** Leaves **2048 bytes** for the human-readable text prefix.

2. **Standard BERT / RoBERTa (e.g., `xlm-roberta-base`)**
   - **Dimensions:** 768
   - **Data Type:** `binary16` (half-precision floats)
   - **Total Size:** 768 * 2 = **1536 bytes**.
   - **Result:** Leaves **1280 bytes** for the text prefix. (Note: 32-bit floats would take 3072 bytes, exceeding the arena).

## Author's Stance on Space Allocation (Update 2026-09-07)
While the current `bge-small` profile preserves a large human-readable text prefix, the author explicitly notes that **spending more of the arena on the machine vector is an acceptable tradeoff.** 

Therefore, a 768-dimensional multilingual model is a highly viable candidate for a future embedding profile. Consuming 1536 bytes for a superior, globally applicable vector and leaving 1280 bytes for the human-readable text is considered a sound architectural choice, prioritizing machine-driven information retrieval over human-readable verbosity on the card itself.