#!/usr/bin/env python3
"""Headless tests for the document engine. Run: python tests/test_document.py"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz

from pdfstudio.document import PdfDocument, PdfError, WHITE

TMP = tempfile.mkdtemp(prefix="pdfstudio-test-")
PARAGRAPH = "The quick brown fox jumps over the lazy dog."


def make_sample(path, pages=3):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text(fitz.Point(72, 100), f"PAGE-{i + 1}", fontsize=20)
        if i == 0:
            page.insert_textbox(fitz.Rect(72, 200, 500, 260), PARAGRAPH, fontsize=12)
    doc.save(path)
    doc.close()
    return path


def page_marker(doc, i):
    text = doc.page_text(i)
    for token in text.split():
        if token.startswith("PAGE-"):
            return token
    return ""


def main():
    sample = make_sample(os.path.join(TMP, "sample.pdf"))
    events = []
    doc = PdfDocument()
    doc.on_changed = lambda structural: events.append(structural)

    # -- open
    assert doc.open(sample) == "ok"
    assert doc.page_count == 3
    print("open: ok")

    # -- rotate + undo/redo
    doc.rotate_pages([0], 90)
    assert doc.page(0).rotation == 90
    assert doc.can_undo
    doc.undo()
    assert doc.page(0).rotation == 0
    doc.redo()
    assert doc.page(0).rotation == 90
    doc.undo()
    print("rotate/undo/redo: ok")

    # -- rotation coordinate round-trip (annotation coords vs rendered pixels)
    doc.rotate_pages([0], 90)
    hits = doc.search_page(0, "PAGE-1")
    assert hits, "search on rotated page found nothing"
    center = fitz.Point((hits[0].x0 + hits[0].x1) / 2, (hits[0].y0 + hits[0].y1) / 2)
    fwd = doc.display_matrix(0, 1.5)
    inv = doc.inverse_matrix(0, 1.5)
    display_pt = center * fwd
    pix = doc.render(0, 1.5)
    assert 0 <= display_pt.x <= pix.width and 0 <= display_pt.y <= pix.height, \
        f"mapped point {display_pt} outside pixmap {pix.width}x{pix.height}"
    back = display_pt * inv
    assert abs(back.x - center.x) < 0.01 and abs(back.y - center.y) < 0.01
    doc.undo()
    print("rotation coordinate round-trip: ok")

    # -- move page: [1,2,3] -> move page 0 to index 2 -> [2,3,1]
    doc.move_page(0, 2)
    order = [page_marker(doc, i) for i in range(3)]
    assert order == ["PAGE-2", "PAGE-3", "PAGE-1"], f"move down produced {order}"
    doc.move_page(2, 0)
    order = [page_marker(doc, i) for i in range(3)]
    assert order == ["PAGE-1", "PAGE-2", "PAGE-3"], f"move up produced {order}"
    print("move_page semantics: ok")

    # -- delete
    doc.delete_pages([1])
    assert doc.page_count == 2
    assert [page_marker(doc, i) for i in range(2)] == ["PAGE-1", "PAGE-3"]
    try:
        doc.delete_pages([0, 1])
        assert False, "deleting all pages should raise"
    except PdfError:
        pass
    doc.undo()
    assert doc.page_count == 3
    print("delete_pages: ok")

    # -- insert blank + insert pdf + extract
    doc.insert_blank_page(1, like=0)
    assert doc.page_count == 4
    assert page_marker(doc, 1) == ""
    other = make_sample(os.path.join(TMP, "other.pdf"), pages=2)
    added = doc.insert_pdf_file(other, at=0)
    assert added == 2 and doc.page_count == 6
    out = os.path.join(TMP, "extract.pdf")
    doc.extract_pages([0, 1], out)
    check = fitz.open(out)
    assert check.page_count == 2
    check.close()
    doc.undo()
    doc.undo()
    assert doc.page_count == 3
    print("insert/merge/extract: ok")

    # -- annotations
    page_rect = fitz.Rect(100, 300, 220, 340)
    doc.add_highlight(0, fitz.Rect(70, 90, 180, 110))
    doc.add_shape(0, "rect", page_rect, color=(1, 0, 0), width=2)
    doc.add_shape(0, "ellipse", fitz.Rect(240, 300, 340, 360), color=(0, 0, 1))
    doc.add_line(0, fitz.Point(100, 400), fitz.Point(300, 430), arrow=True)
    doc.add_ink(0, [(100, 500), (140, 520), (180, 500), (220, 530)], color=(0, 0.5, 0))
    doc.add_textbox(0, fitz.Rect(100, 560, 320, 600), "Added text box", fontsize=14)
    doc.add_note(0, fitz.Point(400, 300), "A sticky note")
    annots = list(doc.page(0).annots())
    assert len(annots) == 7, f"expected 7 annots, got {len(annots)}"
    hit = doc.annot_at(0, fitz.Point(160, 320))
    assert hit is not None
    assert doc.delete_annot(0, hit[0])
    assert len(list(doc.page(0).annots())) == 6
    print("annotations: ok")

    # -- whiteout removes text underneath
    hits = doc.search_page(1, "PAGE-2")
    assert hits
    area = fitz.Rect(hits[0]) + (-2, -2, 2, 2)
    doc.redact_area(1, area, fill=WHITE)
    assert not doc.search_page(1, "PAGE-2"), "whiteout left text behind"
    doc.undo()
    assert doc.search_page(1, "PAGE-2")
    print("whiteout/redact: ok")

    # -- edit text block
    block = doc.block_at(0, fitz.Point(100, 210))
    assert block is not None, "paragraph block not found"
    assert "quick brown fox" in PdfDocument.block_text(block)
    doc.replace_block_text(0, block, "Edited paragraph text, rewritten by the test.")
    text = doc.page_text(0)
    assert "quick brown fox" not in text
    assert "Edited paragraph" in text
    print("edit text: ok")

    # -- watermark + page numbers + metadata
    doc.add_watermark("DRAFT", fontsize=40, opacity=0.2)
    doc.add_page_numbers(fmt="{n} / {total}")
    assert doc.search_page(0, "1 / 3")
    doc.set_metadata({"title": "Test Title", "author": "Tester"})
    assert doc.get_metadata()["title"] == "Test Title"
    print("watermark/page numbers/metadata: ok")

    # -- save + reopen
    saved = os.path.join(TMP, "saved.pdf")
    doc.save(saved)
    assert not doc.dirty
    reopened = fitz.open(saved)
    assert reopened.page_count == 3
    assert "Edited paragraph" in reopened[0].get_text()
    reopened.close()
    print("save/reopen: ok")

    # -- encrypted save
    locked = os.path.join(TMP, "locked.pdf")
    doc.save(locked, user_pw="secret123")
    doc2 = PdfDocument()
    assert doc2.open(locked) == "needs_password"
    assert doc2.open(locked, "wrong") == "bad_password"
    assert doc2.open(locked, "secret123") == "ok"
    assert doc2.page_count == 3
    print("encryption: ok")

    # -- export page image
    png = os.path.join(TMP, "page.png")
    doc.export_page_image(0, png)
    assert os.path.getsize(png) > 1000
    print("export image: ok")

    assert events, "change notifications never fired"
    print("\nALL DOCUMENT TESTS PASSED")


if __name__ == "__main__":
    main()
