#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
venv_dir="${MINTKIT_VENV:-${VIRTUAL_ENV:-../../myenv}}"
if [[ ! -x "$venv_dir/bin/python" ]]; then
    python3 -m venv "$venv_dir"
fi

if [[ "$(uname -s)" == "Linux" ]]; then
    torch_channel="${MINTKIT_TORCH_CHANNEL:-}"
    if [[ -z "$torch_channel" ]]; then
        if command -v nvidia-smi >/dev/null && nvidia-smi -L >/dev/null 2>&1; then
            torch_channel=cu128
        else
            torch_channel=cpu
        fi
    fi
    "$venv_dir/bin/python" -m pip install torch --index-url "https://download.pytorch.org/whl/$torch_channel"
fi

"$venv_dir/bin/python" -m pip install -e '.[embed,mldr,msmarco,images,dev]'
