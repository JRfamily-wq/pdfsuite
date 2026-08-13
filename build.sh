#!/usr/bin/env bash
# Build the PDF Studio executable on Linux or macOS.
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt "pyinstaller>=6.3"
pyinstaller --noconfirm pdfstudio.spec

echo
echo "============================================"
echo " Done! Your executable is: dist/PDFStudio"
echo "============================================"
