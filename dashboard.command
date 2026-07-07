#!/bin/bash
cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/uvicorn" ]; then
    echo "First run: installing everything, this may take a few minutes..."
    echo
    bash setup.command
fi
if [ ! -x ".venv/bin/uvicorn" ]; then
    echo
    echo "Setup failed - see messages above."
    read -p "Press Enter to close..."
    exit 1
fi

open "http://127.0.0.1:8517"

while true; do
    if [ -f ".update-pending" ]; then
        echo "Finishing update: upgrading engine and libraries..."
        .venv/bin/pip install -q -U -r requirements.txt
        rm -f ".update-pending"
    fi
    .venv/bin/uvicorn dashboard.app:app --host 127.0.0.1 --port 8517
    [ "$?" = "42" ] || break
done
