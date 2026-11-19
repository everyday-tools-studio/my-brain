#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if command -v uv >/dev/null; then
    [ -x .venv/bin/python ] || uv venv .venv
    uv pip install --python .venv/bin/python -r requirements.txt
else
    [ -x .venv/bin/python ] || python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt
fi
dir="${XDG_DATA_HOME:-$HOME/.local/share}/mon-cerveau/modeles"
if [ ! -d "$dir/vosk-model-small-fr-0.22" ]; then
    mkdir -p "$dir"
    archive=$(mktemp)
    trap 'unlink "$archive"' EXIT
    curl -fsSL https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip -o "$archive"
    echo "cabf6180e177eb9b3a9a9d43a437bd5e549f3a7d09525e5d69a3fed787be12ad  $archive" | sha256sum -c -
    unzip -qn "$archive" -d "$dir"
fi
