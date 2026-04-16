#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

VENV_PYTHON=".venv/bin/python"

if [ ! -x "$VENV_PYTHON" ]; then
    if command -v python3 >/dev/null 2>&1; then
        python3 -m venv .venv
    elif command -v python >/dev/null 2>&1; then
        python -m venv .venv
    else
        echo "Python was not found. Install Python 3 and make it available in PATH." >&2
        exit 1
    fi
fi

"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r requirements.txt
exec "$VENV_PYTHON" main.py --config config.json "$@"
