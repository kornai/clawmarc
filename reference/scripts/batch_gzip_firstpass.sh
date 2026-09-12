#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 CONFIG" >&2
  exit 2
}

[[ $# -eq 1 ]] || usage
CONFIG=$1
[[ -f "$CONFIG" ]] || { echo "missing config: $CONFIG" >&2; exit 2; }

# shellcheck source=/dev/null
. "$CONFIG"

: "${SOURCE_DIR:?}"
: "${WORK_ROOT:?}"
: "${BATCH_DEST:?}"
: "${CARD_DEST:?}"
: "${BATCH_SIZE:?}"
: "${DOCVEC:?}"
: "${SAMPLE_DECOMPRESSED_CHARS:?}"
: "${CLAWMARC_DIR:?}"
: "${PYTHON:?}"
: "${SCHEMA:?}"
: "${LIBANGEL_CATALOG:?}"
: "${COLLECTION_MINTER:?}"

SOURCE_HOST=${SOURCE_HOST:-}
FILE_GLOB=${FILE_GLOB:-"*.gz"}
FILE_MANIFEST=${FILE_MANIFEST:-}
CLASSIFICATION=${CLASSIFICATION:-"gzip.sampled-line-text"}
KEYWORDS=${KEYWORDS:-"gzip, sampled text, first-pass"}
CONTENT_POLICY_NAME=${CONTENT_POLICY_NAME:-"public-academic-text-firstpass-v0"}
CONTENT_POLICY_TEMPLATE=${CONTENT_POLICY_TEMPLATE:-}
ALLOW_TEXT_PREFIX=${ALLOW_TEXT_PREFIX:-"yes"}
ALLOW_DOC_VECTOR=${ALLOW_DOC_VECTOR:-"$DOCVEC"}
ALLOW_IMAGE_THUMBNAIL=${ALLOW_IMAGE_THUMBNAIL:-"no"}
ALLOW_OCR=${ALLOW_OCR:-"no"}
ALLOW_AUDIO_TRANSCRIPT=${ALLOW_AUDIO_TRANSCRIPT:-"no"}
ALLOW_VIDEO_KEYFRAMES=${ALLOW_VIDEO_KEYFRAMES:-"no"}
ALLOW_ARCHIVE_MEMBER_LISTING=${ALLOW_ARCHIVE_MEMBER_LISTING:-"no"}
ALLOW_FULL_DECOMPRESS_HASH=${ALLOW_FULL_DECOMPRESS_HASH:-"no"}
ALLOW_SAMPLE_DECOMPRESS=${ALLOW_SAMPLE_DECOMPRESS:-"yes"}
MEDIA_HASH_ONLY=${MEDIA_HASH_ONLY:-"yes"}
MAX_TEXT_PREFIX_CHARS=${MAX_TEXT_PREFIX_CHARS:-"$SAMPLE_DECOMPRESSED_CHARS"}
CONTENT_POLICY_JSON=${CONTENT_POLICY_JSON:-"$WORK_ROOT/content_policy.json"}
ISSUER_SEED=${ISSUER_SEED:-"LibAngel gzip first-pass issuer v0"}
COLLECTION_ISSUER_SEED=${COLLECTION_ISSUER_SEED:-"LibAngel batch collection issuer v0"}
ORCID=${ORCID:-}
CARD_ISSUED_UNIX=${CARD_ISSUED_UNIX:-}
RSYNC_OPTS=${RSYNC_OPTS:-"-a --partial"}
MAKE_DOUBLY_INDIRECT=${MAKE_DOUBLY_INDIRECT:-"yes"}

MANIFEST_DIR="$WORK_ROOT/manifests"
BATCH_WORK="$WORK_ROOT/batches"
META_WORK="$WORK_ROOT/Meta"
LOG_DIR="$WORK_ROOT/logs"
mkdir -p "$MANIFEST_DIR" "$BATCH_WORK" "$META_WORK" "$LOG_DIR"

MASTER_LIST="$MANIFEST_DIR/files.txt"
RUN_CONFIG_COPY="$META_WORK/run_config.sh"
RUN_MANIFEST="$META_WORK/run_manifest.json"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_DIR/run.log"
}

q() {
  # Single-quote a string for remote sh.
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

source_spec() {
  local rel=$1
  if [[ -n "$SOURCE_HOST" ]]; then
    printf '%s:%s/%s' "$SOURCE_HOST" "$SOURCE_DIR" "$rel"
  else
    printf '%s/%s' "$SOURCE_DIR" "$rel"
  fi
}

rsync_to_dir() {
  local src=$1
  local dst=$2
  # Intentional word splitting for RSYNC_OPTS from config.
  # shellcheck disable=SC2086
  rsync $RSYNC_OPTS "$src" "$dst"
}

yn_bool() {
  case "$1" in
    yes|true|1|on) printf true ;;
    no|false|0|off|"") printf false ;;
    *) echo "bad boolean value: $1" >&2; exit 2 ;;
  esac
}

