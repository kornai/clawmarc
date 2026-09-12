import time
import os
import random
import subprocess
from sentence_transformers import SentenceTransformer

OTHER_DIR = "/Volumes/114/Other"

def get_text_from_file(path):
    suffix = path.lower().split('.')[-1]
    text = ""
    try:
        if suffix == "pdf":
            proc = subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True, timeout=60)
            text = proc.stdout
        elif suffix == "epub":
            proc = subprocess.run(["pandoc", "--from", "epub", "--to", "plain", path], capture_output=True, text=True, timeout=60)
            text = proc.stdout
    except Exception as e:
        print(f"Extraction failed for {path}: {e}")
    return text

print("Finding books in ~/Other...")
book_files = []
for root, _, files in os.walk(OTHER_DIR):
    for f in files:
        if f.lower().endswith((".pdf", ".epub")):
            path = os.path.join(root, f)
            try:
                if os.path.getsize(path) > 2 * 1024 * 1024:
                    book_files.append(path)
            except OSError:
                pass

sample_files = random.sample(book_files, min(10, len(book_files)))
print(f"Selected {len(sample_files)} books. Extracting text (this may take a moment)...")

real_texts = []
for f in sample_files:
    print(f"Extracting {os.path.basename(f)}...")
    txt = get_text_from_file(f)
    if txt:
        real_texts.append(txt)

real_text = "\n".join(real_texts)
print(f"Total extracted characters: {len(real_text)}")
if not real_text.strip():
    print("No text was extracted. Exiting.")
    exit(1)

model_name = "bert-base-multilingual-cased"
print(f"\nLoading model: {model_name}")
try:
    model = SentenceTransformer(model_name)
except Exception as e:
    print(f"Failed to load {model_name}: {e}")
    exit(1)
    
tokenizer = getattr(model, "tokenizer", None)

print("Tokenizing...")
t0 = time.time()
original_model_max_length = getattr(tokenizer, "model_max_length", 512)
tokenizer.model_max_length = max(original_model_max_length, 1_000_000)
token_ids = tokenizer.encode(real_text, add_special_tokens=False)
tokenizer.model_max_length = original_model_max_length
t_tok = time.time() - t0
total_tokens = len(token_ids)
print(f"Tokenization took {t_tok:.2f}s for {total_tokens} tokens.")

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
chunk_vectors = model.encode(chunk_texts, normalize_embeddings=True, convert_to_numpy=True)
t_enc = time.time() - t0

if t_enc > 0:
    throughput_tok_sec = total_tokens / t_enc
    time_per_page = 650 / throughput_tok_sec
else:
    throughput_tok_sec = 0
    time_per_page = 0

print("\n--- Throughput Results (Real Text) ---")
print(f"Total tokens processed: {total_tokens}")
print(f"Total encoding time: {t_enc:.2f} seconds")
print(f"LLM Throughput: {throughput_tok_sec:.2f} tokens/second")
print(f"Time per 650-token page: {time_per_page:.4f} seconds")