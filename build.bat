@echo off
REM Build PDFStudio.exe on Windows.
REM Requires Python 3.10-3.12 from https://python.org (check "Add to PATH" when installing).
cd /d "%~dp0"

where py >nul 2>nul && (set PY=py -3) || (set PY=python)

%PY% -m venv .venv || goto :error
call .venv\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip
pip install -r requirements.txt "pyinstaller>=6.3" || goto :error
pyinstaller --noconfirm pdfstudio.spec || goto :error

echo.
echo ============================================
echo  Done! Your executable is: dist\PDFStudio.exe
echo ============================================
pause
exit /b 0

:error
echo Build failed - see messages above.
pause
exit /b 1
