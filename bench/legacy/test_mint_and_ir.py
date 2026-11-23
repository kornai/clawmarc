import os
import sys
import time
import subprocess
import glob
import json
import struct
import math
import random
from pathlib import Path

OTHER_DIR = "/Volumes/114/Other"
OUTPUT_DIR = "/Users/kornai/.gemini/tmp/clawmarc/Cards_Other"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Find some PDFs
print("Finding files in ~/Other...")
all_files = []
for root, _, files in os.walk(OTHER_DIR):
    for f in files:
        if f.endswith(".pdf"):
            all_files.append(os.path.join(root, f))
            if len(all_files) > 1000:
                break
    if len(all_files) > 1000:
        break

sample_files = random.sample(all_files, min(20, len(all_files)))

print(f"Selected {len(sample_files)} files for minting test.")

start_time = time.time()
cards = []

for idx, file_path in enumerate(sample_files):
    out_card = os.path.join(OUTPUT_DIR, f"card_{idx}.cxcc")
    out_meta = os.path.join(OUTPUT_DIR, f"card_{idx}.cxcc.json")
    
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
        cards.append((out_card, out_meta, file_path))
        print(f"Minted: {os.path.basename(file_path)}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to mint {file_path}: {e.stderr}")

end_time = time.time()
elapsed = end_time - start_time
print(f"Minting {len(cards)} cards took {elapsed:.2f} seconds.")
if len(cards) > 0:
    print(f"Estimated time for 41,000 files: {elapsed / len(cards) * 41000 / 3600:.2f} hours.")

# Simple IR
print("\n--- Testing Local Information Retrieval ---")

def read_vector(card_path):
    with open(card_path, "rb") as f:
        data = f.read()
        # Header is 1216 bytes. Arena split determines text/payload size.
        # But for doc vectors, it's typically a 768-byte payload.
        # Let's inspect the meta json instead, it might not have the vector, but we can extract it from the card.
        header = data[:1216]
        arena_split = struct.unpack_from("<H", header, 8)[0]
        # if vector is present, it's typically the machine payload (from 0x4c0 to 0x4c0 + arena_split)
        # 384 f16le = 768 bytes
        if arena_split == 768:
            vec_bytes = data[0x4c0:0x4c0+768]
            # Convert f16 to float
            import numpy as np
            vec = np.frombuffer(vec_bytes, dtype=np.float16).astype(np.float32)
            return vec
    return None

def cosine_similarity(v1, v2):
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    return dot / (norm1 * norm2) if norm1 > 0 and norm2 > 0 else 0

vectors = []
for c, m, orig in cards:
    v = read_vector(c)
    with open(m, "r") as f:
        meta = json.load(f)
    vectors.append((c, m, orig, v, meta))

# Keyword search test
query_keyword = "theory"
print(f"Keyword search for '{query_keyword}':")
for c, m, orig, v, meta in vectors:
    if "segments" in meta and "body" in meta["segments"]:
        if query_keyword.lower() in meta["segments"]["body"].lower() or query_keyword.lower() in meta["segments"]["title"].lower():
            print(f" - Match: {os.path.basename(orig)}")

# Vector search test (dummy query vector based on the first document's vector if available)
valid_vectors = [x for x in vectors if x[3] is not None]
if len(valid_vectors) > 1:
    query_vec = valid_vectors[0][3]
    query_name = os.path.basename(valid_vectors[0][2])
    print(f"\nVector similarity search for documents like '{query_name}':")
    results = []
    for c, m, orig, v, meta in valid_vectors[1:]:
        sim = cosine_similarity(query_vec, v)
        results.append((os.path.basename(orig), sim))
    
    results.sort(key=lambda x: x[1], reverse=True)
    for name, sim in results:
        print(f" - {name}: {sim:.4f}")
else:
    print("\nNot enough valid vectors extracted for similarity test.")
