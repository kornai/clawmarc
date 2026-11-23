#!/usr/bin/env bash
set -euo pipefail

device="${1:?Pass cpu, cuda, or mps}"
shift
python_bin="${MINTKIT_PYTHON:-python3}"
for preset in mldr-200 msmarco-10k; do
    "$python_bin" -m mintkit bench "$preset" --device "$device" "$@"
done
