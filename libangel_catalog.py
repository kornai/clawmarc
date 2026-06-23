#!/usr/bin/env python3
"""General LibAngel producer for rc1 CXCC catalog cards."""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import mimetypes
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any

from libangel_card import (
    CLASS_ARCHIVE,
    CLASS_ARTICLE,
    CLASS_DATASET,
    CLASS_METADATA,
    CLASS_MODEL,
    CLASS_MUSIC,
    CLASS_PICTURE,
    CLASS_SOFTWARE,
    CLASS_WEBPAGE,
    PROFILE_NONE,
    CardInput,
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
)
from libangel_mint import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_ISSUER_SEED,
    bge_small_embedding_f16le,
    embedding_source_text,
    parse_simple_yaml,
    tex_to_search_text,
)

DEFAULT_SCHEMA = str(Path(__file__).with_name("clawmarc_catalog_card.h"))


def utc_now() -> int:
    return int(dt.datetime.now(dt.UTC).timestamp())


def size_class(size: int) -> int:
    if size == 0:
        return 0
    if size <= 8:
        return 1
    limits = [10**3, 10**6, 10**9, 10**12, 10**15, 10**18, 10**21, 10**24]
    for idx, limit in enumerate(limits, start=2):
        if size <= limit:
            return idx
    return 9


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def first_paragraph(text: str, fallback: str) -> str:
    for para in re.split(r"\n\s*\n", text):
        para = clean_text(para)
        if len(para) >= 80:
            return para
    text = clean_text(text)
    return text[:700] if text else fallback


