import time
import os
import struct
import numpy as np
from sentence_transformers import SentenceTransformer
import random

model_name = "BAAI/bge-small-en-v1.5"
print(f"Loading {model_name}...")
model = SentenceTransformer(model_name)
tokenizer = getattr(model, "tokenizer", None)
if tokenizer is None:
    raise SystemExit(f"{model_name} did not expose a tokenizer")

# Generate a large realistic-looking text to avoid any potential caching/optimization anomalies.
# The Bible is roughly 800,000 words. Let's generate a text of about 1 million words.
print("Generating large text sample (~1 million words)...")
words = ["the", "and", "of", "to", "that", "in", "he", "shall", "unto", "for", "i", "his", "a", "they", "be", "is", "not", "him", "them", "it", "with", "all", "thou", "thy", "was", "god", "which", "my", "me", "said", "but", "ye", "their", "have", "will", "thee", "from", "as", "are", "when", "this", "out", "were", "upon", "by", "you", "up", "israel", "there", "then"]
# just repeat this a lot to get enough words
dummy_text = " ".join(random.choices(words, k=1000000))

print("Tokenizing...")
t0 = time.time()
original_model_max_length = getattr(tokenizer, "model_max_length", 512)
tokenizer.model_max_length = max(original_model_max_length, 1_000_000)
token_ids = tokenizer.encode(dummy_text, add_special_tokens=False)
tokenizer.model_max_length = original_model_max_length
t_tok = time.time() - t0
print(f"Tokenization took {t_tok:.2f}s for {len(token_ids)} tokens.")

max_body_tokens = 480
chunks = [token_ids[i:i + max_body_tokens] for i in range(0, len(token_ids), max_body_tokens)] or [[]]
print(f"Created {len(chunks)} chunks of size up to {max_body_tokens}.")

t0 = time.time()
chunk_texts = [
    tokenizer.decode(chunk, skip_special_tokens=True, clean_up_tokenization_spaces=False)
    for chunk in chunks
]
t_dec = time.time() - t0
print(f"Decoding chunks took {t_dec:.2f}s.")

print("Encoding chunks through the LLM...")
t0 = time.time()
# The encode method batches inputs automatically. We can let it use its default batch_size (typically 32).
chunk_vectors = model.encode(chunk_texts, normalize_embeddings=True, convert_to_numpy=True)
t_enc = time.time() - t0

total_tokens = len(token_ids)
throughput_tok_sec = total_tokens / t_enc
time_per_page = 650 / throughput_tok_sec

print("\n--- Throughput Results ---")
print(f"Total tokens processed: {total_tokens}")
print(f"Total encoding time: {t_enc:.2f} seconds")
print(f"LLM Throughput: {throughput_tok_sec:.2f} tokens/second")
print(f"Time per 650-token page: {time_per_page:.4f} seconds")

# Also measure with a larger batch size to see if throughput improves
print("\nTesting with batch_size=128...")
t0 = time.time()
chunk_vectors_128 = model.encode(chunk_texts, batch_size=128, normalize_embeddings=True, convert_to_numpy=True)
t_enc_128 = time.time() - t0
throughput_tok_sec_128 = total_tokens / t_enc_128
time_per_page_128 = 650 / throughput_tok_sec_128
print(f"Total encoding time (batch=128): {t_enc_128:.2f} seconds")
print(f"LLM Throughput (batch=128): {throughput_tok_sec_128:.2f} tokens/second")
print(f"Time per 650-token page (batch=128): {time_per_page_128:.4f} seconds")
