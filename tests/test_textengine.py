#!/usr/bin/env python3
"""Tests for the in-house text layout / editing engine and its commit path.

Run: python tests/test_textengine.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz

from pdfstudio.document import PdfDocument
from pdfstudio.fonts import FontResolver, base14_code
from pdfstudio.textengine import ALIGN_CENTER, EditableText

TMP = tempfile.mkdtemp(prefix="pdfstudio-text-")
BODY = ("Revenue grew fourteen percent quarter over quarter, driven by the new "
        "subscription tier and steady retention across every segment we track.")


def build(path):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text(fitz.Point(72, 90), "Quarterly Report", fontsize=24, fontname="hebo")
    page.insert_text(fitz.Point(72, 125), "Finance team", fontsize=12,
                     fontname="tiit", color=(0.3, 0.3, 0.35))
    page.insert_textbox(fitz.Rect(72, 170, 470, 280), BODY, fontsize=12)
    page.insert_text(fitz.Point(72, 330), "Mono 12345", fontsize=11, fontname="cour")
    doc.save(path)
    doc.close()
    return path


def main():
    src = build(os.path.join(TMP, "src.pdf"))
    doc = PdfDocument()
    doc.open(src)

    # ---------------------------------------------------- font resolution
    resolver = doc.fonts
    blocks = doc.raw_blocks(0)
    print(f"blocks: {len(blocks)}")
    assert len(blocks) >= 4, "heading/subtitle/body/mono should be separate blocks"

    span = blocks[0]["lines"][0]["spans"][0]
    font = resolver.resolve_span(0, span)
    assert font.bold, f"heading should resolve bold, got {font.display_name}"
    assert base14_code("Times-Italic", 2) == "tiit"
    assert base14_code("Courier", 8) == "cour"
    assert font.width("Hello", 24) > 0
    print("font resolution: ok")

    # ------------------------------------------------------------- caret
    ed = doc.editable_at(0, fitz.Point(120, 86))
    assert ed and ed.text == "Quarterly Report", repr(ed.text if ed else None)

    # hit-test every boundary and confirm it maps back to the same index
    for i in range(len(ed.text) + 1):
        x = ed.caret_x(i)
        line = ed.layout()[ed.line_of(i)]
        got = ed.hit_test(fitz.Point(x, line.baseline - 2))
        assert got == i, f"caret round-trip failed at {i}: got {got}"
    print("caret hit-test round trip: ok")

    # caret rect must sit inside the line box
    rect = ed.caret_rect(5)
    line = ed.layout()[0]
    assert rect.y0 <= line.baseline <= rect.y1
    assert rect.height > 4
    print("caret geometry: ok")

    # ---------------------------------------------------------- editing
    ed.set_caret(9)                     # "Quarterly| Report"
    ed.insert(" Financial")
    assert ed.text == "Quarterly Financial Report", ed.text
    ed.backspace()
    assert ed.text == "Quarterly Financia Report", ed.text
    ed.insert("l")
    ed.set_caret(0)
    ed.delete_forward()
    assert ed.text == "uarterly Financial Report"
    ed.insert("Q")
    print("insert/backspace/delete: ok")

    # selection
    ed.select_word_at(2)
    assert ed.selected_text() == "Quarterly", repr(ed.selected_text())
    ed.insert("Annual")
    assert ed.text == "Annual Financial Report", ed.text
    ed.select_all()
    assert len(ed.selection_rects()) >= 1
    ed.set_caret(0)
    print("selection: ok")

    # caret movement
    ed.move_horizontal(1, extend=True)
    assert ed.selected_text() == "A"
    ed.set_caret(0)
    ed.move_horizontal(1, word=True)
    assert ed.caret == 7, ed.caret
    ed.move_line_edge(True)
    assert ed.caret == len(ed.text)
    print("caret movement: ok")

    # ------------------------------------------------------- style edits
    ed.select_all()
    ed.apply_style(italic=True, resolver=resolver)
    assert ed.style_at(0).font.italic
    ed.apply_style(size=30.0, resolver=resolver)
    assert abs(ed.style_at(0).size - 30.0) < 0.01
    ed.apply_style(color=(1.0, 0.0, 0.0), resolver=resolver)
    assert ed.style_at(0).color == (1.0, 0.0, 0.0)
    ed.set_caret(0)
    print("style changes: ok")

    doc.commit_text(0, ed, erase_rect=ed.source_rect)
    text = doc.page_text(0)
    assert "Annual Financial Report" in text, text[:200]
    assert "Quarterly Report" not in text, "old heading was not erased"
    print("commit heading: ok")

    # ------------------------------------------------------------ wrapping
    body = doc.editable_at(0, fitz.Point(200, 190))
    assert body and "Revenue grew" in body.text
    original_lines = len(body.layout())
    assert original_lines >= 2, original_lines
    body.set_caret(0)
    body.insert("URGENT: ")
    assert len(body.layout()) >= original_lines
    joined = body.text.replace("\n", " ")
    assert "URGENT: Revenue grew fourteen percent" in joined
    # every original word survives the reflow
    for word in ("subscription", "retention", "segment"):
        assert word in joined, f"lost {word} during reflow"
    print("reflow keeps content: ok")

    # widening the wrap box reduces the line count
    tall = len(body.layout())
    body.set_wrap_width(body.width * 1.8)
    assert len(body.layout()) <= tall
    body.set_wrap_width(body.width / 1.8)
    print("wrap width: ok")

    # ------------------------------------------------------------- moving
    before = body.bounds()
    body.move_by(30, -12)
    after = body.bounds()
    assert abs((after.x0 - before.x0) - 30) < 0.01
    assert abs((after.y0 - before.y0) + 12) < 0.01
    doc.commit_text(0, body, erase_rect=body.source_rect)
    moved = doc.editable_at(0, fitz.Point(after.x0 + 40, after.y0 + 8))
    assert moved is not None, "moved block not found at its new home"
    assert "URGENT" in moved.text, moved.text[:60]
    print("drag-to-move commit: ok")

    # ------------------------------------------------- italic font survives
    sub = doc.editable_at(0, fitz.Point(100, 121))
    assert sub and sub.text.startswith("Finance")
    assert sub.style_at(0).font.italic, "italic subtitle should resolve italic"
    sub.select_all()
    sub.insert("Prepared by Finance")
    doc.commit_text(0, sub, erase_rect=sub.source_rect)

    out = os.path.join(TMP, "out.pdf")
    doc.save(out)
    check = fitz.open(out)
    fonts = {}
    for block in check[0].get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for sp in line["spans"]:
                fonts[sp["text"][:20]] = (sp["font"], round(sp["size"], 1))
    check.close()
    for snippet, (name, size) in fonts.items():
        print(f"   {name:<22} {size:<6} {snippet!r}")
    assert any("Italic" in n for n, _ in fonts.values()), "italic face was lost"
    assert any(abs(s - 30.0) < 0.5 for _, s in fonts.values()), "30pt heading lost"
    print("fonts preserved through save: ok")

    # --------------------------------------------------------- blank text
    blank = EditableText.blank(resolver, (100, 500), 260, size=18,
                               color=(0, 0.2, 0.8), bold=True)
    blank.insert("Brand new text box")
    assert blank.dirty and not blank.is_empty()
    doc.commit_text(0, blank, erase_rect=None)
    assert "Brand new text box" in doc.page_text(0)
    print("new text box: ok")

    # ------------------------------------------------------------ centring
    centred = EditableText("Centred", [blank.style_at(0)] * 7, (100, 600), 300,
                           20.0, ALIGN_CENTER)
    line = centred.layout()[0]
    assert line.x > 100, "centre alignment should indent the line"
    print("alignment: ok")

    # --------------------------------------------------- undo restores all
    assert doc.can_undo
    doc.undo()
    assert "Brand new text box" not in doc.page_text(0)
    print("undo after inline edit: ok")

    print("\nALL TEXT ENGINE TESTS PASSED")


if __name__ == "__main__":
    main()
