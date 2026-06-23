#!/usr/bin/env python3
"""Inspect and verify a CXCC catalog card."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from libangel_card import unpack_basic


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a CXCC card")
    parser.add_argument("card")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    info = unpack_basic(Path(args.card).read_bytes())
    if args.json:
        print(json.dumps(info, indent=2, ensure_ascii=False, sort_keys=True))
        return
    for key in [
        "card_id",
        "card_content_id",
        "issuer_fingerprint_prefix",
        "object_sha256",
        "schema_sha256",
        "arena_split",
        "arena_class",
        "size_class",
        "flags",
        "card_issued_unix",
        "sequence",
        "responsible_orcid",
        "author_count",
        "swarm_reference",
        "ipfs_cid",
        "ipns_name",
        "http_hint",
        "embedding_profile_id",
        "title",
        "keywords",
        "classification",
    ]:
        print(f"{key}: {info[key]}")


if __name__ == "__main__":
    main()
