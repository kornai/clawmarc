#!/usr/bin/env bash
set -euo pipefail
source_spec=msmarco":${1:-passage}"
if (( $# )); then shift; fi
exec "${MINTKIT_PYTHON:-python3}" -m mintkit mint "$source_spec" "$@"
