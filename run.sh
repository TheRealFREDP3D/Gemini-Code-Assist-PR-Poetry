#!/usr/bin/env bash
# Launch the Gemini Poetry scanner using uv + .venv.
# Usage: ./run.sh [--top 5] [--repos owner/repo,...] [--user username] [...]

set -euo pipefail
cd "$(dirname "$0")"

# Ensure uv is available
if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required but not installed. Install: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# Create the .venv with uv if missing
if [ ! -d ".venv" ]; then
    echo "Creating .venv with uv..."
    uv venv .venv
fi

# Sync dependencies with uv
uv pip install --python .venv -r requirements.txt --quiet

# Activate venv and run
source .venv/bin/activate
python scan_poems.py "$@"
