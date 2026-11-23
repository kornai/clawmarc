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
print(f"Selected {len(sample_files)} books.\n")

model_name = "bert-base-multilingual-cased"
print(f"Loading model: {model_name}")
try:
    model = SentenceTransformer(model_name)
except Exception as e:
    print(f"Failed to load {model_name}: {e}")
    exit(1)
    
tokenizer = getattr(model, "tokenizer", None)
original_model_max_length = getattr(tokenizer, "model_max_length", 512)

total_tokens_all = 0
total_time_all = 0

for i, f in enumerate(sample_files, 1):
    name = os.path.basename(f)
    print(f"\n--- [{i}/{len(sample_files)}] Processing: {name} ---")
    
    t0_ext = time.time()
    txt = get_text_from_file(f)
    t_ext = time.time() - t0_ext
    print(f"Extracted {len(txt)} chars in {t_ext:.2f}s.")
    
    if not txt.strip():
        print("No text extracted, skipping.")
        continue
        
    t0_tok = time.time()
    tokenizer.model_max_length = max(original_model_max_length, 1_000_000)
    token_ids = tokenizer.encode(txt, add_special_tokens=False)
    tokenizer.model_max_length = original_model_max_length
    t_tok = time.time() - t0_tok
    total_tokens = len(token_ids)
    print(f"Tokenized {total_tokens} tokens in {t_tok:.2f}s.")
    
    if total_tokens == 0:
        continue
        
    max_body_tokens = 480
    chunks = [token_ids[i:i + max_body_tokens] for i in range(0, total_tokens, max_body_tokens)] or [[]]
    
    chunk_texts = [
        tokenizer.decode(chunk, skip_special_tokens=True, clean_up_tokenization_spaces=False)
        for chunk in chunks
    ]
    
    t0_enc = time.time()
    chunk_vectors = model.encode(chunk_texts, normalize_embeddings=True, convert_to_numpy=True)
    t_enc = time.time() - t0_enc
    
    throughput = total_tokens / t_enc if t_enc > 0 else 0
    print(f"Embedded in {t_enc:.2f}s (Throughput: {throughput:.2f} tok/s).")
    
    total_tokens_all += total_tokens
    total_time_all += t_enc

print("\n=========================================")
print("FINAL RESULTS OVER ALL 10 DOCUMENTS")
print("=========================================")
print(f"Total tokens processed: {total_tokens_all}")
print(f"Total embedding time: {total_time_all:.2f} seconds")
if total_time_all > 0:
    global_throughput = total_tokens_all / total_time_all
    print(f"Average LLM Throughput: {global_throughput:.2f} tokens/second")
    print(f"Average time per 650-token page: {650 / global_throughput:.4f} seconds")
