#!/bin/bash
cd "$(dirname "$0")" || exit 1
echo "============================================"
echo " HH Dashboard setup (internet required)"
echo "============================================"
echo

# macOS often ships an old system python3 (3.9). Look for a 3.11+ among the
# usual command names before giving up.
find_python() {
    for c in python3.13 python3.12 python3.11 python3; do
        if command -v "$c" >/dev/null 2>&1 && \
           "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
            echo "$c"
            return 0
        fi
    done
    return 1
}

PY="$(find_python)"

if [ -z "$PY" ] && command -v brew >/dev/null 2>&1; then
    echo "No Python 3.11+ found. Installing it via Homebrew (a few minutes)..."
    brew install python@3.12
    PY="$(find_python)"
fi

if [ -z "$PY" ]; then
    echo "No Python 3.11 or newer found."
    echo
    echo "Please install Python from https://www.python.org/downloads/"
    echo "  1. open the link, download the macOS installer (Python 3.12)"
    echo "  2. run it (just click Continue / Install)"
    echo "  3. start dashboard.command again"
    read -p "Press Enter to close..."
    exit 1
fi

echo "Using $PY ($($PY --version 2>&1))"
echo "[1/3] Creating environment..."
"$PY" -m venv .venv || { echo "Failed to create environment."; read -p "Press Enter..."; exit 1; }

echo "[2/3] Downloading the tool and libraries (takes a few minutes)..."
.venv/bin/pip install -q -r requirements.txt || { echo "Install error. Check your internet and try again."; read -p "Press Enter..."; exit 1; }

echo "[3/3] Downloading browser for hh.ru login (~150 MB)..."
.venv/bin/hh-applicant-tool install

echo
echo "============================================"
echo " Setup complete!"
echo "============================================"
