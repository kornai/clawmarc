#!/usr/bin/env bash
# push_github_release.sh — upload the four model archives (plus SHA256SUMS,
# PUBLISH_MANIFEST.md, CARD_INDEX.md) as assets of a GitHub Release on
# kornai/clawmarc, with a live progress meter, per-file speed, and a log.
#
#   ./push_github_release.sh            # release tag v1.rc3 (default)
#   TAG=v1.rc4 ./push_github_release.sh # another tag
#
# Idempotent: assets already present at the right size are skipped; partial or
# mismatched assets are deleted and re-uploaded (GitHub asset uploads cannot be
# resumed). Needs the GitHub CLI (gh) logged in with repo scope.
set -u
REPO=kornai/clawmarc
TAG=${TAG:-v1.rc3}
HERE=$(cd "$(dirname "$0")" && pwd)
ARCH="$HERE/archives"
LOG="$HERE/../../Blackboard/github_release_$(date +%Y%m%d).log"
FILES=(bge-small-en-v1.5.tar.zst
       bert-base-multilingual-cased.tar.zst
       paraphrase-multilingual-mpnet-base-v2.tar.zst
       xlm-roberta-base.tar.zst)
EXTRA=(SHA256SUMS PUBLISH_MANIFEST.md CARD_INDEX.md
       cards/bge-small-en-v1.5.cxcc cards/bge-small-en-v1.5.cxcc.json
       cards/bert-base-multilingual-cased.cxcc cards/bert-base-multilingual-cased.cxcc.json
       cards/paraphrase-multilingual-mpnet-base-v2.cxcc cards/paraphrase-multilingual-mpnet-base-v2.cxcc.json
       cards/xlm-roberta-base.cxcc cards/xlm-roberta-base.cxcc.json)

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG"; }
human() { awk -v b="$1" 'BEGIN{ if (b>=1073741824) printf "%.2f GB", b/1073741824; else if (b>=1048576) printf "%.1f MB", b/1048576; else printf "%d KB", b/1024 }'; }

command -v gh >/dev/null || { echo "gh (GitHub CLI) not found — brew install gh"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "not logged in — run: gh auth login"; exit 1; }
TOKEN=$(gh auth token)

if ! gh release view "$TAG" -R "$REPO" >/dev/null 2>&1; then
  log "creating release $TAG on $REPO"
  gh release create "$TAG" -R "$REPO" --title "clawmarc $TAG" --notes \
    "Opaque model archives (.tar.zst) for the four embedding models evaluated in the WADL 2026 paper, with SHA256SUMS and the publication manifest. Their root cards are in src/model_resources/cards/; each card binds its archive by SHA-256." \
    || { log "release creation failed"; exit 1; }
fi
RID=$(gh api "repos/$REPO/releases/tags/$TAG" --jq .id) || { log "cannot resolve release id"; exit 1; }

asset_field() { gh api "repos/$REPO/releases/$RID/assets" --jq ".[] | select(.name==\"$1\") | .$2" 2>/dev/null; }

upload() {
  local f=$1 name size have attempt t0 dt
  name=$(basename "$f"); size=$(stat -f%z "$f")
  have=$(asset_field "$name" size)
  if [ "${have:-}" = "$size" ]; then log "skip   $name — already uploaded ($(human "$size"))"; return 0; fi
  if [ -n "${have:-}" ]; then
    log "delete $name — partial/mismatched asset on server ($have bytes)"
    gh api -X DELETE "repos/$REPO/releases/assets/$(asset_field "$name" id)" >/dev/null
  fi
  attempt=1
  while [ "$attempt" -le 3 ]; do
    log "upload $name ($(human "$size")) attempt $attempt"
    t0=$(date +%s)
    # -T streams the file (no in-memory copy); the progress meter goes to stderr.
    if curl --fail --progress-meter -o /dev/null -X POST -T "$f" \
         -H "Authorization: token $TOKEN" -H "Content-Type: application/octet-stream" \
         "https://uploads.github.com/repos/$REPO/releases/$RID/assets?name=$name"; then
      dt=$(( $(date +%s) - t0 )); [ "$dt" -eq 0 ] && dt=1
      have=$(asset_field "$name" size)
      if [ "$have" = "$size" ]; then
        log "done   $name in ${dt}s — $(human $((size / dt)))/s average, size verified on server"
        return 0
      fi
      log "size mismatch after upload ($have vs $size) — deleting and retrying"
      gh api -X DELETE "repos/$REPO/releases/assets/$(asset_field "$name" id)" >/dev/null
    else
      log "curl failed for $name (attempt $attempt)"
    fi
    attempt=$((attempt + 1)); sleep 15
  done
  log "GAVE UP on $name after 3 attempts"; return 1
}

log "== release $TAG (id $RID) on $REPO — log: $LOG"
rc=0
for n in "${FILES[@]}"; do upload "$ARCH/$n" || rc=1; done
for n in "${EXTRA[@]}"; do upload "$HERE/$n"  || rc=1; done
log "== assets on the release now:"
gh api "repos/$REPO/releases/$RID/assets" --jq '.[] | "\(.name)\t\(.size)\t\(.browser_download_url)"' | tee -a "$LOG"
[ "$rc" -eq 0 ] && log "== ALL DONE" || log "== FINISHED WITH FAILURES (rerun to retry; completed assets are skipped)"
exit $rc
