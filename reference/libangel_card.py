#!/usr/bin/env python3
"""CXCC catalog-card packing, signing, and inspection helpers."""

from __future__ import annotations

import base64
import binascii
import dataclasses
import hashlib
import json
import re
import struct
import unicodedata
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

CARD_BYTES = 4096
HEADER_BYTES = 1216
ARENA_BYTES = 2816
FOOTER_OFFSET = 0xFC0
SIGNATURE_OFFSET = 0x0D0
SIGNATURE_BYTES = 64

LAYOUT_MAJOR = 1
LAYOUT_MINOR = 2

CLASS_CATALOG_OBJECT = 0
CLASS_INDIRECT_CATALOG_CARD = 1
CLASS_DOUBLY_INDIRECT_CATALOG_CARD = 2
CLASS_ARTICLE = 16
CLASS_BOOK = 17
CLASS_PICTURE = 18
CLASS_MOVIE = 19
CLASS_MUSIC = 20
CLASS_SOFTWARE = 21
CLASS_DATASET = 22
CLASS_MAP = 23
CLASS_METADATA = 24
CLASS_SEQUENCE = 25
CLASS_MODEL = 26
CLASS_WEBPAGE = 27
CLASS_ARCHIVE = 28

SIZE_EMPTY = 0
SIZE_64BIT = 1
SIZE_KB = 2
SIZE_MB = 3
SIZE_GB = 4
SIZE_TB = 5
SIZE_PB = 6
SIZE_EB = 7
SIZE_ZB = 8
SIZE_YB = 9

ACCESS_OPEN = 0
ENC_NONE = 0

FLAG_OBJECT_SHA256_PRESENT = 1 << 0
FLAG_PREV_CARD_PRESENT = 1 << 1
FLAG_SWARM_REF_PRESENT = 1 << 2
FLAG_IPFS_CID_PRESENT = 1 << 3
FLAG_IPNS_PRESENT = 1 << 4
FLAG_HTTP_HINT_PRESENT = 1 << 5
FLAG_ARTIFACT_ENCRYPTED = 1 << 6
FLAG_ACCESS_GATED = 1 << 7
FLAG_EMBEDDING_PRESENT = 1 << 8
FLAG_TEXT_TRUNCATED = 1 << 9
FLAG_ISSUER_CARD_REF_PRESENT = 1 << 10

PROFILE_NONE = 0
PROFILE_BGE_SMALL_EN_V1_5_F16_384 = 1


