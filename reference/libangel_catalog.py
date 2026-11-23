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
import sys
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REFERENCE_DIR = Path(__file__).resolve().parent
if str(REFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(REFERENCE_DIR))

from content_policy import bool_override, clamp_text_prefix, load_content_policy
from libangel_card import (
    CLASS_COLLECTION,
    CLASS_DATASET,
    CLASS_MOVING_IMAGE,
    CLASS_SOFTWARE,
    CLASS_SOUND,
    CLASS_STILL_IMAGE,
    CLASS_TEXT,
    CLASS_UNSPECIFIED,
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
    document_embedding_f16le,
    embedding_source_text,
    PREIMAGE_RECIPE_V2,
    positive_issued_time,
    parse_simple_yaml,
    tex_to_search_text,
)

DEFAULT_SCHEMA = str(REFERENCE_DIR / "clawmarc_catalog_card.h")


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


def image_payload(data: bytes, max_preview_bytes: int = 128) -> bytes:
    if max_preview_bytes < 128:
        return b""
    try:
        from PIL import Image
    except ImportError:
        return b""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("1")
            img.thumbnail((32, 32))
            canvas = Image.new("1", (32, 32), 1)
            x = (32 - img.width) // 2
            y = (32 - img.height) // 2
            canvas.paste(img, (x, y))
            preview = canvas.tobytes()
            if len(preview) > max_preview_bytes:
                return b""
            return b"CXB1" + bytes([32, 32]) + preview
    except Exception:
        return b""


def _decoded_text(data: bytes) -> str:
    # Match Path.read_text's universal newline handling.
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


class ExtractionError(RuntimeError):
    """A required document extractor failed."""


