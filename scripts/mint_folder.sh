#!/usr/bin/env bash
set -euo pipefail
source_spec=folder":${1:?Pass a document folder}"
if (( $# )); then shift; fi
exec "${MINTKIT_PYTHON:-python3}" -m mintkit mint "$source_spec" "$@"