def sha256_bytes(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def zero_pad(data: bytes, size: int, field: str) -> bytes:
    if len(data) > size:
        raise ValueError(f"{field} too long: {len(data)} > {size}")
    return data + b"\0" * (size - len(data))


def text_field(text: str, size: int, field: str) -> bytes:
    return zero_pad(text.encode("utf-8"), size, field)


def ascii_field(text: str, size: int, field: str) -> bytes:
    return zero_pad(text.encode("ascii"), size, field)


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def deterministic_private_key(seed_label: str) -> Ed25519PrivateKey:
    seed = sha256_bytes(seed_label.encode("utf-8"))
    return Ed25519PrivateKey.from_private_bytes(seed)


def public_key_raw(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def public_key_pem(private_key: Ed25519PrivateKey) -> str:
    return private_key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii")


def crc32(data: bytes) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


@dataclasses.dataclass(frozen=True)
class TextSegments:
    title: str
    abstract: str
    keywords: str
    classification: str
    body: str = ""

    def encode(self, capacity: int) -> tuple[bytes, tuple[int, int, int, int], bool]:
        title_b = clean_text(self.title).encode("utf-8")
        keywords_b = clean_text(self.keywords).encode("utf-8")
        classification_b = clean_text(self.classification).encode("utf-8")
        fixed_len = len(title_b) + len(keywords_b) + len(classification_b)
        if fixed_len > capacity:
            raise ValueError("title+keywords+classification exceed arena capacity")

        abstract = clean_text(self.abstract)
        abstract_b = abstract.encode("utf-8")
        truncated = False
        remaining = capacity - fixed_len
        if len(abstract_b) > remaining:
            truncated = True
            abstract_b = abstract_b[:remaining]
            while True:
                try:
                    abstract_b.decode("utf-8")
                    break
                except UnicodeDecodeError:
                    abstract_b = abstract_b[:-1]
            abstract_b = abstract_b.rstrip()

        remaining = capacity - fixed_len - len(abstract_b)
        body_b = clean_text(self.body).encode("utf-8")
        if len(body_b) > remaining:
            truncated = True
            body_b = body_b[:remaining]
            while True:
                try:
                    body_b.decode("utf-8")
                    break
                except UnicodeDecodeError:
                    body_b = body_b[:-1]
            body_b = body_b.rstrip()

        used = title_b + abstract_b + keywords_b + classification_b + body_b
        return (
            used + b"\0" * (capacity - len(used)),
            (len(title_b), len(abstract_b), len(keywords_b), len(classification_b)),
            truncated,
        )


@dataclasses.dataclass(frozen=True)
class CardInput:
    card_issued_unix: int
    work_created_unix: int
    work_revised_unix: int
    sequence: int
    arena_class: int
    size_class: int
    schema_sha256: bytes
    object_sha256: bytes
    source_or_manifest_sha256: bytes
    issuer_private_key: Ed25519PrivateKey
    responsible_orcid: str
    author_count: int
    classification_count: int
    url_count: int
    primary_author_fpr: bytes
    author_list_sha256: bytes
    license_id: str
    swarm_reference: bytes
    ipfs_cid: str
    ipns_name: str
    http_hint: str
    locator_set_sha256: bytes
    text: TextSegments
    embedding: bytes = b""
    embedding_profile_id: int = PROFILE_NONE


def pack_unsigned_card(inp: CardInput) -> tuple[bytearray, dict[str, Any]]:
    if len(inp.schema_sha256) != 32:
        raise ValueError("schema_sha256 must be 32 bytes")
    if len(inp.object_sha256) != 32:
        raise ValueError("object_sha256 must be 32 bytes")
    if len(inp.source_or_manifest_sha256) != 32:
        raise ValueError("source_or_manifest_sha256 must be 32 bytes")
    if len(inp.primary_author_fpr) != 32:
        raise ValueError("primary_author_fpr must be 32 bytes")
    if len(inp.author_list_sha256) != 32:
        raise ValueError("author_list_sha256 must be 32 bytes")
    if len(inp.locator_set_sha256) != 32:
        raise ValueError("locator_set_sha256 must be 32 bytes")
    if len(inp.swarm_reference) not in (0, 32):
        raise ValueError("swarm_reference must be zero length or 32 bytes")
    if len(inp.embedding) > ARENA_BYTES:
        raise ValueError("embedding too large")

    arena_split = len(inp.embedding)
    text_capacity = ARENA_BYTES - arena_split
    arena_text, lengths, text_truncated = inp.text.encode(text_capacity)
    title_len, abstract_len, keywords_len, classification_len = lengths
    used_text = arena_text.rstrip(b"\0")
    arena = inp.embedding + arena_text
    if len(arena) != ARENA_BYTES:
        raise AssertionError("arena packing bug")

    flags = FLAG_OBJECT_SHA256_PRESENT
    if inp.swarm_reference:
        flags |= FLAG_SWARM_REF_PRESENT
    if inp.ipfs_cid:
        flags |= FLAG_IPFS_CID_PRESENT
    if inp.ipns_name:
        flags |= FLAG_IPNS_PRESENT
    if inp.http_hint:
        flags |= FLAG_HTTP_HINT_PRESENT
    if inp.embedding:
        flags |= FLAG_EMBEDDING_PRESENT
    if text_truncated:
        flags |= FLAG_TEXT_TRUNCATED

    card = bytearray(CARD_BYTES)
    off = 0
    card[off:off + 4] = b"CXCC"; off += 4
    struct.pack_into("<H", card, off, LAYOUT_MAJOR); off += 2
    struct.pack_into("<H", card, off, LAYOUT_MINOR); off += 2
    struct.pack_into("<H", card, off, arena_split); off += 2
    struct.pack_into("<B", card, off, inp.arena_class); off += 1
    struct.pack_into("<B", card, off, inp.size_class); off += 1
    struct.pack_into("<I", card, off, flags); off += 4
    struct.pack_into("<Q", card, off, inp.card_issued_unix); off += 8
    struct.pack_into("<Q", card, off, inp.work_created_unix); off += 8
    struct.pack_into("<Q", card, off, inp.work_revised_unix); off += 8
    struct.pack_into("<Q", card, off, inp.sequence); off += 8
    card[off:off + 32] = inp.schema_sha256; off += 32
    card[off:off + 32] = inp.object_sha256; off += 32
    card[off:off + 32] = inp.source_or_manifest_sha256; off += 32
    off += 32  # prev_card_sha256 zero
    issuer_pub = public_key_raw(inp.issuer_private_key)
    card[off:off + 32] = issuer_pub; off += 32
    sig_off = off
    off += 64  # card_signature zero
    off += 32  # issuer_card_ref zero
    struct.pack_into("<B", card, off, ACCESS_OPEN); off += 1
    struct.pack_into("<B", card, off, ENC_NONE); off += 1
    struct.pack_into("<B", card, off, 0); off += 1
    struct.pack_into("<B", card, off, 0); off += 1
    off += 32  # artefact_key zero
    off += 64  # access_ref zero
    card[off:off + 20] = ascii_field(inp.responsible_orcid, 20, "responsible_orcid"); off += 20
    struct.pack_into("<B", card, off, inp.author_count); off += 1
    struct.pack_into("<B", card, off, inp.classification_count); off += 1
    struct.pack_into("<B", card, off, inp.url_count); off += 1
    struct.pack_into("<B", card, off, 0); off += 1
    card[off:off + 32] = inp.primary_author_fpr; off += 32
    card[off:off + 32] = inp.author_list_sha256; off += 32
    card[off:off + 8] = ascii_field(inp.license_id, 8, "license_id"); off += 8
    if inp.swarm_reference:
        card[off:off + 32] = inp.swarm_reference
    off += 32
    card[off:off + 64] = ascii_field(inp.ipfs_cid, 64, "ipfs_cid"); off += 64
    card[off:off + 48] = ascii_field(inp.ipns_name, 48, "ipns_name"); off += 48
    card[off:off + 96] = text_field(inp.http_hint, 96, "http_hint"); off += 96
    card[off:off + 32] = inp.locator_set_sha256; off += 32
    struct.pack_into("<H", card, off, inp.embedding_profile_id); off += 2
    struct.pack_into("<H", card, off, title_len); off += 2
    struct.pack_into("<H", card, off, abstract_len); off += 2
    struct.pack_into("<H", card, off, keywords_len); off += 2
    struct.pack_into("<H", card, off, classification_len); off += 2
    struct.pack_into("<H", card, off, 1); off += 2  # NFC text
    card[off:off + 32] = sha256_bytes(used_text); off += 32
    card[off:off + 32] = sha256_bytes(inp.embedding) if inp.embedding else b"\0" * 32; off += 32
    off += 32  # target_card_id zero
    off += 336  # header_reserved zero
    if off != 0x4C0:
        raise AssertionError(f"header offset mismatch: {off:#x}")
    card[off:off + ARENA_BYTES] = arena; off += ARENA_BYTES
    if off != FOOTER_OFFSET:
        raise AssertionError(f"footer offset mismatch: {off:#x}")

    card[FOOTER_OFFSET:FOOTER_OFFSET + 4] = struct.pack("<I", crc32(card[:HEADER_BYTES]))
    card[FOOTER_OFFSET + 4:FOOTER_OFFSET + 8] = struct.pack("<I", crc32(card[HEADER_BYTES:FOOTER_OFFSET]))
    if sig_off != SIGNATURE_OFFSET:
        raise AssertionError(f"signature offset mismatch: {sig_off:#x}")

    meta = {
        "flags": flags,
        "arena_split": arena_split,
        "arena_class": inp.arena_class,
        "size_class": inp.size_class,
        "title_len": title_len,
        "abstract_len": abstract_len,
        "keywords_len": keywords_len,
        "classification_len": classification_len,
        "text_truncated": text_truncated,
        "issuer_public_key_hex": issuer_pub.hex(),
        "issuer_fingerprint_prefix": sha256_hex(issuer_pub)[:16],
        "header_crc32": f"{struct.unpack_from('<I', card, FOOTER_OFFSET)[0]:08x}",
        "body_crc32": f"{struct.unpack_from('<I', card, FOOTER_OFFSET + 4)[0]:08x}",
    }
    return card, meta


def sign_card(unsigned_card: bytearray, private_key: Ed25519PrivateKey) -> bytes:
    working = bytearray(unsigned_card)
    working[SIGNATURE_OFFSET:SIGNATURE_OFFSET + SIGNATURE_BYTES] = b"\0" * SIGNATURE_BYTES
    signature = private_key.sign(bytes(working))
    signed = bytearray(unsigned_card)
    signed[SIGNATURE_OFFSET:SIGNATURE_OFFSET + SIGNATURE_BYTES] = signature
    return bytes(signed)


def card_content_id(card: bytes) -> bytes:
    working = bytearray(card)
    working[SIGNATURE_OFFSET:SIGNATURE_OFFSET + SIGNATURE_BYTES] = b"\0" * SIGNATURE_BYTES
    working[FOOTER_OFFSET:FOOTER_OFFSET + 8] = b"\0" * 8
    return sha256_bytes(bytes(working))


def card_id(card: bytes) -> bytes:
    return sha256_bytes(card)


def verify_card(card: bytes) -> dict[str, Any]:
    if len(card) != CARD_BYTES:
        raise ValueError(f"card size must be {CARD_BYTES}")
    if card[:4] != b"CXCC":
        raise ValueError("bad magic")
    signature = bytes(card[SIGNATURE_OFFSET:SIGNATURE_OFFSET + SIGNATURE_BYTES])
    issuer_pub = bytes(card[0x0B0:0x0B0 + 32])
    working = bytearray(card)
    working[SIGNATURE_OFFSET:SIGNATURE_OFFSET + SIGNATURE_BYTES] = b"\0" * SIGNATURE_BYTES
    stored_header_crc = struct.unpack_from("<I", working, FOOTER_OFFSET)[0]
    stored_body_crc = struct.unpack_from("<I", working, FOOTER_OFFSET + 4)[0]
    computed_header_crc = crc32(working[:HEADER_BYTES])
    computed_body_crc = crc32(working[HEADER_BYTES:FOOTER_OFFSET])
    if stored_header_crc != computed_header_crc:
        raise ValueError("header CRC mismatch")
    if stored_body_crc != computed_body_crc:
        raise ValueError("body CRC mismatch")
    Ed25519PublicKey.from_public_bytes(issuer_pub).verify(signature, bytes(working))
    return {
        "card_id": card_id(card).hex(),
        "card_content_id": card_content_id(card).hex(),
        "issuer_fingerprint_prefix": sha256_hex(issuer_pub)[:16],
        "signature_b64": base64.b64encode(signature).decode("ascii"),
    }


def unpack_basic(card: bytes) -> dict[str, Any]:
    if len(card) != CARD_BYTES:
        raise ValueError(f"card size must be {CARD_BYTES}")
    arena_split = struct.unpack_from("<H", card, 0x008)[0]
    title_len, abstract_len, keywords_len, classification_len = struct.unpack_from("<HHHH", card, 0x306)
    text_start = 0x4C0 + arena_split
    text_capacity = ARENA_BYTES - arena_split
    text_used_len = len(card[text_start:text_start + text_capacity].rstrip(b"\0"))
    text = card[text_start:text_start + text_used_len]
    stored_text_sha256 = bytes(card[0x310:0x330])
    computed_text_sha256 = sha256_bytes(text)
    if stored_text_sha256 != computed_text_sha256:
        raise ValueError("text_sha256 mismatch")
    a = title_len
    b = a + abstract_len
    c = b + keywords_len
    d = c + classification_len
    return {
        "magic": card[:4].decode("ascii"),
        "layout_major": struct.unpack_from("<H", card, 0x004)[0],
        "layout_minor": struct.unpack_from("<H", card, 0x006)[0],
        "arena_split": arena_split,
        "arena_class": card[0x00A],
        "size_class": card[0x00B],
        "flags": struct.unpack_from("<I", card, 0x00C)[0],
        "card_issued_unix": struct.unpack_from("<Q", card, 0x010)[0],
        "work_created_unix": struct.unpack_from("<Q", card, 0x018)[0],
        "work_revised_unix": struct.unpack_from("<Q", card, 0x020)[0],
        "sequence": struct.unpack_from("<Q", card, 0x028)[0],
        "schema_sha256": card[0x030:0x050].hex(),
        "object_sha256": card[0x050:0x070].hex(),
        "source_or_manifest_sha256": card[0x070:0x090].hex(),
        "responsible_orcid": card[0x194:0x194 + 20].split(b"\0", 1)[0].decode("ascii"),
        "author_count": card[0x1A8],
        "swarm_reference": card[0x1F4:0x1F4 + 32].hex(),
        "ipfs_cid": card[0x214:0x214 + 64].split(b"\0", 1)[0].decode("ascii"),
        "ipns_name": card[0x254:0x254 + 48].split(b"\0", 1)[0].decode("ascii"),
        "http_hint": card[0x284:0x284 + 96].split(b"\0", 1)[0].decode("utf-8"),
        "embedding_profile_id": struct.unpack_from("<H", card, 0x304)[0],
        "text_sha256": stored_text_sha256.hex(),
        "computed_text_sha256": computed_text_sha256.hex(),
        "title": text[:a].decode("utf-8"),
        "abstract": text[a:b].decode("utf-8"),
        "keywords": text[b:c].decode("utf-8"),
        "classification": text[c:d].decode("utf-8"),
        "body_prefix": text[d:].decode("utf-8"),
        **verify_card(card),
    }