def _extract_with_tool(
    command: list[str], tool_args: list[str], data: bytes, name: Path, path: Path | None,
    strict: bool,
) -> str:
    def extract(input_path: Path) -> str:
        invocation = [*command, str(input_path), *tool_args]
        if not strict:
            return run_text_tool(invocation)
        try:
            result = subprocess.run(invocation, check=True, capture_output=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            detail = exc.stderr.decode("utf-8", errors="replace").strip() if getattr(exc, "stderr", None) else str(exc)
            raise ExtractionError(f"{command[0]} failed on {name.name}: {detail}") from exc
        return result.stdout.decode("utf-8", errors="replace")

    if path is not None:
        return extract(path)
    with tempfile.TemporaryDirectory() as directory:
        input_path = Path(directory) / f"artifact{name.suffix}"
        input_path.write_bytes(data)
        return extract(input_path)


def extract_text(
    data: bytes, name: Path, mime: str, path: Path | None = None, *, strict_tools: bool = False,
) -> tuple[int, str, str, bytes, int]:
    suffix = name.suffix.lower()
    if path is None and mime == "text/plain":
        return CLASS_TEXT, "utf8-text", _decoded_text(data), b"", 1
    if suffix == ".tex":
        text = tex_to_search_text(_decoded_text(data))
        return CLASS_TEXT, "tex-detex", text, b"", 1
    if suffix == ".pdf" or mime == "application/pdf":
        # Text-bearing PDF: pdftotext (poppler). A scanned PDF yields no text and
        # falls through to a descriptor-only card; OCR is a policy decision left
        # to the caller (see content_policy allow_ocr).
        text = _extract_with_tool(["pdftotext", "-layout", "-enc", "UTF-8"], ["-"], data, name, path, strict_tools)
        return CLASS_TEXT, "pdftotext", text, b"", 1 if text.strip() else 0
    if suffix == ".epub":
        text = _extract_with_tool(["pandoc", "--from", "epub", "--to", "plain"], [], data, name, path, strict_tools)
        return CLASS_TEXT, "epub-pandoc", text, b"", 1 if text.strip() else 0
    if suffix in {".html", ".htm"} or mime == "text/html":
        text = _extract_with_tool(["pandoc", "--from", "html", "--to", "plain"], [], data, name, path, strict_tools)
        if not text:
            text = _decoded_text(data)
        return CLASS_TEXT, "html-pandoc", text, b"", 1
    if suffix in {".md", ".txt"} or mime.startswith("text/"):
        return CLASS_TEXT, "utf8-text", _decoded_text(data), b"", 1
    if suffix == ".docx":
        text = _extract_with_tool(["docx2txt"], ["-"], data, name, path, strict_tools)
        return CLASS_TEXT, "docx2txt", text, b"", 1 if text else 0
    if suffix == ".doc":
        text = _extract_with_tool(["catdoc"], [], data, name, path, strict_tools)
        return CLASS_TEXT, "catdoc", text, b"", 1 if text else 0
    return 0, "", "", b"", 0


def zip_project_metadata(archive: bytes) -> tuple[dict[str, Any], bytes, str]:
    try:
        with zipfile.ZipFile(io.BytesIO(archive), "r") as zf:
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
    # Coarse type -> DCMI Type Vocabulary class. Subject description is NOT
    # decided here; it goes in the classification text and the machine payload.
    suffix = path.suffix.lower()
    if mime.startswith("image/"):
        return CLASS_STILL_IMAGE, "image"
    if mime.startswith("video/"):
        return CLASS_MOVING_IMAGE, "video"
    if mime.startswith("audio/"):
        return CLASS_SOUND, "audio"
    if suffix in {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z"}:
        return CLASS_COLLECTION, "archive"
    if suffix in {".json", ".yaml", ".yml", ".xml", ".csv", ".tsv", ".parquet", ".sqlite", ".db"}:
        return CLASS_DATASET, "dataset"
    if suffix in {".safetensors", ".pt", ".pth", ".onnx"}:
        return CLASS_DATASET, "model-weights"
    if suffix in {".bin", ".exe", ".dylib", ".so", ".o", ".a"} or mime.startswith("application/x-"):
        return CLASS_SOFTWARE, "software"
    if mime == "application/octet-stream":
        return CLASS_UNSPECIFIED, "opaque"
    return CLASS_TEXT, "generic"


@dataclass(frozen=True)
class SigningContext:
    schema_sha: bytes
    issuer_private: Any
    issuer_public: str


def signing_context(args: argparse.Namespace) -> SigningContext:
    private = deterministic_private_key(args.issuer_seed)
    schema_sha = sha256_bytes(Path(args.schema).read_bytes()) if args.schema else bytes(32)
    return SigningContext(schema_sha, private, public_key_pem(private).strip())


@dataclass
class Prepared:
    name: str
    artifact_path: str
    nbytes: int
    object_sha256: bytes
    mime: str
    arena_class: int
    handler: str
    classification_count: int
    machine_payload: bytes
    source_or_manifest_sha256: bytes
    segments: TextSegments
    extracted_text: str
    title_source: str
    full_text: str
    body_text: str
    content_policy: dict[str, Any]
    wants_vector: bool
    preimage: str


def resolve_content_policy(args: argparse.Namespace) -> dict[str, Any]:
    return load_content_policy(
        args.content_policy,
        name=args.policy_name,
        allow_text_prefix=bool_override(args.allow_text_prefix, args.no_text_prefix),
        allow_doc_vector=bool_override(args.allow_doc_vector, args.no_doc_vector or not args.embed),
        allow_image_thumbnail=bool_override(args.allow_image_thumbnail, args.no_image_thumbnail),
        allow_ocr=bool_override(args.allow_ocr, args.no_ocr),
        max_text_prefix_chars=args.max_text_prefix_chars,
    )


def prepare_card(
    data: bytes, name: str, args: argparse.Namespace, *, path: Path | None = None,
    mime: str | None = None, content_policy: dict[str, Any] | None = None,
    dataset_title: str | None = None, synthetic_title: str | None = None,
    preimage_recipe: str = PREIMAGE_RECIPE_V2, strict_tools: bool = False,
) -> Prepared:
    name_path = Path(name)
    if mime is None:
        mime = (
            detect_mime(path) if path is not None
            else mimetypes.guess_type(name)[0] or "application/octet-stream"
        )
    content_policy = content_policy if content_policy is not None else resolve_content_policy(args)

    arena_class, handler, text, machine_payload, classification_count = extract_text(data, name_path, mime, path, strict_tools=strict_tools)
    project: dict[str, Any] = {}
    source_or_manifest = b"\0" * 32
    if not handler and zipfile.is_zipfile(io.BytesIO(data)):
        project, manifest_bytes, text = zip_project_metadata(data)
        arena_class = CLASS_COLLECTION
        handler = "clawxiv-zip" if project else "archive"
        if manifest_bytes:
            source_or_manifest = sha256_bytes(manifest_bytes)

    if not handler:
        arena_class, handler = classify(name_path, mime)
        if arena_class == CLASS_STILL_IMAGE:
            machine_payload = (
                image_payload(data, int(content_policy.get("max_image_preview_bytes", 128) or 0))
                if content_policy.get("allow_image_thumbnail")
                else b""
            )
            text = args.abstract or f"Image artefact: {name_path.name}; MIME {mime}; {len(data)} bytes."
        else:
            text = args.abstract or f"{handler.capitalize()} artefact: {name_path.name}; MIME {mime}; {len(data)} bytes."

    titles = (
        (args.title, "cli"), (dataset_title, "dataset"), (project.get("title"), "metadata"),
        (synthetic_title, "synthetic"), (name_path.name, "filename"),
    )
    title, title_source = next(item for item in titles if item[0])
    abstract = args.abstract or project.get("abstract") or project.get("description") or first_paragraph(text, f"{handler} artefact")
    keywords = args.keywords or project.get("keywords") or ""
    if isinstance(keywords, list):
        keywords = ", ".join(keywords)
    classification = args.classification or project.get("classification") or handler
    full_text = clean_text(text)
    body_text = clamp_text_prefix(full_text, content_policy)
    segments = TextSegments(title=title, abstract=abstract, keywords=keywords, classification=classification, body=body_text)

    extracted_text = unicodedata.normalize("NFC", text)
    preimage = embedding_source_text(
        segments, full_text, recipe=preimage_recipe, include_title=title_source not in {"synthetic", "filename"},
    )
    return Prepared(
        name=name, artifact_path=str(path) if path is not None else name,
        nbytes=len(data), object_sha256=sha256_bytes(data), mime=mime,
        arena_class=arena_class, handler=handler, classification_count=classification_count,
        machine_payload=machine_payload, source_or_manifest_sha256=source_or_manifest,
        segments=segments, extracted_text=extracted_text, title_source=title_source, full_text=full_text, body_text=body_text, content_policy=content_policy,
        wants_vector=bool(
            content_policy.get("allow_doc_vector")
            and arena_class in {CLASS_TEXT, CLASS_DATASET, CLASS_COLLECTION}
            and full_text
        ),
        preimage=preimage,
    )


def pack_and_sign(
    prep: Prepared, embedding: bytes, embedding_policy: dict[str, Any], args: argparse.Namespace,
    *, verify: bool = True, include_preimage: bool = True,
    signing: SigningContext | None = None, record_title_source: bool = False,
) -> tuple[bytes, dict[str, Any]]:
    issued = utc_now() if args.card_issued_unix is None else positive_issued_time(args.card_issued_unix)
    work_created = args.work_created_unix if args.work_created_unix is not None else issued
    work_revised = args.work_revised_unix if args.work_revised_unix is not None else issued
    machine_payload = embedding if embedding else prep.machine_payload
    profile_id = embedding_policy["embedding_profile_id"] if embedding else PROFILE_NONE
    if not embedding and machine_payload:
        embedding_policy = {
            "embedding_mode": "machine-payload",
            "payload_sha256": sha256_hex(machine_payload),
            "payload_bytes": len(machine_payload),
        }
    segments = prep.segments
    swarm_ref = bytes.fromhex(args.swarm_reference) if re.fullmatch(r"[0-9a-fA-F]{64}", args.swarm_reference) else b""
    locators = {
        "swarm_reference": swarm_ref.hex() if swarm_ref else "",
        "ipfs_cid": args.ipfs_cid,
        "ipns_name": args.ipns_name,
        "http_hint": args.http_hint,
    }
    signing = signing if signing is not None else signing_context(args)
    issuer_private = signing.issuer_private

    card_input = CardInput(
        card_issued_unix=issued,
        work_created_unix=work_created,
        work_revised_unix=work_revised,
        sequence=args.sequence,
        arena_class=prep.arena_class,
        size_class=size_class(prep.nbytes),
        schema_sha256=signing.schema_sha,
        object_sha256=prep.object_sha256,
        source_or_manifest_sha256=prep.source_or_manifest_sha256,
        issuer_private_key=issuer_private,
        responsible_orcid=args.orcid,
        author_count=0,
        classification_count=prep.classification_count,
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
        embedding_profile_id=profile_id,
    )
    unsigned, pack_meta = pack_unsigned_card(card_input)
    signed = sign_card(unsigned, issuer_private)
    verify_meta = verify_card(signed) if verify else {}
    meta = {
        "schema": "libangel-general-cataloger-rc1",
        "artifact": {
            "path": prep.artifact_path,
            "sha256": prep.object_sha256.hex(),
            "bytes": prep.nbytes,
            "mime": prep.mime,
        },
        "handler": prep.handler,
        "cxcc": {
            "card_bytes": len(signed),
            "card_id": card_id(signed).hex(),
            "card_content_id": card_content_id(signed).hex(),
            **pack_meta,
            **verify_meta,
        },
        "issuer": {
            "seed_label": args.issuer_seed,
            "public_key_pem": signing.issuer_public,
            "key_kind": "deterministic-test-seed",
            "key_note": ("Private key derived from the public seed label; forgeable by design. "
                         "The signature attests reproducibility, not issuer identity."),
        },
        "text_segments": {
            "title": segments.title,
            "abstract": segments.abstract,
            "keywords": segments.keywords,
            "classification": segments.classification,
            "body_sha256": sha256_hex(prep.body_text.encode("utf-8")),
        },
        "policy": embedding_policy,
        "content_policy": prep.content_policy,
    }
    if record_title_source:
        meta["text_segments"]["title_source"] = prep.title_source
    if include_preimage:
        meta["text_segments"]["embedding_preimage"] = prep.preimage
    elif prep.wants_vector:
        meta["text_segments"]["embedding_preimage_sha256"] = sha256_hex(prep.preimage.encode("utf-8"))
    return signed, meta


def build_card(args: argparse.Namespace, *, legacy_embedding: bool = False) -> tuple[bytes, dict[str, Any]]:
    path = Path(args.artifact)
    # Resolve the original default at the start of minting, before extraction or embedding.
    issued = utc_now() if args.card_issued_unix is None else positive_issued_time(args.card_issued_unix)
    args = argparse.Namespace(**(vars(args) | {"card_issued_unix": issued}))
    recipe = PREIMAGE_RECIPE_V2 if args.embed and not legacy_embedding else "body/v1"
    prep = prepare_card(path.read_bytes(), path.name, args, path=path, preimage_recipe=recipe)
    embedding, policy = b"", {"embedding_mode": "none"}
    if prep.wants_vector:
        embedding, policy = document_embedding_f16le(prep.preimage, args.embedding_model, recipe=recipe)
    return pack_and_sign(prep, embedding, policy, args, record_title_source=bool(embedding) and not legacy_embedding)


def license_id(value: str) -> str:
    if not value.isascii() or len(value) > 8:
        raise argparse.ArgumentTypeError("license ID must be at most 8 ASCII bytes, e.g. CC-BY-SA")
    return value


def add_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    parser.add_argument("--issuer-seed", default=DEFAULT_ISSUER_SEED)
    parser.add_argument("--card-issued-unix", "--issued-unix", type=positive_issued_time)
    parser.add_argument("--work-created-unix", type=int)
    parser.add_argument("--work-revised-unix", type=int)
    parser.add_argument("--orcid", default="")
    parser.add_argument("--license-id", type=license_id, default="CC0-1.0")
    parser.add_argument("--swarm-reference", default="")
    parser.add_argument("--ipfs-cid", default="")
    parser.add_argument("--ipns-name", default="")
    parser.add_argument("--http-hint", default="")
    parser.add_argument("--content-policy", help="JSON content extraction policy")
    parser.add_argument("--policy-name")
    parser.add_argument("--max-text-prefix-chars", type=int)
    parser.add_argument("--allow-text-prefix", action="store_true")
    parser.add_argument("--no-text-prefix", action="store_true")
    parser.add_argument("--allow-doc-vector", action="store_true")
    parser.add_argument("--no-doc-vector", action="store_true")
    parser.add_argument("--allow-image-thumbnail", action="store_true")
    parser.add_argument("--no-image-thumbnail", action="store_true")
    parser.add_argument("--allow-ocr", action="store_true")
    parser.add_argument("--no-ocr", action="store_true")
    parser.add_argument("--no-embed", dest="embed", action="store_false")
    parser.set_defaults(embed=True)


def add_card_options(parser: argparse.ArgumentParser) -> None:
    add_run_options(parser)
    parser.add_argument("--sequence", type=int, default=1)
    parser.add_argument("--title", default="")
    parser.add_argument("--abstract", default="")
    parser.add_argument("--keywords", default="")
    parser.add_argument("--classification", default="")
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mint a general rc1 CXCC catalog card")
    parser.add_argument("artifact")
    parser.add_argument("--out-card", required=True)
    parser.add_argument("--out-meta", required=True)
    add_card_options(parser)
    args = parser.parse_args()

    try:
        card, meta = build_card(args)
    except ValueError as exc:
        parser.error(str(exc))
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
