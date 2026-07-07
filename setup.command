#!/bin/bash
cd "$(dirname "$0")" || exit 1
echo "============================================"
echo " HH Dashboard setup (internet required)"
echo "============================================"
echo

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 not found."
    echo "Install it from https://www.python.org/downloads/"
    echo "or via Homebrew:  brew install python"
    read -p "Press Enter to close..."
    exit 1
fi

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'; then
    echo "Installed Python is too old, need 3.11 or newer."
    echo "Get a newer one from https://www.python.org/downloads/"
    read -p "Press Enter to close..."
    exit 1
fi

echo "[1/3] Creating environment..."
python3 -m venv .venv || { echo "Failed to create environment."; read -p "Press Enter..."; exit 1; }

echo "[2/3] Downloading the tool and libraries (takes a few minutes)..."
.venv/bin/pip install -q -r requirements.txt || { echo "Install error. Check your internet and try again."; read -p "Press Enter..."; exit 1; }

echo "[3/3] Downloading browser for hh.ru login (~150 MB)..."
.venv/bin/hh-applicant-tool install

echo
echo "============================================"
echo " Setup complete!"
echo "============================================"
