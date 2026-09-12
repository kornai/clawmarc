#!/usr/bin/env python3
"""Verify and rank transported Clawmarc cards without neural inference."""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import struct
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

CARD_BYTES = 4096
HEADER_BYTES = 1216
FOOTER_OFFSET = 0xFC0
SIGNATURE_OFFSET = 0x0D0
SIGNATURE_BYTES = 64
ARENA_BYTES = 2816


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def crc32(data: bytes) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


def card_info(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) != CARD_BYTES:
        raise ValueError(f"{path}: expected 4096 bytes, got {len(data)}")
    if data[:4] != b"CXCC":
        raise ValueError(f"{path}: bad magic")

    working = bytearray(data)
    signature = bytes(data[SIGNATURE_OFFSET:SIGNATURE_OFFSET + SIGNATURE_BYTES])
    issuer = bytes(data[0x0B0:0x0D0])
    working[SIGNATURE_OFFSET:SIGNATURE_OFFSET + SIGNATURE_BYTES] = b"\0" * SIGNATURE_BYTES
    stored_header, stored_body = struct.unpack_from("<II", data, FOOTER_OFFSET)
    if stored_header != crc32(working[:HEADER_BYTES]):
        raise ValueError(f"{path}: header CRC mismatch")
    if stored_body != crc32(working[HEADER_BYTES:FOOTER_OFFSET]):
        raise ValueError(f"{path}: body CRC mismatch")
    Ed25519PublicKey.from_public_bytes(issuer).verify(signature, bytes(working))

    arena_split = struct.unpack_from("<H", data, 0x008)[0]
    if not 0 < arena_split <= ARENA_BYTES or arena_split % 2:
        raise ValueError(f"{path}: unsupported arena split {arena_split}")
    embedding = data[0x4C0:0x4C0 + arena_split]
    stored_embedding_digest = data[0x330:0x350].hex()
    if stored_embedding_digest != sha256(embedding):
        raise ValueError(f"{path}: embedding digest mismatch")
    if len(embedding) % 2:
        raise ValueError(f"{path}: embedding is not binary16-aligned")
    vector = struct.unpack("<" + "e" * (len(embedding) // 2), embedding)
    norm = sum(x * x for x in vector) ** 0.5
    if norm == 0:
        raise ValueError(f"{path}: zero embedding")
    content = bytearray(data)
    content[SIGNATURE_OFFSET:SIGNATURE_OFFSET + SIGNATURE_BYTES] = b"\0" * SIGNATURE_BYTES
    content[FOOTER_OFFSET:FOOTER_OFFSET + 8] = b"\0" * 8
    return {
        "file": path.name,
        "card_id": sha256(data),
        "card_content_id": sha256(bytes(content)),
        "profile": struct.unpack_from("<H", data, 0x304)[0],
        "dimensions": len(vector),
        "embedding": tuple(vector),
    }


def rank(cards: list[dict], query: dict, top_k: int) -> list[dict]:
    if any(c["profile"] != query["profile"] or c["dimensions"] != query["dimensions"] for c in cards):
        raise ValueError("query and corpus cards must use one embedding profile and dimension")
    q = query["embedding"]
    qnorm = sum(x * x for x in q) ** 0.5
    scored = []
    for c in cards:
        cnorm = sum(x * x for x in c["embedding"]) ** 0.5
        score = sum(a * b for a, b in zip(q, c["embedding"])) / (qnorm * cnorm)
        scored.append({"card_id": c["card_id"], "file": c["file"], "score": score})
    return sorted(scored, key=lambda x: (-x["score"], x["card_id"]))[:top_k]


def run(args: argparse.Namespace) -> dict:
    paths = sorted(Path(args.cards).glob("*.cxcc"))
    if not paths:
        raise ValueError(f"no .cxcc cards found in {args.cards}")
    cards = [card_info(p) for p in paths]
    query = card_info(Path(args.query))
    result = {
        "probe_version": 1,
        "cards": [{k: c[k] for k in ("file", "card_id", "card_content_id", "profile", "dimensions")} for c in cards],
        "query": {k: query[k] for k in ("file", "card_id", "card_content_id", "profile", "dimensions")},
        "top_k": args.top_k,
        "ranking": rank(cards, query, args.top_k),
    }
    if args.expected:
        expected = json.loads(Path(args.expected).read_text())
        if result["cards"] != expected.get("cards") or result["query"] != expected.get("query"):
            raise ValueError("transported card identity or metadata differs from reference")
        got = [x["card_id"] for x in result["ranking"]]
        want = [x["card_id"] for x in expected.get("ranking", [])]
        if got != want:
            raise ValueError(f"ranking mismatch: got {got}, expected {want}")
        result["reference_match"] = True
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--write-reference")
    ap.add_argument("--expected")
    ap.add_argument("--output")
    args = ap.parse_args()
    try:
        result = run(args)
        payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.write_reference:
            Path(args.write_reference).write_text(payload)
        if args.output:
            Path(args.output).write_text(payload)
        print(json.dumps({"cards": len(result["cards"]), "top": result["ranking"][:3],
                          "reference_match": result.get("reference_match", False)}, indent=2))
        return 0
    except Exception as exc:
        print(f"transport probe failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
