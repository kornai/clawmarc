#!/usr/bin/env bash
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PY=${PYTHON:-python3}

echo "== required files"
test -f "$ROOT/draft-kornai-clawmarc-00.xml"
test -f "$ROOT/draft-kornai-clawmarc-01.md"
test -f "$ROOT/draft-kornai-clawmarc-01.xml"
test -f "$ROOT/reference/clawmarc_catalog_card.h"
test -f "$ROOT/reference/libangel_card.py"
test -f "$ROOT/content_policy.py"
test -f "$ROOT/content_policies/public_library_science.json"
test -f "$ROOT/scripts/batch_gzip_firstpass.sh"
test -f "$ROOT/scripts/mint_collection_card.py"
test -f "$ROOT/cards/reference_dropofwater.cxcc"

echo "== header compile"
cat > /private/tmp/clawmarc_repo_header_check.c <<EOF
#include "$ROOT/reference/clawmarc_catalog_card.h"
int main(void) {
    return sizeof(ClawXivCatalogCardV1) == 4096 ? 0 : 1;
}
EOF
cc -std=c11 -Wall -Wextra -Werror -o /private/tmp/clawmarc_repo_header_check /private/tmp/clawmarc_repo_header_check.c
/private/tmp/clawmarc_repo_header_check

echo "== python compile"
env PYTHONPYCACHEPREFIX=/private/tmp/clawmarc-repo-pycache "$PY" -m py_compile \
  "$ROOT/content_policy.py" \
  "$ROOT/libangel_catalog.py" \
  "$ROOT/libangel_mint.py" \
  "$ROOT/libangel_inspect.py" \
  "$ROOT/reference/libangel_card.py" \
  "$ROOT/scripts/mint_collection_card.py"

echo "== shell syntax"
bash -n "$ROOT/scripts/batch_gzip_firstpass.sh"

echo "== reference card"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT:$ROOT/reference" "$PY" "$ROOT/libangel_inspect.py" "$ROOT/cards/reference_dropofwater.cxcc" >/private/tmp/clawmarc-repo-card.inspect
grep -q '^object_sha256: 325a3123ad5f4bc43a3a26358163764d20546e454a5759239b4c3f412f488c51$' /private/tmp/clawmarc-repo-card.inspect

echo "OK"
