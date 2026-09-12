from __future__ import annotations

import hashlib
import struct
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import probe


def make_card(path: Path, seed: str, values: list[float], profile: int = 1) -> None:
    key = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(seed.encode()).digest())
    embedding = struct.pack("<" + "e" * len(values), *values)
    card = bytearray(probe.CARD_BYTES)
    card[:4] = b"CXCC"
    struct.pack_into("<HH", card, 4, 1, 3)
    struct.pack_into("<H", card, 8, len(embedding))
    struct.pack_into("<I", card, 12, 1 << 8)
    card[0x0B0:0x0D0] = key.public_key().public_bytes_raw()
    struct.pack_into("<H", card, 0x304, profile)
    card[0x330:0x350] = hashlib.sha256(embedding).digest()
    card[0x4C0:0x4C0 + len(embedding)] = embedding
    card[probe.FOOTER_OFFSET:probe.FOOTER_OFFSET + 4] = struct.pack("<I", probe.crc32(card[:probe.HEADER_BYTES]))
    card[probe.FOOTER_OFFSET + 4:probe.FOOTER_OFFSET + 8] = struct.pack("<I", probe.crc32(card[probe.HEADER_BYTES:probe.FOOTER_OFFSET]))
    unsigned = bytes(card)
    card[probe.SIGNATURE_OFFSET:probe.SIGNATURE_OFFSET + probe.SIGNATURE_BYTES] = key.sign(unsigned)
    card[probe.FOOTER_OFFSET:probe.FOOTER_OFFSET + 4] = struct.pack("<I", probe.crc32(card[:probe.HEADER_BYTES]))
    path.write_bytes(card)


def test_verify_rank_and_reference() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cards = root / "cards"
        cards.mkdir()
        make_card(cards / "a.cxcc", "a", [1.0, 0.0])
        make_card(cards / "b.cxcc", "b", [0.0, 1.0])
        make_card(root / "query.cxcc", "q", [1.0, 0.0])
        args = type("Args", (), {"cards": str(cards), "query": str(root / "query.cxcc"), "top_k": 2, "expected": None})
        result = probe.run(args)
        assert result["ranking"][0]["file"] == "a.cxcc"
        ref = root / "reference.json"
        ref.write_text(__import__("json").dumps(result))
        args.expected = str(ref)
        assert probe.run(args)["reference_match"] is True
