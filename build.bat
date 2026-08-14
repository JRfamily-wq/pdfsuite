@echo off
REM Build PDFStudio.exe on Windows.
REM Requires Python 3.10-3.12 from https://python.org (tick "Add to PATH").
cd /d "%~dp0"

where py >nul 2>nul && (set PY=py -3) || (set PY=python)

%PY% -m venv .venv || goto :error
call .venv\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip

REM Dependencies are pinned by exact version and SHA-256. If a downloaded file
REM does not match requirements.lock the build stops here rather than baking an
REM unverified package into the executable. See SECURITY.md.
pip install --require-hashes --only-binary :all: -r requirements.lock || goto :hasherror
pip install "pyinstaller>=6.3" || goto :error

python tests\test_document.py || goto :error
python tests\test_textengine.py || goto :error
python tests\test_features.py || goto :error
set QT_QPA_PLATFORM=offscreen
python tests\test_gui.py || goto :error
set QT_QPA_PLATFORM=

pyinstaller --noconfirm pdfstudio.spec || goto :error

echo.
echo ============================================
echo  Done. Your executable is: dist\PDFStudio.exe
echo ============================================
echo SHA-256 of the build:
certutil -hashfile dist\PDFStudio.exe SHA256
pause
exit /b 0

:hasherror
echo.
echo ********************************************************
echo  DEPENDENCY VERIFICATION FAILED
echo  A package did not match its recorded SHA-256 hash.
echo  Do not use this build. See SECURITY.md.
echo ********************************************************
pause
exit /b 2

:error
echo Build failed - see messages above.
pause
exit /b 1
