import torch

# 1. Check if Apple Silicon GPU acceleration is available
device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
print(f"Using device: {device}")

# 2. Load XLM-R directly from Meta's PyTorch Hub repository
# (This bypasses Hugging Face and downloads from Meta's servers)
print("Loading model...")
xlmr = torch.hub.load('pytorch/fairseq:main', 'xlmr.large')
xlmr.to(device)  # Move the model to your M1 GPU
xlmr.eval()      # Put model in evaluation mode

# 3. Test text processing
text = "Hello world! Hola mundo! Bonjour le monde!"

# Extract features/embeddings
print("Extracting features...")
with torch.no_grad():
    tokens = xlmr.encode(text).to(device)
    last_layer_features = xlmr.extract_features(tokens)

print(f"Feature shape: {last_layer_features.shape}")
print("Success! Running on Apple Silicon.")

