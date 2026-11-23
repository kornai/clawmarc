"""Single import boundary for the flat reference implementation."""

import sys
from pathlib import Path

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"
if not REFERENCE_DIR.is_dir():
    REFERENCE_DIR = REFERENCE_DIR.with_name("clawmarc_reference")
if str(REFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(REFERENCE_DIR))

from libangel_card import (  # noqa: E402
    ARENA_BYTES,
    CARD_BYTES,
    FLAG_EMBEDDING_PRESENT,
    HEADER_BYTES,
    LAYOUT_MAJOR,
    LAYOUT_MINOR,
    sha256_bytes,
    TextSegments,
    unpack_basic,
)
from libangel_catalog import (  # noqa: E402
    ExtractionError, Prepared, add_run_options, pack_and_sign, prepare_card, resolve_content_policy, signing_context,
)
from libangel_mint import (  # noqa: E402
    EMBEDDING_PROFILES, DEFAULT_EMBEDDING_MODEL, PREIMAGE_RECIPE_V2,
    Chunk, ChunkPlan, body_tokens_for, embedding_policy_meta, plan_chunks,
    reduce_mean_tokw, vector_to_f16le,
    document_embedding_f16le,
    load_embedding_model,
    lookup_embedding_profile,
)
