# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for PDF Studio (PyInstaller >= 6).
# Build with:  pyinstaller --noconfirm pdfstudio.spec
# Produces a single-file executable in dist/ (PDFStudio.exe on Windows).

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtNetwork',
              'PySide6.QtOpenGL', 'PySide6.QtQuick3D', 'PySide6.QtSql',
              'PySide6.QtTest', 'PySide6.QtDesigner'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PDFStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
