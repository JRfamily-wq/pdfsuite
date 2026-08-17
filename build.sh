#!/usr/bin/env bash
# Build the PDF Studio executable on Linux or macOS.
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip

# Dependencies are pinned by exact version and SHA-256. If a downloaded file
# does not match requirements.lock this aborts rather than baking an unverified
# package into the executable. See SECURITY.md.
if ! pip install --require-hashes --only-binary :all: -r requirements.lock; then
    echo
    echo "********************************************************"
    echo " DEPENDENCY VERIFICATION FAILED"
    echo " A package did not match its recorded SHA-256 hash."
    echo " Do not use this build. See SECURITY.md."
    echo "********************************************************"
    exit 2
fi
pip install "pyinstaller>=6.3"

python tests/test_document.py
python tests/test_textengine.py
python tests/test_features.py
python tests/test_compress.py
QT_QPA_PLATFORM=offscreen python tests/test_packaging.py
QT_QPA_PLATFORM=offscreen python tests/test_gui.py

QT_QPA_PLATFORM=offscreen python tools/make_icon.py
pyinstaller --noconfirm pdfstudio.spec

echo
echo "============================================"
echo " Done. Your executable is: dist/PDFStudio"
echo "============================================"
echo "SHA-256 of the build:"
if command -v sha256sum >/dev/null; then sha256sum dist/PDFStudio; else shasum -a 256 dist/PDFStudio; fi
