import os
import sys
import time
import subprocess
import glob
import json
import random
from pathlib import Path

OTHER_DIR = "/Volumes/114/Other"
OUTPUT_DIR = "/Users/kornai/.gemini/tmp/clawmarc/Cards_Books"
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("Finding books in ~/Other...")
book_files = []
for root, _, files in os.walk(OTHER_DIR):
    for f in files:
        if f.lower().endswith((".pdf", ".epub")):
            path = os.path.join(root, f)
            # Filter for larger files to approximate books (> 2MB)
            try:
                if os.path.getsize(path) > 2 * 1024 * 1024:
                    book_files.append(path)
                    if len(book_files) > 2000:
                        break
            except OSError:
                pass
    if len(book_files) > 2000:
        break

sample_files = random.sample(book_files, min(20, len(book_files)))
print(f"Selected {len(sample_files)} book candidates for minting test.")

total_chars_embedded = 0
total_time_spent = 0
results = []

for idx, file_path in enumerate(sample_files):
    out_card = os.path.join(OUTPUT_DIR, f"card_book_{idx}.cxcc")
    out_meta = os.path.join(OUTPUT_DIR, f"card_book_{idx}.cxcc.json")
    
    start_time = time.time()
    cmd = [
        "python3", "reference/libangel_catalog.py",
        "--out-card", out_card,
        "--out-meta", out_meta,
        "--schema", "reference/clawmarc_catalog_card.h",
        "--allow-doc-vector",
        "--allow-text-prefix",
        file_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        elapsed = time.time() - start_time
        
        chars = 0
        tokens = 0
        if os.path.exists(out_meta):
            with open(out_meta, "r") as f:
                meta = json.load(f)
                if "segments" in meta and "body" in meta["segments"]:
                    chars = len(meta["segments"]["body"])
                if "policy" in meta and "chunking" in meta["policy"]:
                    tokens = meta["policy"]["chunking"].get("token_count", 0)
        
        results.append((os.path.basename(file_path), elapsed, chars, tokens))
        total_time_spent += elapsed
        total_chars_embedded += tokens  # using this variable for total tokens
        print(f"Minted: {os.path.basename(file_path)} | Time: {elapsed:.2f}s | Tokens: {tokens}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to mint {file_path}: {e.stderr}")

print(f"\nMinting {len(results)} book cards took {total_time_spent:.2f} seconds.")
if len(results) > 0 and total_chars_embedded > 0:
    # Estimate ~650 tokens per page
    total_pages = total_chars_embedded / 650.0
    time_per_page = total_time_spent / total_pages if total_pages > 0 else 0
    print(f"Total extracted text embedded: {total_chars_embedded} tokens (approx {total_pages:.1f} pages)")
    print(f"Time per page of embedded text: {time_per_page:.2f} seconds.")
