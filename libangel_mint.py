#!/usr/bin/env python3
"""Mint a CXCC catalog card for a signed ClawXiv bundle."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import struct
import zipfile
from pathlib import Path
from typing import Any

from libangel_card import (
    CardInput,
    CLASS_ARTICLE,
    SIZE_MB,
    TextSegments,
    canonical_json_bytes,
    card_content_id,
    card_id,
    deterministic_private_key,
    pack_unsigned_card,
    public_key_pem,
    sha256_bytes,
    sha256_hex,
    sign_card,
    verify_card,
    PROFILE_BGE_SMALL_EN_V1_5_F16_384,
)


DEFAULT_ISSUER_SEED = "LibAngel reference issuer v1: GPT-5 Codex independent DropOfWater card"
DEFAULT_ISSUED_UNIX = 1782071790  # 2026-06-21T19:56:30Z, later AI signature timestamp
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_TEXT_PROFILE = "cxcc-text-v1"
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
LAST_TEXT_EXTRACTOR = "none"


def parse_simple_yaml(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_key = None
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("-") and current_key:
            data.setdefault(current_key, []).append(stripped[1:].strip().strip("'\""))
            continue
        m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        current_key = key
        if value in (">", "|"):
            data[key] = ""
        elif value == "":
            data[key] = []
        else:
            value = value.split("#", 1)[0].strip()
            data[key] = value.strip("'\"")
    return data


def read_zip_member(zf: zipfile.ZipFile, name: str) -> bytes:
    try:
        return zf.read(name)
    except KeyError as exc:
        raise SystemExit(f"missing bundle member: {name}") from exc


def iso_to_unix(value: str) -> int:
    return int(dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def extract_hex_reference(value: str) -> bytes:
    value = value.strip()
    if re.fullmatch(r"[0-9a-fA-F]{64}", value):
        return bytes.fromhex(value)
    return b""


def first_url(text: str) -> str:
    m = re.search(r"https?://[^\s,)]+", text)
    return m.group(0) if m else ""


def tex_to_search_text(tex: str) -> str:
    global LAST_TEXT_EXTRACTOR
    for cmd in (["opendetex"], ["/Library/TeX/texbin/detex"], ["detex"]):
        try:
            proc = subprocess.run(
                cmd,
                input=tex,
                text=True,
                check=True,
                capture_output=True,
            )
            cleaned = re.sub(r"\s+", " ", proc.stdout).strip()
            if cleaned:
                LAST_TEXT_EXTRACTOR = " ".join(cmd)
                return cleaned
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

    LAST_TEXT_EXTRACTOR = "libangel-regex-fallback"
    tex = re.sub(r"%.*", "", tex)
    tex = re.sub(r"\\cite\{[^}]*\}", "", tex)
    tex = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{([^{}]*)\})?", r"\1", tex)
    tex = tex.replace("---", " ")
    tex = tex.replace("--", " ")
    tex = re.sub(r"[{}$]", " ", tex)
    tex = re.sub(r"\s+", " ", tex)
    return tex.strip()


def embedding_source_text(segments: TextSegments, extracted_body: str = "") -> str:
    body = clean_embedding_text(extracted_body or segments.body)
    if body:
        return body
    return clean_embedding_text(f"{segments.title}\n\n{segments.abstract}\n\n{segments.keywords}")


def clean_embedding_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def bge_small_embedding_f16le(text: str, model_name: str) -> tuple[bytes, dict[str, Any]]:
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except ImportError as exc:
        raise SystemExit(
            "sentence-transformers is required for embedding profile 1; "
            "rerun with --no-embedding only for an explicit text-only card"
        ) from exc

    model = SentenceTransformer(model_name)
    tokenizer = getattr(model, "tokenizer", None)
    if tokenizer is None:
        raise SystemExit(f"{model_name} did not expose a tokenizer")

    original_model_max_length = getattr(tokenizer, "model_max_length", 512)
    tokenizer.model_max_length = max(original_model_max_length, 1_000_000)
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    tokenizer.model_max_length = original_model_max_length
    max_body_tokens = 480
    chunks = [token_ids[i:i + max_body_tokens] for i in range(0, len(token_ids), max_body_tokens)] or [[]]
    chunk_texts = [
        tokenizer.decode(chunk, skip_special_tokens=True, clean_up_tokenization_spaces=False)
        for chunk in chunks
    ]
    chunk_vectors = model.encode(chunk_texts, normalize_embeddings=True, convert_to_numpy=True)
    weights = np.array([max(1, len(chunk)) for chunk in chunks], dtype=np.float32)
    vector = np.average(chunk_vectors, axis=0, weights=weights)
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        raise SystemExit("embedding vector has zero norm")
    vector = vector / norm
    if len(vector) != 384:
        raise SystemExit(f"{model_name} returned {len(vector)} dimensions, expected 384")

    embedding = b"".join(struct.pack("<e", float(x)) for x in vector)
    return embedding, {
        "embedding_mode": "bge-small-en-v1.5-f16le",
        "embedding_status": "provisional-long-body-reduction",
        "reduction_policy": "producer-choice until the TACL pooling study pins a reduction",
        "embedding_profile_id": PROFILE_BGE_SMALL_EN_V1_5_F16_384,
        "model": model_name,
        "dim": len(vector),
        "pooling": "Producer-choice provisional reduction: token chunks of 480 body tokens; encode each chunk with normalize_embeddings=True; token-count weighted mean; final L2 normalize",
        "normalization": "Chunk vectors and final pooled vector are L2-normalized",
        "chunking": {
            "tokenizer": "model tokenizer",
            "add_special_tokens": False,
            "max_body_tokens_per_chunk": max_body_tokens,
            "stride": 0,
            "chunk_count": len(chunks),
            "token_count": len(token_ids),
            "chunk_token_counts": [len(chunk) for chunk in chunks],
        },
        "encoding": "IEEE-754 binary16 little-endian",
        "bytes": len(embedding),
        "source_text_sha256": sha256_hex(text.encode("utf-8")),
        "embedding_sha256": sha256_hex(embedding),
    }


def first_body_paragraph(clean_text_value: str) -> str:
    for para in re.split(r"\n\s*\n", clean_text_value):
        para = re.sub(r"\s+", " ", para).strip()
        if len(para) >= 80 and not para.lower().startswith("two drops of water"):
            return para
    return re.sub(r"\s+", " ", clean_text_value).strip()[:600]


def build_segments(project: dict[str, Any], tex: str, args: argparse.Namespace) -> TextSegments:
    title = project.get("title") or "Two Drops of Water"
    clean_body = tex_to_search_text(tex)
    abstract = args.abstract or project.get("abstract") or project.get("description") or first_body_paragraph(clean_body)
    keywords = args.keywords or project.get("keywords") or ""
    if isinstance(keywords, list):
        keywords = ", ".join(keywords)
    classification = args.classification or project.get("classification") or "cs.CY; cs.AI"
    return TextSegments(title=title, abstract=abstract, keywords=keywords, classification=classification, body=clean_body)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def make_card(args: argparse.Namespace) -> tuple[bytes, dict[str, Any]]:
    bundle = Path(args.bundle)
    bundle_bytes = bundle.read_bytes()
    bundle_sha = sha256_bytes(bundle_bytes)

    with zipfile.ZipFile(bundle, "r") as zf:
        project_bytes = read_zip_member(zf, "project.yaml")
        tex_bytes = read_zip_member(zf, "src/two_drops_of_water.tex")
        pdf_bytes = read_zip_member(zf, "src/two_drops_of_water.pdf")
        try:
            manifest_bytes = zf.read("manifest.json")
        except KeyError:
            manifest_bytes = b""

    project_text = project_bytes.decode("utf-8")
    tex_text = tex_bytes.decode("utf-8")
    project = parse_simple_yaml(project_text)

    codex_prov = load_json(Path(args.codex_provenance)) if args.codex_provenance else None
    claude_prov = load_json(Path(args.claude_provenance)) if args.claude_provenance else None
    provenances = [p for p in (claude_prov, codex_prov) if p]
    for prov in provenances:
        got = prov["signed_artifact"]["sha256"]
        if got != bundle_sha.hex():
            raise SystemExit(f"provenance {prov['signer']['name']} signs {got}, not bundle {bundle_sha.hex()}")

    schema_sha = sha256_bytes(Path(args.schema).read_bytes()) if args.schema else b"\0" * 32
    issued = args.card_issued_unix
    if issued is None and provenances:
        issued = max(iso_to_unix(p["entropy_sources"]["timestamp_utc"]) for p in provenances)
    if issued is None:
        issued = DEFAULT_ISSUED_UNIX

    work_created = args.work_created_unix if args.work_created_unix is not None else issued
    work_revised = args.work_revised_unix if args.work_revised_unix is not None else issued

    authors = project.get("authors") or []
    signer_records = []
    for prov in provenances:
        key_hex = prov["key"]["public_key_hex"]
        signer_records.append({
            "name": prov["signer"]["name"],
            "provider": prov["signer"].get("provider", ""),
            "fingerprint_prefix": prov["key"]["fingerprint_prefix"],
            "public_key_sha256": sha256_hex(bytes.fromhex(key_hex)),
        })
    author_list_sha = sha256_bytes(canonical_json_bytes({
        "authors": authors,
        "signers": signer_records,
    }))

    if claude_prov:
        primary_key_hex = claude_prov["key"]["public_key_hex"]
    elif provenances:
        primary_key_hex = provenances[0]["key"]["public_key_hex"]
    else:
        primary_key_hex = ""
    primary_author_fpr = sha256_bytes(bytes.fromhex(primary_key_hex)) if primary_key_hex else b"\0" * 32

    swarm_ref = extract_hex_reference(args.swarm_reference or project.get("swarm_v2_reference", ""))
    ipfs_cid = args.ipfs_cid or project.get("ipfs_cid", "")
    ipns_name = args.ipns_name or ""
    http_candidates = [u.strip() for u in args.http_hint.split(",") if u.strip()]
    if not http_candidates:
        http_candidates = re.findall(r"https?://[^\s,)]+", project_text)
    http_hint = sorted(http_candidates)[0] if http_candidates else first_url(project_text)
    locators = {
        "swarm_reference": swarm_ref.hex() if swarm_ref else "",
        "ipfs_cid": ipfs_cid,
        "ipns_name": ipns_name,
        "http_hint": http_hint,
        "http_mirrors": sorted(http_candidates),
    }
    locator_set_sha = sha256_bytes(canonical_json_bytes(locators))

    issuer_private = deterministic_private_key(args.issuer_seed)
    segments = build_segments(project, tex_text, args)
    embed_text = embedding_source_text(segments, segments.body)
    if args.no_embedding:
        embedding = b""
        embedding_profile_id = 0
        embedding_policy = {
            "embedding_mode": "none",
            "reason": "Caller explicitly requested --no-embedding.",
            "deterministic": True,
        }
    else:
        embedding, embedding_policy = bge_small_embedding_f16le(embed_text, args.embedding_model)
        embedding_profile_id = embedding_policy["embedding_profile_id"]

    inp = CardInput(
        card_issued_unix=issued,
        work_created_unix=work_created,
        work_revised_unix=work_revised,
        sequence=args.sequence,
        arena_class=CLASS_ARTICLE,
        size_class=SIZE_MB,
        schema_sha256=schema_sha,
        object_sha256=bundle_sha,
        source_or_manifest_sha256=sha256_bytes(manifest_bytes) if manifest_bytes else b"\0" * 32,
        issuer_private_key=issuer_private,
        responsible_orcid=project.get("orcid", ""),
        author_count=len(authors) if isinstance(authors, list) else 0,
        classification_count=4,
        url_count=sum(1 for v in locators.values() if v),
        primary_author_fpr=primary_author_fpr,
        author_list_sha256=author_list_sha,
        license_id=args.license_id,
        swarm_reference=swarm_ref,
        ipfs_cid=ipfs_cid,
        ipns_name=ipns_name,
        http_hint=http_hint,
        locator_set_sha256=locator_set_sha,
        text=segments,
        embedding=embedding,
        embedding_profile_id=embedding_profile_id,
    )
    unsigned, pack_meta = pack_unsigned_card(inp)
    signed = sign_card(unsigned, issuer_private)
    verify_meta = verify_card(signed)
    meta = {
        "schema": "libangel-cxcc-mint-v1",
        "artifact": {
            "path": str(bundle),
            "sha256": bundle_sha.hex(),
            "project_yaml_sha256": sha256_hex(project_bytes),
            "manifest_json_sha256": sha256_hex(manifest_bytes) if manifest_bytes else "",
            "tex_sha256": sha256_hex(tex_bytes),
            "pdf_sha256": sha256_hex(pdf_bytes),
        },
        "cxcc": {
            "card_bytes": len(signed),
            "card_id": card_id(signed).hex(),
            "card_content_id": card_content_id(signed).hex(),
            **pack_meta,
            **verify_meta,
        },
        "issuer": {
            "seed_label": args.issuer_seed,
            "public_key_pem": public_key_pem(issuer_private).strip(),
        },
        "locators": locators,
        "authors": authors,
        "signer_records": signer_records,
        "text_segments": {
            "text_profile": DEFAULT_TEXT_PROFILE,
            "text_extractor": LAST_TEXT_EXTRACTOR,
            "title": segments.title,
            "abstract": segments.abstract,
            "keywords": segments.keywords,
            "classification": segments.classification,
            "embedding_preimage": embed_text,
            "embedding_preimage_sha256": sha256_hex(embed_text.encode("utf-8")),
        },
        "policy": {
            **embedding_policy,
            "deterministic": True,
        },
    }
    return signed, meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Mint a 4096-byte CXCC catalog card")
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--codex-provenance")
    parser.add_argument("--claude-provenance")
    parser.add_argument("--schema")
    parser.add_argument("--out-card", required=True)
    parser.add_argument("--out-meta", required=True)
    parser.add_argument("--issuer-seed", default=DEFAULT_ISSUER_SEED)
    parser.add_argument("--sequence", type=int, default=1)
    parser.add_argument("--card-issued-unix", type=int)
    parser.add_argument("--work-created-unix", type=int)
    parser.add_argument("--work-revised-unix", type=int)
    parser.add_argument("--swarm-reference", default="")
    parser.add_argument("--ipfs-cid", default="")
    parser.add_argument("--ipns-name", default="")
    parser.add_argument("--http-hint", default="")
    parser.add_argument("--license-id", default="CC0-1.0")
    parser.add_argument("--abstract", default="")
    parser.add_argument("--keywords", default="")
    parser.add_argument("--classification", default="")
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--no-embedding", action="store_true")
    args = parser.parse_args()

    card, meta = make_card(args)
    out_card = Path(args.out_card)
    out_meta = Path(args.out_meta)
    out_card.parent.mkdir(parents=True, exist_ok=True)
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    out_card.write_bytes(card)
    out_meta.write_text(json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out_card}")
    print(f"wrote {out_meta}")
    print(f"card_id={meta['cxcc']['card_id']}")
    print(f"card_content_id={meta['cxcc']['card_content_id']}")
    print(f"issuer_fingerprint={meta['cxcc']['issuer_fingerprint_prefix']}")


if __name__ == "__main__":
    main()
