#!/usr/bin/env python3
"""Mint an indirect or doubly-indirect clawmarc card for a card collection."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "reference"))

from libangel_card import (
    ACCESS_OPEN,
    ENC_NONE,
    CLASS_INDIRECT_CATALOG_CARD,
    CLASS_DOUBLY_INDIRECT_CATALOG_CARD,
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


DEFAULT_ISSUER_SEED = "LibAngel batch collection issuer v0"


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Mint clawmarc collection cards")
    parser.add_argument("--object", required=True, help="Concatenated card artefact to bind")
    parser.add_argument("--out-card", required=True)
    parser.add_argument("--out-meta", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--kind", choices=["indirect", "doubly-indirect"], required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--abstract", required=True)
    parser.add_argument("--keywords", default="clawmarc, catalog cards")
    parser.add_argument("--classification", default="clawmarc.collection")
    parser.add_argument("--issuer-seed", default=DEFAULT_ISSUER_SEED)
    parser.add_argument("--manifest", help="Optional run/config manifest to bind in source_or_manifest_sha256")
    parser.add_argument("--sequence", type=int, default=1)
    parser.add_argument("--card-issued-unix", type=int)
    parser.add_argument("--work-created-unix", type=int)
    parser.add_argument("--work-revised-unix", type=int)
    parser.add_argument("--orcid", default="")
    parser.add_argument("--http-hint", default="")
    args = parser.parse_args()

    obj_path = Path(args.object)
    obj = obj_path.read_bytes()
    schema = Path(args.schema).read_bytes()
    manifest_bytes = Path(args.manifest).read_bytes() if args.manifest else b""
    issued = args.card_issued_unix or utc_now()
    work_created = args.work_created_unix if args.work_created_unix is not None else issued
    work_revised = args.work_revised_unix if args.work_revised_unix is not None else issued
    private = deterministic_private_key(args.issuer_seed)
    locators = {
        "swarm_reference": "",
        "ipfs_cid": "",
        "ipns_name": "",
        "http_hint": args.http_hint,
    }
    arena_class = (
        CLASS_INDIRECT_CATALOG_CARD
        if args.kind == "indirect"
        else CLASS_DOUBLY_INDIRECT_CATALOG_CARD
    )
    card_input = CardInput(
        card_issued_unix=issued,
        work_created_unix=work_created,
        work_revised_unix=work_revised,
        sequence=args.sequence,
        arena_class=arena_class,
        size_class=size_class(len(obj)),
        schema_sha256=sha256_bytes(schema),
        object_sha256=sha256_bytes(obj),
        source_or_manifest_sha256=sha256_bytes(manifest_bytes) if manifest_bytes else b"\0" * 32,
        issuer_private_key=private,
        responsible_orcid=args.orcid,
        author_count=0,
        classification_count=1 if args.classification else 0,
        url_count=1 if args.http_hint else 0,
        primary_author_fpr=b"\0" * 32,
        author_list_sha256=sha256_bytes(canonical_json_bytes([])),
        license_id="CC0-1.0",
        swarm_reference=b"",
        ipfs_cid="",
        ipns_name="",
        http_hint=args.http_hint,
        locator_set_sha256=sha256_bytes(canonical_json_bytes(locators)),
        text=TextSegments(
            title=args.title,
            abstract=args.abstract,
            keywords=args.keywords,
            classification=args.classification,
            body="",
        ),
        embedding=b"",
        embedding_profile_id=PROFILE_NONE,
    )
    unsigned, pack_meta = pack_unsigned_card(card_input)
    signed = sign_card(unsigned, private)
    verify_meta = verify_card(signed)
    meta = {
        "schema": "clawmarc-collection-card-v0",
        "collection": {
            "kind": args.kind,
            "object_path": str(obj_path),
            "object_bytes": len(obj),
            "object_sha256": sha256_hex(obj),
            "manifest_path": args.manifest or "",
            "manifest_sha256": sha256_hex(manifest_bytes) if manifest_bytes else "",
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
            "public_key_pem": public_key_pem(private).strip(),
        },
        "locators": locators,
        "text_segments": {
            "title": args.title,
            "abstract": args.abstract,
            "keywords": args.keywords,
            "classification": args.classification,
        },
    }
    out_card = Path(args.out_card)
    out_meta = Path(args.out_meta)
    out_card.parent.mkdir(parents=True, exist_ok=True)
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    out_card.write_bytes(signed)
    out_meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out_card}")
    print(f"wrote {out_meta}")
    print(f"card_id={meta['cxcc']['card_id']}")


if __name__ == "__main__":
    main()
