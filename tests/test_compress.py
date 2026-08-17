#!/usr/bin/env python3
"""Tests for file-size compression.

Run: python tests/test_compress.py
"""

import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz

from pdfstudio.doc_features import COMPRESS_PRESETS
from pdfstudio.document import PdfDocument

TMP = tempfile.mkdtemp(prefix="pdfstudio-compress-")


def make_photo(path, width=1400, height=1000):
    """A gradient with noise — compresses roughly like a real photograph."""
    random.seed(11)
    buf = bytearray()
    for y in range(height):
        base_g = (y * 255) // height
        for x in range(width):
            r = (x * 255) // width
            n = random.randint(-16, 16)
            buf += bytes((max(0, min(255, r + n)),
                          max(0, min(255, base_g + n)),
                          max(0, min(255, (r + base_g) // 2 + n))))
    fitz.Pixmap(fitz.csRGB, width, height, bytes(buf), 0).save(path)
    return path


def build_heavy(path, photo, pages=3):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_image(fitz.Rect(40, 40, 555, 420), filename=photo)
        page.insert_text(fitz.Point(60, 470), f"Section {i + 1}",
                         fontsize=18, fontname="hebo")
        page.insert_textbox(fitz.Rect(60, 495, 540, 780),
                            "Readable body text that must survive compression "
                            "untouched. " * 12, fontsize=11)
    doc.save(path)
    doc.close()
    return path


def build_text_only(path, pages=4):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text(fitz.Point(72, 90), f"Chapter {i + 1}",
                         fontsize=20, fontname="hebo")
        page.insert_textbox(fitz.Rect(72, 120, 520, 760),
                            "Plain prose with no images at all. " * 60, fontsize=11)
    doc.save(path)
    doc.close()
    return path


def kb(n):
    return f"{n / 1024:.0f} KB"


def main():
    photo = make_photo(os.path.join(TMP, "photo.png"))
    heavy = build_heavy(os.path.join(TMP, "heavy.pdf"), photo)
    original = os.path.getsize(heavy)
    print(f"test document: {kb(original)} with 3 full-width photos")

    # ------------------------------------------------------- image analysis
    doc = PdfDocument()
    doc.open(heavy)
    report = doc.image_report()
    assert report["count"] >= 1, report
    assert report["share"] > 0.5, f"images should dominate the file: {report['share']:.0%}"
    assert report["max_dpi"] > 150, f"expected high-dpi images, got {report['max_dpi']:.0f}"
    print(f"image report: {report['count']} image(s), "
          f"{report['share']:.0%} of the file, up to {report['max_dpi']:.0f} dpi: ok")

    text_before = doc.page_text(0)
    assert "Section 1" in text_before

    # ------------------------------------------------------------- presets
    keys = [row[0] for row in COMPRESS_PRESETS]
    assert keys == ["lossless", "print", "balanced", "screen", "smallest"], keys
    for key, label, desc, opts in COMPRESS_PRESETS:
        assert label and desc, key
        assert set(opts) >= {"image_dpi", "quality", "grayscale", "subset_fonts"}, opts
    print("presets well formed: ok")

    # ------------------------------------------------- lossless never resamples
    doc_l = PdfDocument()
    doc_l.open(heavy)
    stats = doc_l.compress(**doc_l.preset("lossless"))
    assert stats["after"] <= stats["before"], stats
    assert not stats["did"]["images"], "lossless preset must not touch images"
    after_report = doc_l.image_report()
    assert abs(after_report["max_dpi"] - report["max_dpi"]) < 1.0, \
        "lossless changed image resolution"
    print(f"lossless: {kb(stats['before'])} -> {kb(stats['after'])} "
          f"({stats['ratio']:.0%} smaller), images untouched: ok")

    # --------------------------------------------- each lossy preset shrinks
    previous = None
    for key in ("print", "balanced", "screen", "smallest"):
        d = PdfDocument()
        d.open(heavy)
        result = d.compress(**d.preset(key))
        assert result["did"]["images"], f"{key} did not resample images"
        assert result["after"] < result["before"], (key, result)
        assert result["ratio"] > 0.3, f"{key} only saved {result['ratio']:.0%}"
        # text must be completely intact — compression is for images
        assert "Section 1" in d.page_text(0), f"{key} damaged the text"
        assert d.page_count == 3, f"{key} changed the page count"
        print(f"{key:>9}: {kb(result['before'])} -> {kb(result['after'])}"
              f"  ({result['ratio']:.0%} smaller)")
        if previous is not None:
            assert result["after"] <= previous * 1.05, \
                f"{key} should not be larger than the gentler preset"
        previous = result["after"]
        d.doc.close()
    print("every lossy preset shrinks the file and keeps the text: ok")

    # ------------------------------------------------------- undo restores
    d = PdfDocument()
    d.open(heavy)
    before = d.measure_size()
    d.compress(**d.preset("smallest"))
    shrunk = d.measure_size()
    assert shrunk < before
    assert d.can_undo
    d.undo()
    restored = d.measure_size()
    assert restored > shrunk * 2, f"undo did not restore the images: {restored} vs {shrunk}"
    assert abs(d.image_report()["max_dpi"] - report["max_dpi"]) < 1.0
    print(f"undo restores the originals: {kb(shrunk)} -> {kb(restored)}: ok")

    # -------------------------------------------- saved file really is smaller
    out = os.path.join(TMP, "compressed.pdf")
    d2 = PdfDocument()
    d2.open(heavy)
    d2.compress(**d2.preset("balanced"))
    d2.save(out)
    on_disk = os.path.getsize(out)
    assert on_disk < original * 0.5, f"{kb(on_disk)} vs original {kb(original)}"
    # and it must still open and render
    check = PdfDocument()
    assert check.open(out) == "ok"
    assert check.page_count == 3
    assert "Section 1" in check.page_text(0)
    assert check.render(0, 1.0).width > 100
    print(f"saved file: {kb(original)} -> {kb(on_disk)} on disk, reopens and renders: ok")

    # --------------------------------------- greyscale preset really greys out
    d3 = PdfDocument()
    d3.open(heavy)
    d3.compress(**d3.preset("smallest"))
    pix = d3.render(0, 0.4)
    mid = pix.pixel(pix.width // 2, pix.height // 5)
    assert max(mid[:3]) - min(mid[:3]) < 40, f"expected near-grey pixel, got {mid[:3]}"
    print(f"greyscale preset desaturates the image (sample rgb {mid[:3]}): ok")

    # ------------------------------------- text-only file: honest small gain
    text_pdf = build_text_only(os.path.join(TMP, "text.pdf"))
    d4 = PdfDocument()
    d4.open(text_pdf)
    rep = d4.image_report()
    assert rep["count"] == 0, rep
    assert rep["share"] == 0.0
    undo_depth = len(d4._undo)
    result = d4.compress(**d4.preset("balanced"))
    # A compressor must never inflate a file. This one is already minimal, so
    # the operation should report no gain and leave the document untouched.
    assert result["after"] <= result["before"], result
    assert result["no_gain"], result
    assert result["did"]["image_count"] == 0, result
    assert len(d4._undo) == undo_depth, "a no-gain compress left an undo step behind"
    assert "Chapter 1" in d4.page_text(0)
    print(f"text-only file: no images, {kb(result['before'])} unchanged, "
          f"reported as no gain, no undo step left: ok")

    # ------------------------------------------- flatten option reduces too
    d5 = PdfDocument()
    d5.open(heavy)
    d5.add_highlight(0, fitz.Rect(60, 470, 300, 490))
    d5.add_note(0, fitz.Point(500, 480), "note")
    assert len(list(d5.page(0).annots())) == 2
    d5.compress(image_dpi=150, quality=75, flatten_annotations=True)
    assert not list(d5.page(0).annots()), "flatten_annotations left annotations behind"
    print("flatten option bakes annotations in: ok")

    # -------------------------------------------- encryption still works after
    locked = os.path.join(TMP, "locked.pdf")
    d6 = PdfDocument()
    d6.open(heavy)
    d6.compress(**d6.preset("screen"))
    d6.save(locked, user_pw="pw1234")
    probe = PdfDocument()
    assert probe.open(locked) == "needs_password"
    assert probe.open(locked, "pw1234") == "ok"
    print("compressed + password protected still opens: ok")

    print("\nALL COMPRESSION TESTS PASSED")


if __name__ == "__main__":
    main()