write_content_policy() {
  if [[ -s "$CONTENT_POLICY_JSON" ]]; then
    log "using existing content policy $CONTENT_POLICY_JSON"
  else
    log "writing content policy $CONTENT_POLICY_JSON"
    "$PYTHON" - "$CONTENT_POLICY_JSON" "$CONTENT_POLICY_TEMPLATE" <<PY
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
template = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else None
policy = {}
if template and template.exists():
    policy.update(json.loads(template.read_text(encoding="utf-8")))
policy.update({
    "profile": policy.get("profile") or policy.get("name") or "$CONTENT_POLICY_NAME",
    "name": "$CONTENT_POLICY_NAME",
    "allow_text_prefix": $(yn_bool "$ALLOW_TEXT_PREFIX"),
    "allow_doc_vector": $(yn_bool "$ALLOW_DOC_VECTOR"),
    "allow_image_thumbnail": $(yn_bool "$ALLOW_IMAGE_THUMBNAIL"),
    "allow_ocr": $(yn_bool "$ALLOW_OCR"),
    "allow_audio_transcript": $(yn_bool "$ALLOW_AUDIO_TRANSCRIPT"),
    "allow_video_keyframes": $(yn_bool "$ALLOW_VIDEO_KEYFRAMES"),
    "allow_archive_member_listing": $(yn_bool "$ALLOW_ARCHIVE_MEMBER_LISTING"),
    "allow_full_decompress_hash": $(yn_bool "$ALLOW_FULL_DECOMPRESS_HASH"),
    "allow_sample_decompress": $(yn_bool "$ALLOW_SAMPLE_DECOMPRESS"),
    "max_text_prefix_chars": int("$MAX_TEXT_PREFIX_CHARS"),
    "media_hash_only": $(yn_bool "$MEDIA_HASH_ONLY"),
})
with open(out, "w", encoding="utf-8") as f:
    json.dump(policy, f, indent=2, sort_keys=True)
    f.write("\\n")
PY
  fi
  cp "$CONFIG" "$RUN_CONFIG_COPY"
  cp "$CONTENT_POLICY_JSON" "$META_WORK/content_policy.json"
  "$PYTHON" - "$RUN_MANIFEST" "$RUN_CONFIG_COPY" "$META_WORK/content_policy.json" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

out, config, policy = map(Path, sys.argv[1:])

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

manifest = {
    "schema": "clawmarc-run-manifest-v0",
    "config_path": str(config),
    "config_sha256": sha(config),
    "content_policy_path": str(policy),
    "content_policy_sha256": sha(policy),
}
out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

ensure_dest_root() {
  local spec=$1
  if [[ "$spec" == *:* && "$spec" != /* ]]; then
    local host=${spec%%:*}
    local path=${spec#*:}
    ssh "$host" "mkdir -p $(q "$path")"
  else
    mkdir -p "$spec"
  fi
}

enumerate_files() {
  if [[ -s "$MASTER_LIST" ]]; then
    log "using existing manifest $MASTER_LIST"
    return
  fi
  if [[ -n "$FILE_MANIFEST" ]]; then
    log "copying configured file manifest $FILE_MANIFEST"
    cp "$FILE_MANIFEST" "$MASTER_LIST"
    return
  fi
  log "enumerating source files"
  if [[ -n "$SOURCE_HOST" ]]; then
    ssh "$SOURCE_HOST" "cd $(q "$SOURCE_DIR") && find . -maxdepth 1 -type f -name $(q "$FILE_GLOB") -printf '%P\n' | sort" > "$MASTER_LIST.tmp"
  else
    (cd "$SOURCE_DIR" && find . -maxdepth 1 -type f -name "$FILE_GLOB" -printf '%P\n' | sort) > "$MASTER_LIST.tmp"
  fi
  mv "$MASTER_LIST.tmp" "$MASTER_LIST"
  log "enumerated $(wc -l < "$MASTER_LIST" | tr -d ' ') files"
}

sample_gzip_text() {
  local gz=$1
  "$PYTHON" - "$gz" "$SAMPLE_DECOMPRESSED_CHARS" <<'PY'
import gzip
import re
import sys

path = sys.argv[1]
limit = int(sys.argv[2])
out = []
remaining = max(limit, 0)
try:
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("# text = "):
                line = line[9:]
            elif line.startswith("# newdoc"):
                line = line.replace("\t", " ")
            elif line.startswith("#") or not line.strip():
                continue
            else:
                parts = line.split("\t")
                if len(parts) >= 2 and parts[0].isdigit():
                    line = parts[1]
            line = re.sub(r"\s+", " ", line).strip()
            if not line:
                continue
            chunk = line + " "
            if len(chunk) > remaining:
                out.append(chunk[:remaining])
                break
            out.append(chunk)
            remaining -= len(chunk)
            if remaining <= 0:
                break
except Exception as exc:
    out = [f"gzip first-pass sample unavailable: {exc}"]
print(re.sub(r"\s+", " ", "".join(out)).strip())
PY
}

mint_direct_card() {
  local file=$1
  local rel=$2
  local out_card=$3
  local out_meta=$4
  local seq=$5
  local abstract
  abstract=$(sample_gzip_text "$file")
  [[ -n "$abstract" ]] || abstract="gzip-compressed artefact; no decompressed UTF-8 prefix sample available"

  local args=(
    "$LIBANGEL_CATALOG" "$file"
    --schema "$SCHEMA"
    --out-card "$out_card"
    --out-meta "$out_meta"
    --issuer-seed "$ISSUER_SEED"
    --sequence "$seq"
    --title "$rel"
    --abstract "$abstract"
    --keywords "$KEYWORDS"
    --classification "$CLASSIFICATION"
    --content-policy "$CONTENT_POLICY_JSON"
  )
  if [[ -n "$ORCID" ]]; then
    args+=(--orcid "$ORCID")
  fi
  if [[ -n "$CARD_ISSUED_UNIX" ]]; then
    args+=(--card-issued-unix "$CARD_ISSUED_UNIX" --work-created-unix "$CARD_ISSUED_UNIX" --work-revised-unix "$CARD_ISSUED_UNIX")
  fi
  if [[ "$DOCVEC" != "yes" ]]; then
    args+=(--no-embed)
  fi
  PYTHONPATH="$CLAWMARC_DIR:$CLAWMARC_DIR/reference" "$PYTHON" "${args[@]}"
}

mint_collection_card() {
  local kind=$1
  local object=$2
  local out_card=$3
  local out_meta=$4
  local title=$5
  local abstract=$6
  local seq=$7
  local args=(
    "$COLLECTION_MINTER"
    --kind "$kind"
    --object "$object"
    --schema "$SCHEMA"
    --out-card "$out_card"
    --out-meta "$out_meta"
    --issuer-seed "$COLLECTION_ISSUER_SEED"
    --sequence "$seq"
    --title "$title"
    --abstract "$abstract"
    --classification "clawmarc.collection"
    --keywords "clawmarc, indirect card, batch"
    --manifest "$RUN_MANIFEST"
  )
  if [[ -n "$ORCID" ]]; then
    args+=(--orcid "$ORCID")
  fi
  if [[ -n "$CARD_ISSUED_UNIX" ]]; then
    args+=(--card-issued-unix "$CARD_ISSUED_UNIX" --work-created-unix "$CARD_ISSUED_UNIX" --work-revised-unix "$CARD_ISSUED_UNIX")
  fi
  PYTHONPATH="$CLAWMARC_DIR:$CLAWMARC_DIR/reference" "$PYTHON" "${args[@]}"
}

push_batch_outputs() {
  local batch_name=$1
  local batch_dir=$2
  local card_dir=$3
  log "pushing $batch_name to $BATCH_DEST and $CARD_DEST"
  rsync_to_dir "$batch_dir/" "$BATCH_DEST/$batch_name/"
  rsync_to_dir "$card_dir/" "$CARD_DEST/$batch_name/"
}

build_batch() {
  local batch_no=$1
  local start=$2
  local end=$3
  local batch_name
  batch_name=$(printf 'Batch_%06d' "$batch_no")
  local dir="$BATCH_WORK/$batch_name"
  local data_dir="$dir/data"
  local card_dir="$dir/cards"
  local state_dir="$dir/.state"
  local list="$dir/filelist.txt"
  mkdir -p "$data_dir" "$card_dir" "$state_dir"

  if [[ -f "$state_dir/transferred.done" ]]; then
    log "$batch_name already transferred; skipping"
    return
  fi

  sed -n "${start},${end}p" "$MASTER_LIST" > "$list"
  local count
  count=$(wc -l < "$list" | tr -d ' ')
  [[ "$count" -gt 0 ]] || return
  log "$batch_name: $count files"

  local idx=0
  while IFS= read -r rel; do
    idx=$((idx + 1))
    local n
    n=$(printf '%06d' "$idx")
    local local_file="$data_dir/$rel"
    local direct_card="$card_dir/direct_${n}.cxcc"
    local direct_meta="$card_dir/direct_${n}.cxcc.json"

    if [[ ! -s "$local_file" ]]; then
      log "$batch_name: staging $rel"
      rsync_to_dir "$(source_spec "$rel")" "$data_dir/"
    fi

    if [[ ! -s "$direct_card" ]]; then
      log "$batch_name: minting direct card $n for $rel"
      mint_direct_card "$local_file" "$rel" "$direct_card.tmp" "$direct_meta.tmp" "$idx"
      mv "$direct_card.tmp" "$direct_card"
      mv "$direct_meta.tmp" "$direct_meta"
    fi

    printf '%s\t%s\t%s\n' "$n" "$rel" "$(basename "$direct_card")" >> "$dir/manifest.jsonl.tmp"
  done < "$list"

  if [[ ! -s "$dir/manifest.jsonl" ]]; then
    mv "$dir/manifest.jsonl.tmp" "$dir/manifest.jsonl"
  else
    rm -f "$dir/manifest.jsonl.tmp"
  fi

  local collection="$card_dir/${batch_name}.cards"
  local indirect="$card_dir/${batch_name}.indirect.cxcc"
  local indirect_meta="$card_dir/${batch_name}.indirect.cxcc.json"
  if [[ ! -s "$indirect" ]]; then
    log "$batch_name: concatenating direct cards"
    find "$card_dir" -maxdepth 1 -type f -name 'direct_*.cxcc' | sort | xargs cat > "$collection.tmp"
    mv "$collection.tmp" "$collection"
    log "$batch_name: minting indirect card"
    mint_collection_card \
      indirect \
      "$collection" \
      "$indirect.tmp" \
      "$indirect_meta.tmp" \
      "$batch_name direct-card collection" \
      "$batch_name: indirect card binding a deterministic concatenation of $count direct clawmarc cards." \
      "$batch_no"
    mv "$indirect.tmp" "$indirect"
    mv "$indirect_meta.tmp" "$indirect_meta"
  fi

  mkdir -p "$META_WORK/$batch_name"
  cp "$indirect" "$META_WORK/$batch_name/"
  cp "$indirect_meta" "$META_WORK/$batch_name/"

  push_batch_outputs "$batch_name" "$dir" "$card_dir"
  touch "$state_dir/transferred.done"
  log "$batch_name: done"
}

build_doubly_indirect() {
  [[ "$MAKE_DOUBLY_INDIRECT" == "yes" ]] || return
  local all="$META_WORK/all_indirect.cards"
  local root_card="$META_WORK/root.doubly_indirect.cxcc"
  local root_meta="$META_WORK/root.doubly_indirect.cxcc.json"
  if [[ -s "$root_card" ]]; then
    log "doubly-indirect card already exists"
  else
    log "building doubly-indirect collection"
    find "$META_WORK" -mindepth 2 -maxdepth 2 -type f -name '*.indirect.cxcc' | sort | xargs cat > "$all.tmp"
    mv "$all.tmp" "$all"
    mint_collection_card \
      doubly-indirect \
      "$all" \
      "$root_card.tmp" \
      "$root_meta.tmp" \
      "root doubly-indirect card collection" \
      "Doubly-indirect card binding deterministic concatenation of all batch indirect cards." \
      1
    mv "$root_card.tmp" "$root_card"
    mv "$root_meta.tmp" "$root_meta"
  fi
  log "pushing Meta cards to $CARD_DEST/Meta"
  rsync_to_dir "$META_WORK/" "$CARD_DEST/Meta/"
}

main() {
  enumerate_files
  write_content_policy
  ensure_dest_root "$BATCH_DEST"
  ensure_dest_root "$CARD_DEST"
  local total batches b start end
  total=$(wc -l < "$MASTER_LIST" | tr -d ' ')
  batches=$(( (total + BATCH_SIZE - 1) / BATCH_SIZE ))
  log "planning $total files in $batches batches of up to $BATCH_SIZE"
  for ((b = 1; b <= batches; b++)); do
    start=$(( (b - 1) * BATCH_SIZE + 1 ))
    end=$(( b * BATCH_SIZE ))
    build_batch "$b" "$start" "$end"
  done
  build_doubly_indirect
  log "all done"
}

main "$@"
