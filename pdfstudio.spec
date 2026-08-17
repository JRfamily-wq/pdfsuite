# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for PDF Studio (PyInstaller >= 6).
# Build with:  pyinstaller --noconfirm pdfstudio.spec
#
# Produces a single-file executable in dist/ (PDFStudio.exe on Windows, and
# additionally a double-clickable PDFStudio.app bundle on macOS). The file
# icon comes from assets/ (regenerate with `python tools/make_icon.py`), and
# on Windows a version-information resource is embedded so the executable
# carries a publisher, product name and version in its Properties sheet.

import os
import re
import sys

# The spec's directory is not on sys.path when PyInstaller executes it, so the
# version and app name are parsed from the package rather than imported.
# SPECPATH is provided by PyInstaller: the directory containing this file.
_init = open(os.path.join(SPECPATH, "pdfstudio", "__init__.py"),
             encoding="utf-8").read()
__version__ = re.search(r'__version__ = "([^"]+)"', _init).group(1)
APP_NAME = re.search(r'APP_NAME = "([^"]+)"', _init).group(1)

VERSION_TUPLE = tuple(int(part) for part in __version__.split(".")) + (0,)
_ASSETS = os.path.join(SPECPATH, "assets")
ICON = (os.path.join(_ASSETS, "app.ico") if sys.platform == "win32" else
        os.path.join(_ASSETS, "app.icns") if sys.platform == "darwin" else None)

version_resource = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo,
                                                     StringFileInfo,
                                                     StringStruct, StringTable,
                                                     VarFileInfo, VarStruct,
                                                     VSVersionInfo)
    version_resource = VSVersionInfo(
        ffi=FixedFileInfo(filevers=VERSION_TUPLE, prodvers=VERSION_TUPLE),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "PDF Studio open-source project"),
                StringStruct("FileDescription", "PDF Studio — PDF viewer and editor"),
                StringStruct("FileVersion", __version__),
                StringStruct("ProductName", APP_NAME),
                StringStruct("ProductVersion", __version__),
                StringStruct("OriginalFilename", "PDFStudio.exe"),
                StringStruct("LegalCopyright",
                             "AGPL-3.0 — source available in the project repository"),
            ])]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ])

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
    icon=ICON,
    version=version_resource,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name='PDFStudio.app',
        icon=os.path.join(_ASSETS, 'app.icns'),
        bundle_identifier='org.pdfstudio.pdfstudio',
        version=__version__,
        info_plist={
            'CFBundleShortVersionString': __version__,
            'NSHighResolutionCapable': True,
            'NSPrincipalClass': 'NSApplication',
        },
    )
