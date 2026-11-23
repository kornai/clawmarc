#!/usr/bin/env bash
set -euo pipefail
source_spec=mldr":${1:-en}"
if (( $# )); then shift; fi
exec "${MINTKIT_PYTHON:-python3}" -m mintkit mint "$source_spec" "$@"