def run_text_tool(cmd: list[str], data: bytes | None = None) -> str:
    try:
        proc = subprocess.run(cmd, input=data, check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""
    return proc.stdout.decode("utf-8", errors="replace")


def detect_mime(path: Path) -> str:
    out = run_text_tool(["file", "-b", "--mime-type", str(path)])
    if out:
        return out.strip()
    guess, _ = mimetypes.guess_type(str(path))
    return guess or "application/octet-stream"


def image_payload(path: Path) -> bytes:
    try:
        from PIL import Image
    except ImportError:
        return b""
    try:
        with Image.open(path) as img:
            img = img.convert("L")
            img.thumbnail((48, 48))
            canvas = Image.new("L", (48, 48), 255)
            x = (48 - img.width) // 2
            y = (48 - img.height) // 2
            canvas.paste(img, (x, y))
            return b"CXVG1" + bytes([48, 48]) + canvas.tobytes()
    except Exception:
        return b""


def extract_text(path: Path, mime: str) -> tuple[int, str, str, bytes, int]:
    suffix = path.suffix.lower()
    if suffix == ".tex":
        text = tex_to_search_text(path.read_text(encoding="utf-8", errors="replace"))
        return CLASS_ARTICLE, "tex-detex", text, b"", 1
    if suffix in {".html", ".htm"} or mime == "text/html":
        text = run_text_tool(["pandoc", "--from", "html", "--to", "plain", str(path)])
        if not text:
            text = path.read_text(encoding="utf-8", errors="replace")
        return CLASS_WEBPAGE, "html-pandoc", text, b"", 1
    if suffix in {".md", ".txt"} or mime.startswith("text/"):
        return CLASS_ARTICLE, "utf8-text", path.read_text(encoding="utf-8", errors="replace"), b"", 1
    if suffix == ".docx":
        text = run_text_tool(["docx2txt", str(path), "-"])
        return CLASS_ARTICLE, "docx2txt", text, b"", 1 if text else 0
    if suffix == ".doc":
        text = run_text_tool(["catdoc", str(path)])
        return CLASS_ARTICLE, "catdoc", text, b"", 1 if text else 0
    return 0, "", "", b"", 0


def zip_project_metadata(path: Path) -> tuple[dict[str, Any], bytes, str]:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            project = zf.read("project.yaml")
            data = parse_simple_yaml(project.decode("utf-8", errors="replace"))
            root = data.get("root_tex", "")
            body = ""
            if root:
                try:
                    body = tex_to_search_text(zf.read(root).decode("utf-8", errors="replace"))
                except KeyError:
                    body = ""
            return data, b"", body
    except (KeyError, zipfile.BadZipFile):
        return {}, b"", ""


def classify(path: Path, mime: str) -> tuple[int, str]:
    suffix = path.suffix.lower()
    if mime.startswith("image/"):
        return CLASS_PICTURE, "image"
    if mime.startswith("audio/"):
        return CLASS_MUSIC, "audio"
    if suffix in {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z"}:
        return CLASS_ARCHIVE, "archive"
    if suffix in {".json", ".yaml", ".yml", ".xml"}:
        return CLASS_METADATA, "metadata"
    if suffix in {".bin", ".exe", ".dylib", ".so", ".o", ".a"}:
        return CLASS_SOFTWARE, "software"
    if suffix in {".safetensors", ".pt", ".pth", ".onnx"}:
        return CLASS_MODEL, "model"
    if suffix in {".csv", ".tsv", ".parquet", ".sqlite", ".db"}:
        return CLASS_DATASET, "dataset"
    return CLASS_SOFTWARE if mime == "application/octet-stream" else CLASS_ARTICLE, "generic"


def build_card(args: argparse.Namespace) -> tuple[bytes, dict[str, Any]]:
    path = Path(args.artifact)
    data = path.read_bytes()
    object_sha = sha256_bytes(data)
    mime = detect_mime(path)
    issued = args.card_issued_unix or utc_now()
    work_created = args.work_created_unix if args.work_created_unix is not None else issued
    work_revised = args.work_revised_unix if args.work_revised_unix is not None else issued

    arena_class, handler, text, machine_payload, classification_count = extract_text(path, mime)
    project: dict[str, Any] = {}
    source_or_manifest = b"\0" * 32
    if not handler and zipfile.is_zipfile(path):
        project, manifest_bytes, text = zip_project_metadata(path)
        arena_class = CLASS_ARCHIVE
        handler = "clawxiv-zip" if project else "archive"
        if manifest_bytes:
            source_or_manifest = sha256_bytes(manifest_bytes)

    if not handler:
        arena_class, handler = classify(path, mime)
        if arena_class == CLASS_PICTURE:
            machine_payload = image_payload(path)
            text = args.abstract or f"Image artefact: {path.name}; MIME {mime}; {len(data)} bytes."
        else:
            text = args.abstract or f"{handler.capitalize()} artefact: {path.name}; MIME {mime}; {len(data)} bytes."

    title = args.title or project.get("title") or path.name
    abstract = args.abstract or project.get("abstract") or project.get("description") or first_paragraph(text, f"{handler} artefact")
    keywords = args.keywords or project.get("keywords") or ""
    if isinstance(keywords, list):
        keywords = ", ".join(keywords)
    classification = args.classification or project.get("classification") or handler
    body_text = clean_text(text)
    segments = TextSegments(title=title, abstract=abstract, keywords=keywords, classification=classification, body=body_text)

    embedding = b""
    embedding_profile_id = PROFILE_NONE
    embedding_policy: dict[str, Any] = {"embedding_mode": "none"}
    if args.embed and arena_class in {CLASS_ARTICLE, CLASS_WEBPAGE, CLASS_METADATA, CLASS_ARCHIVE} and clean_text(text):
        preimage = embedding_source_text(segments, body_text)
        embedding, embedding_policy = bge_small_embedding_f16le(preimage, args.embedding_model)
        embedding_profile_id = embedding_policy["embedding_profile_id"]
        machine_payload = embedding
    elif machine_payload:
        embedding_policy = {
            "embedding_mode": "machine-payload",
            "payload_sha256": sha256_hex(machine_payload),
            "payload_bytes": len(machine_payload),
        }

    swarm_ref = bytes.fromhex(args.swarm_reference) if re.fullmatch(r"[0-9a-fA-F]{64}", args.swarm_reference) else b""
    locators = {
        "swarm_reference": swarm_ref.hex() if swarm_ref else "",
        "ipfs_cid": args.ipfs_cid,
        "ipns_name": args.ipns_name,
        "http_hint": args.http_hint,
    }
    issuer_private = deterministic_private_key(args.issuer_seed)
    schema_sha = sha256_bytes(Path(args.schema).read_bytes()) if args.schema else b"\0" * 32

    card_input = CardInput(
        card_issued_unix=issued,
        work_created_unix=work_created,
        work_revised_unix=work_revised,
        sequence=args.sequence,
        arena_class=arena_class,
        size_class=size_class(len(data)),
        schema_sha256=schema_sha,
        object_sha256=object_sha,
        source_or_manifest_sha256=source_or_manifest,
        issuer_private_key=issuer_private,
        responsible_orcid=args.orcid,
        author_count=0,
        classification_count=classification_count,
        url_count=sum(1 for v in locators.values() if v),
        primary_author_fpr=b"\0" * 32,
        author_list_sha256=sha256_bytes(canonical_json_bytes([])),
        license_id=args.license_id,
        swarm_reference=swarm_ref,
        ipfs_cid=args.ipfs_cid,
        ipns_name=args.ipns_name,
        http_hint=args.http_hint,
        locator_set_sha256=sha256_bytes(canonical_json_bytes(locators)),
        text=segments,
        embedding=machine_payload,
        embedding_profile_id=embedding_profile_id,
    )
    unsigned, pack_meta = pack_unsigned_card(card_input)
    signed = sign_card(unsigned, issuer_private)
    verify_meta = verify_card(signed)
    meta = {
        "schema": "libangel-general-cataloger-rc1",
        "artifact": {
            "path": str(path),
            "sha256": object_sha.hex(),
            "bytes": len(data),
            "mime": mime,
        },
        "handler": handler,
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
        "text_segments": {
            "title": segments.title,
            "abstract": segments.abstract,
            "keywords": segments.keywords,
            "classification": segments.classification,
            "body_sha256": sha256_hex(body_text.encode("utf-8")),
            "embedding_preimage": embedding_source_text(segments, body_text),
        },
        "policy": embedding_policy,
    }
    return signed, meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Mint a general rc1 CXCC catalog card")
    parser.add_argument("artifact")
    parser.add_argument("--out-card", required=True)
    parser.add_argument("--out-meta", required=True)
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    parser.add_argument("--issuer-seed", default=DEFAULT_ISSUER_SEED)
    parser.add_argument("--sequence", type=int, default=1)
    parser.add_argument("--card-issued-unix", type=int)
    parser.add_argument("--work-created-unix", type=int)
    parser.add_argument("--work-revised-unix", type=int)
    parser.add_argument("--title", default="")
    parser.add_argument("--abstract", default="")
    parser.add_argument("--keywords", default="")
    parser.add_argument("--classification", default="")
    parser.add_argument("--orcid", default="")
    parser.add_argument("--license-id", default="CC0-1.0")
    parser.add_argument("--swarm-reference", default="")
    parser.add_argument("--ipfs-cid", default="")
    parser.add_argument("--ipns-name", default="")
    parser.add_argument("--http-hint", default="")
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--no-embed", dest="embed", action="store_false")
    parser.set_defaults(embed=True)
    args = parser.parse_args()

    card, meta = build_card(args)
    out_card = Path(args.out_card)
    out_meta = Path(args.out_meta)
    out_card.parent.mkdir(parents=True, exist_ok=True)
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    out_card.write_bytes(card)
    out_meta.write_text(json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out_card}")
    print(f"wrote {out_meta}")
    print(f"card_id={meta['cxcc']['card_id']}")


if __name__ == "__main__":
    main()
