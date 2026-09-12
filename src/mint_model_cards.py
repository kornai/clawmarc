#!/usr/bin/env python3
"""Mint signed, text-only Clawmarc cards for opaque model archives."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "reference"))
from libangel_card import (  # noqa: E402
    ACCESS_OPEN,
    CLASS_SOFTWARE,
    ENC_NONE,
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


ROOT = Path(__file__).resolve().parent
# The schema digest binds the normative layout, the C header — the same object
# the two reference cards bind (provenance.json: schema_sha256 1dfaee46…).
SCHEMA = ROOT.parent / "reference" / "clawmarc_catalog_card.h"
ARCHIVES = ROOT / "model_resources" / "archives"
CARDS = ROOT / "model_resources" / "cards"
ISSUER_SEED = "clawmarc model resource issuer v1"

MODELS = {
    "bge-small-en-v1.5": "BAAI/bge-small-en-v1.5",
    "bert-base-multilingual-cased": "bert-base-multilingual-cased",
    "xlm-roberta-base": "xlm-roberta-base",
    "paraphrase-multilingual-mpnet-base-v2": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
}


def _load_locator_tsv(path: Path) -> dict[str, str]:
    """Map archive filename -> value from a two-plus-column TSV with a header row."""
    table: dict[str, str] = {}
    if not path.exists():
        return table
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0]:
            table[parts[0]] = parts[1]
    return table


# Network locators are recorded once the objects have stable identifiers and
# folded into the signed cards here. IPFS_CIDS.tsv is written by push_ipfs.sh;
# SWARM_REFS.tsv by the bee upload. Absent files leave the locators empty.
IPFS_CIDS = _load_locator_tsv(ROOT / "model_resources" / "IPFS_CIDS.tsv")
SWARM_REFS = _load_locator_tsv(ROOT / "model_resources" / "SWARM_REFS.tsv")


def size_class(size: int) -> int:
    if size == 0:
        return 0
    limits = [10**3, 10**6, 10**9, 10**12, 10**15, 10**18, 10**21, 10**24]
    for idx, limit in enumerate(limits, start=2):
        if size <= limit:
            return idx
    return 9


def readme_for(directory: Path, model_id: str) -> str:
    candidates = sorted(directory.glob("README*"))
    if candidates:
        text = candidates[0].read_text(encoding="utf-8", errors="replace")
    else:
        text = (
            f"Model resource: {model_id}. This archive contains the complete "
            "locally cached model directory, including configuration, tokenizer, "
            "and weight files. No model README was present in the local directory."
        )
    return re.sub(r"\s+", " ", text).strip()


def mint(archive: Path) -> None:
    stem = archive.name.removesuffix(".tar.zst")
    model_id = MODELS[stem]
    data = archive.read_bytes()
    source_dir = ROOT / "model_resources" / "source" / stem
    if not source_dir.exists():
        source_dir = Path("/Volumes/114/Sandbox") / stem
    readme = readme_for(source_dir, model_id)
    now = int(time.time())
    # HTTPS sources: lebadus.ai (the hint, packed into the card) and the
    # GitHub release assets (second mirror, in the signed locator set).
    # kornai.homeip.net was dropped (unreliable storage) per AK, 2026-09-11.
    urls = [
        f"https://lebadus.ai/Resources/Models/{archive.name}",
        f"https://github.com/kornai/clawmarc/releases/download/v1.rc3/{archive.name}",
    ]
    cid = IPFS_CIDS.get(archive.name, "")
    swarm_hex = SWARM_REFS.get(archive.name, "")
    title = f"{model_id} model archive ({archive.name})"
    abstract = (
        f"Opaque binary release of {model_id}, archived as {archive.name}. "
        "The card binds the exact archive bytes by SHA-256; it carries no document vector."
    )
    keywords = f"embedding model, {model_id}, model archive, retrieval"
    classification = "software; machine-learning model; opaque binary"
    locators = {"http_hint": urls[0], "http_mirrors": urls, "ipfs_cid": cid, "swarm_reference": swarm_hex}
    private = deterministic_private_key(ISSUER_SEED)
    card_input = CardInput(
        card_issued_unix=now,
        work_created_unix=now,
        work_revised_unix=now,
        sequence=1,
        arena_class=CLASS_SOFTWARE,
        size_class=size_class(len(data)),
        schema_sha256=sha256_bytes(SCHEMA.read_bytes()),
        object_sha256=sha256_bytes(data),
        source_or_manifest_sha256=sha256_bytes(canonical_json_bytes({"model": model_id, "archive": archive.name})),
        issuer_private_key=private,
        responsible_orcid="",
        author_count=0,
        classification_count=1,
        url_count=len(urls),
        primary_author_fpr=b"\0" * 32,
        author_list_sha256=sha256_bytes(canonical_json_bytes([])),
        license_id="SEE-RDME",
        swarm_reference=bytes.fromhex(swarm_hex) if swarm_hex else b"",
        ipfs_cid=cid,
        ipns_name="",
        http_hint=urls[0],
        locator_set_sha256=sha256_bytes(canonical_json_bytes(locators)),
        text=TextSegments(title=title, abstract=abstract, keywords=keywords,
                          classification=classification, body=readme),
        embedding=b"",
        embedding_profile_id=PROFILE_NONE,
    )
    unsigned, packed = pack_unsigned_card(card_input)
    signed = sign_card(unsigned, private)
    verify = verify_card(signed)
    out_card = CARDS / f"{stem}.cxcc"
    out_meta = CARDS / f"{stem}.cxcc.json"
    out_card.write_bytes(signed)
    meta = {
        "schema": "clawmarc-opaque-model-card-v1",
        "artifact": {"path": str(archive), "bytes": len(data), "sha256": sha256_hex(data)},
        "model": model_id,
        "readme_sha256": sha256_hex(readme.encode("utf-8")),
        "locators": locators,
        "embedding": {"profile_id": PROFILE_NONE, "present": False, "reason": "opaque binary artifact"},
        "issuer": {"seed_label": ISSUER_SEED, "public_key_pem": public_key_pem(private).strip(),
                   "key_kind": "deterministic-test-seed",
                   "key_note": "Private key is derived from the public seed label and is forgeable by "
                               "design; the signature attests reproducibility, not issuer identity."},
        "cxcc": {"card_bytes": len(signed), "card_id": card_id(signed).hex(),
                 "card_content_id": card_content_id(signed).hex(), **packed, **verify},
        "text": {"title": title, "abstract": abstract, "keywords": keywords,
                 "classification": classification, "readme": readme},
    }
    out_meta.write_text(json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{stem}: artifact_sha256={sha256_hex(data)} card_id={verify['card_id']}")


def main() -> None:
    CARDS.mkdir(parents=True, exist_ok=True)
    for archive in sorted(ARCHIVES.glob("*.tar.zst")):
        mint(archive)


if __name__ == "__main__":
    main()
