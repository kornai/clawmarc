#!/usr/bin/env python3
"""Content extraction policy hooks for LibAngel producers.

The policy object is mechanism, not governance.  It records what derived
representations this producer is authorized/configured to create during this
run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BUILTIN_PROFILES: dict[str, dict[str, Any]] = {
    "public_library_science": {
        "name": "public_library_science",
        "allow_text_prefix": True,
        "allow_doc_vector": True,
        "allow_image_thumbnail": True,
        "allow_ocr": True,
        "allow_audio_transcript": True,
        "allow_video_keyframes": True,
        "allow_archive_member_listing": True,
        "allow_full_decompress_hash": True,
        "allow_sample_decompress": True,
        "max_text_prefix_chars": 100000,
        "max_image_preview_bytes": 128,
        "media_hash_only": False,
    },
    "public_academic_text_firstpass": {
        "name": "public_academic_text_firstpass",
        "allow_text_prefix": True,
        "allow_doc_vector": False,
        "allow_image_thumbnail": False,
        "allow_ocr": False,
        "allow_audio_transcript": False,
        "allow_video_keyframes": False,
        "allow_archive_member_listing": False,
        "allow_full_decompress_hash": False,
        "allow_sample_decompress": True,
        "max_text_prefix_chars": 3000,
        "max_image_preview_bytes": 0,
        "media_hash_only": True,
    },
    "private_ip_respecting": {
        "name": "private_ip_respecting",
        "allow_text_prefix": True,
        "allow_doc_vector": False,
        "allow_image_thumbnail": False,
        "allow_ocr": False,
        "allow_audio_transcript": False,
        "allow_video_keyframes": False,
        "allow_archive_member_listing": True,
        "allow_full_decompress_hash": False,
        "allow_sample_decompress": True,
        "max_text_prefix_chars": 1200,
        "max_image_preview_bytes": 0,
        "media_hash_only": True,
    },
    "hash_only": {
        "name": "hash_only",
        "allow_text_prefix": False,
        "allow_doc_vector": False,
        "allow_image_thumbnail": False,
        "allow_ocr": False,
        "allow_audio_transcript": False,
        "allow_video_keyframes": False,
        "allow_archive_member_listing": False,
        "allow_full_decompress_hash": False,
        "allow_sample_decompress": False,
        "max_text_prefix_chars": 0,
        "max_image_preview_bytes": 0,
        "media_hash_only": True,
    },
}


DEFAULT_CONTENT_POLICY: dict[str, Any] = dict(BUILTIN_PROFILES["public_library_science"])


def _base_policy(name: str | None) -> dict[str, Any]:
    if name and name in BUILTIN_PROFILES:
        return dict(BUILTIN_PROFILES[name])
    policy = dict(DEFAULT_CONTENT_POLICY)
    if name:
        policy["name"] = name
    return policy


def load_content_policy(path: str | None = None, **overrides: Any) -> dict[str, Any]:
    profile_name = overrides.pop("name", None)
    loaded: dict[str, Any] = {}
    if path:
        loaded_obj = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(loaded_obj, dict):
            raise ValueError("content policy must be a JSON object")
        loaded = loaded_obj
        profile_name = loaded.get("profile") or loaded.get("name") or profile_name

    policy = _base_policy(profile_name)
    policy.update(loaded)
    for key, value in overrides.items():
        if value is not None:
            policy[key] = value
    return policy


def bool_override(allow: bool, deny: bool) -> bool | None:
    if allow and deny:
        raise ValueError("conflicting allow/deny policy flags")
    if allow:
        return True
    if deny:
        return False
    return None


def clamp_text_prefix(text: str, policy: dict[str, Any]) -> str:
    if not policy.get("allow_text_prefix", True):
        return ""
    limit = int(policy.get("max_text_prefix_chars", 3000) or 0)
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()
