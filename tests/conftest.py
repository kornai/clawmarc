"""Network-free fixtures for minting tests."""

import hashlib

import numpy as np
import pytest


class FakeTokenizer:
    model_max_length = 512

    def encode(self, text, *, add_special_tokens=False):
        return text.split()

    def decode(self, tokens, *, skip_special_tokens=True, clean_up_tokenization_spaces=False):
        return " ".join(tokens)


class FakeModel:
    def __init__(self, dimensions=384, max_seq_length=512):
        self.tokenizer = FakeTokenizer()
        self.dimensions = dimensions
        self.max_seq_length = max_seq_length

    def encode(self, texts, *, batch_size=32, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False):
        vectors = []
        for text in texts:
            seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "little")
            vector = np.random.default_rng(seed).standard_normal(self.dimensions, dtype=np.float32)
            if normalize_embeddings:
                vector /= np.linalg.norm(vector)
            vectors.append(vector)
        return np.stack(vectors)


@pytest.fixture
def fake_model():
    return FakeModel
