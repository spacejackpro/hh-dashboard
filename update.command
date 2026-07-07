#!/bin/bash
# Re-exec from a temp copy so we can safely overwrite update.command itself.
if [ "$1" != "--inplace" ]; then
    PROJ="$(cd "$(dirname "$0")" && pwd)"
    TMP="$(mktemp -t hhdashupd).command"
    cp "$0" "$TMP"
    exec bash "$TMP" --inplace "$PROJ"
fi

cd "$2" || exit 1
echo "============================================"
echo " HH Dashboard update"
echo "============================================"
echo
echo "[1/3] Downloading the latest version from GitHub..."
ZIP="$(mktemp -t hhdashzip).zip"
if ! curl -fsSL "https://codeload.github.com/spacejackpro/hh-dashboard/zip/refs/heads/main" -o "$ZIP"; then
    echo "Download failed. Check your internet and try again."
    read -p "Press Enter to close..."
    exit 1
fi
SRC="$(mktemp -d -t hhdashsrc)"
unzip -q -o "$ZIP" -d "$SRC"
cp -R "$SRC"/hh-dashboard-main/. .
chmod +x *.command 2>/dev/null
echo "       Code updated."

echo "[2/3] Upgrading the hh-applicant-tool engine and libraries..."
.venv/bin/pip install -q -U -r requirements.txt

echo "[3/3] Checking browser for hh.ru login..."
.venv/bin/hh-applicant-tool install

echo
echo "============================================"
echo " Done! Start dashboard.command"
echo "============================================"
read -p "Press Enter to close..."
