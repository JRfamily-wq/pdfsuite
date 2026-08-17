#!/usr/bin/env python3
"""Tests for the packaging identity: icon containers, spec wiring, versioning.

Run: python tests/test_packaging.py
"""

import os
import re
import struct
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import make_icon
from pdfstudio import APP_NAME, __version__


def parse_ico(path):
    data = open(path, "rb").read()
    zero, kind, count = struct.unpack("<HHH", data[:6])
    assert (zero, kind) == (0, 1), "not an ICO file"
    entries = []
    offset = 6
    for _ in range(count):
        w, h, _c, _r, planes, bpp, size, data_offset = struct.unpack(
            "<BBBBHHII", data[offset:offset + 16])
        offset += 16
        payload = data[data_offset:data_offset + size]
        if payload[:8] == b"\x89PNG\r\n\x1a\n":
            fmt = "PNG"
        elif struct.unpack("<I", payload[:4])[0] == 40:
            fmt = "BMP"
        else:
            fmt = "UNKNOWN"
        entries.append({"dim": w or 256, "bpp": bpp, "fmt": fmt,
                        "size": size, "payload": payload})
    return entries


def parse_icns(path):
    data = open(path, "rb").read()
    assert data[:4] == b"icns", "not an ICNS file"
    total = struct.unpack(">I", data[4:8])[0]
    assert total == len(data), "ICNS length field does not match the file"
    chunks = {}
    offset = 8
    while offset < len(data):
        kind = data[offset:offset + 4].decode()
        length = struct.unpack(">I", data[offset + 4:offset + 8])[0]
        chunks[kind] = data[offset + 8:offset + length]
        offset += length
    return chunks


def main():
    # ------------------------------------------- generator output is valid
    out = tempfile.mkdtemp(prefix="pdfstudio-icons-")
    paths = make_icon.main(out)

    entries = parse_ico(paths["ico"])
    dims = sorted(e["dim"] for e in entries)
    assert dims == sorted(make_icon.ICO_SIZES), dims
    for entry in entries:
        assert entry["fmt"] in ("PNG", "BMP"), entry
        expected = "BMP" if entry["dim"] in make_icon.ICO_BMP_SIZES else "PNG"
        assert entry["fmt"] == expected, (entry["dim"], entry["fmt"])
        assert entry["bpp"] == 32
    # BMP entries must carry the doubled-height header ICO requires
    bmp = next(e for e in entries if e["fmt"] == "BMP")
    header_size, width, height = struct.unpack("<Iii", bmp["payload"][:12])
    assert header_size == 40 and height == width * 2, (width, height)
    print(f"ICO: {len(entries)} entries, BMP for small sizes, PNG for large: ok")

    chunks = parse_icns(paths["icns"])
    assert set(chunks) == {t.decode() for t in make_icon.ICNS_TYPES.values()}, chunks.keys()
    for kind, payload in chunks.items():
        assert payload[:8] == b"\x89PNG\r\n\x1a\n", f"{kind} is not PNG"
    print(f"ICNS: {sorted(chunks)} all PNG: ok")

    png = open(paths["png"], "rb").read()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    print("PNG preview valid: ok")

    # ------------------------------------------- committed assets are valid
    assets = os.path.join(ROOT, "assets")
    for name in ("app.ico", "app.icns", "app.png"):
        path = os.path.join(assets, name)
        assert os.path.exists(path), f"missing committed asset {name}"
    parse_ico(os.path.join(assets, "app.ico"))
    parse_icns(os.path.join(assets, "app.icns"))
    print("committed assets parse: ok")

    # ------------------------------------------------------- spec wiring
    spec = open(os.path.join(ROOT, "pdfstudio.spec"), encoding="utf-8").read()
    for needle in ("app.ico", "app.icns", "VSVersionInfo", "BUNDLE",
                   "bundle_identifier", "version=version_resource",
                   "icon=ICON"):
        assert needle in spec, f"spec is missing {needle!r}"
    print("spec references icons, version resource and the macOS bundle: ok")

    # the spec parses the version the same way it will at build time
    init = open(os.path.join(ROOT, "pdfstudio", "__init__.py"),
                encoding="utf-8").read()
    parsed = re.search(r'__version__ = "([^"]+)"', init).group(1)
    assert parsed == __version__, (parsed, __version__)
    parsed_name = re.search(r'APP_NAME = "([^"]+)"', init).group(1)
    assert parsed_name == APP_NAME
    tuple(int(part) for part in parsed.split("."))   # must be numeric x.y.z
    print(f"version {parsed} parses for the Windows resource: ok")

    # ------------------------------------ release workflow carries the hooks
    release = open(os.path.join(ROOT, ".github", "workflows", "release.yml"),
                   encoding="utf-8").read()
    for needle in ("WIN_SIGN_CERT_B64", "signtool", "MAC_SIGN_CERT_B64",
                   "codesign", "PDFStudio.app", "make_icon.py"):
        assert needle in release, f"release workflow is missing {needle!r}"
    print("release workflow has signing hooks and ships the .app: ok")

    print("\nALL PACKAGING TESTS PASSED")


if __name__ == "__main__":
    main()
