#!/usr/bin/env python3
"""Generate the application icon files from the in-code painter.

Writes assets/app.ico (Windows), assets/app.icns (macOS) and assets/app.png
(Linux / previews), all rendered from pdfstudio.icons.app_icon_pixmap so the
executable's file icon can never drift from the window icon.

The ICO and ICNS containers are written by hand rather than pulling in an
imaging library: both formats are simple envelopes around PNG (and, for small
ICO sizes, raw BGRA bitmaps), and the dependency tree is pinned by hash — a
whole image library is a lot of supply chain for two file headers.

Run:  python tools/make_icon.py [output-dir]     (defaults to assets/)
"""

from __future__ import annotations

import os
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
# Small ICO entries are stored as classic BGRA bitmaps — every consumer ever
# written understands those — while the big ones use PNG to keep the file small.
ICO_BMP_SIZES = {16, 24, 32, 48}

# icns chunk types for PNG payloads at each size.
ICNS_TYPES = {16: b"icp4", 32: b"icp5", 64: b"icp6", 128: b"ic07",
              256: b"ic08", 512: b"ic09"}


def _renders(sizes):
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtWidgets import QApplication

    from pdfstudio.icons import app_icon_pixmap

    app = QApplication.instance() or QApplication([])
    out = {}
    for size in sizes:
        image = app_icon_pixmap(size).toImage()
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        out[size] = {"image": image, "png": bytes(buffer.data())}
        buffer.close()
    return out


def _bgra_rows_bottom_up(image) -> bytes:
    """32-bit BGRA pixel data the way BMP wants it: bottom row first."""
    from PySide6.QtGui import QImage
    converted = image.convertToFormat(QImage.Format_ARGB32)  # 0xAARRGGBB
    width, height = converted.width(), converted.height()
    rows = []
    for y in range(height - 1, -1, -1):
        row = bytearray()
        for x in range(width):
            argb = converted.pixel(x, y)
            row += struct.pack("<I", argb)   # little-endian => B,G,R,A on disk
        rows.append(bytes(row))
    return b"".join(rows)


def _ico_bmp_entry(image) -> bytes:
    """A classic ICO DIB: BITMAPINFOHEADER with doubled height, BGRA pixels,
    then an all-zero AND mask (alpha does the masking)."""
    width, height = image.width(), image.height()
    pixels = _bgra_rows_bottom_up(image)
    mask_stride = ((width + 31) // 32) * 4
    mask = b"\x00" * (mask_stride * height)
    header = struct.pack("<IiiHHIIiiII", 40, width, height * 2, 1, 32, 0,
                         len(pixels) + len(mask), 0, 0, 0, 0)
    return header + pixels + mask


def write_ico(path: str, renders: dict):
    entries = []
    for size in ICO_SIZES:
        if size in ICO_BMP_SIZES:
            entries.append((size, _ico_bmp_entry(renders[size]["image"])))
        else:
            entries.append((size, renders[size]["png"]))
    with open(path, "wb") as fh:
        fh.write(struct.pack("<HHH", 0, 1, len(entries)))
        offset = 6 + 16 * len(entries)
        for size, data in entries:
            dim = 0 if size >= 256 else size
            fh.write(struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                                 len(data), offset))
            offset += len(data)
        for _size, data in entries:
            fh.write(data)


def write_icns(path: str, renders: dict):
    chunks = b""
    for size, kind in ICNS_TYPES.items():
        png = renders[size]["png"]
        chunks += kind + struct.pack(">I", len(png) + 8) + png
    with open(path, "wb") as fh:
        fh.write(b"icns" + struct.pack(">I", len(chunks) + 8) + chunks)


def main(out_dir: str | None = None) -> dict:
    out_dir = out_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
    os.makedirs(out_dir, exist_ok=True)
    sizes = sorted(set(ICO_SIZES) | set(ICNS_TYPES))
    renders = _renders(sizes)

    ico = os.path.join(out_dir, "app.ico")
    icns = os.path.join(out_dir, "app.icns")
    png = os.path.join(out_dir, "app.png")
    write_ico(ico, renders)
    write_icns(icns, renders)
    with open(png, "wb") as fh:
        fh.write(renders[256]["png"])

    for path in (ico, icns, png):
        print(f"wrote {path}  ({os.path.getsize(path)} bytes)")
    return {"ico": ico, "icns": icns, "png": png}


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
