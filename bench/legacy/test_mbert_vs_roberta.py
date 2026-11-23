import time
import os
import torch
from sentence_transformers import SentenceTransformer
import random

def test_model(model_name, dummy_text):
    print(f"\n{'='*40}")
    print(f"Testing model: {model_name}")
    print(f"{'='*40}")
    
    t0 = time.time()
    try:
        model = SentenceTransformer(model_name)
    except Exception as e:
        print(f"Failed to load {model_name}: {e}")
        return
    print(f"Loaded model in {time.time() - t0:.2f}s")
    
    tokenizer = getattr(model, "tokenizer", None)
    if tokenizer is None:
        print(f"{model_name} did not expose a tokenizer")
        return

    print("Tokenizing...")
    t0 = time.time()
    original_model_max_length = getattr(tokenizer, "model_max_length", 512)
    tokenizer.model_max_length = max(original_model_max_length, 1_000_000)
    token_ids = tokenizer.encode(dummy_text, add_special_tokens=False)
    tokenizer.model_max_length = original_model_max_length
    t_tok = time.time() - t0
    total_tokens = len(token_ids)
    print(f"Tokenization took {t_tok:.2f}s for {total_tokens} tokens.")

    # Using max 480 tokens to leave room for special tokens (if any were added)
    max_body_tokens = 480
    chunks = [token_ids[i:i + max_body_tokens] for i in range(0, total_tokens, max_body_tokens)] or [[]]
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
    # using default batch size (32)
    chunk_vectors = model.encode(chunk_texts, normalize_embeddings=True, convert_to_numpy=True)
    t_enc = time.time() - t0

    throughput_tok_sec = total_tokens / t_enc
    time_per_page = 650 / throughput_tok_sec

    print("\n--- Throughput Results ---")
    print(f"Total tokens processed: {total_tokens}")
    print(f"Total encoding time: {t_enc:.2f} seconds")
    print(f"LLM Throughput: {throughput_tok_sec:.2f} tokens/second")
    print(f"Time per 650-token page: {time_per_page:.4f} seconds")


if __name__ == "__main__":
    # Generate 500,000 words dummy text (to keep download+test time reasonable)
    print("Generating large text sample (~500,000 words)...")
    words = ["the", "and", "of", "to", "that", "in", "he", "shall", "unto", "for", "i", "his", "a", "they", "be", "is", "not", "him", "them", "it", "with", "all", "thou", "thy", "was", "god", "which", "my", "me", "said", "but", "ye", "their", "have", "will", "thee", "from", "as", "are", "when", "this", "out", "were", "upon", "by", "you", "up", "israel", "there", "then"]
    dummy_text = " ".join(random.choices(words, k=500000))
    
    # We will test a standard Multilingual BERT and a standard XLM-RoBERTa
    # specifically tuned for sentence embeddings if available, or the base models
    models_to_test = [
        "bert-base-multilingual-cased",
        "xlm-roberta-base"
    ]
    
    for m in models_to_test:
        test_model(m, dummy_text)
