#!/usr/bin/env python3
"""Tests for forms, bookmarks, links, attachments, stamps and page surgery.

Run: python tests/test_features.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz

from pdfstudio.doc_features import (FIELD_CHECKBOX, FIELD_CHOICE, FIELD_TEXT,
                                    STAMP_PRESETS)
from pdfstudio.document import PdfDocument

TMP = tempfile.mkdtemp(prefix="pdfstudio-features-")


def build_form(path):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text(fitz.Point(72, 70), "Application Form", fontsize=20, fontname="hebo")
    page.insert_text(fitz.Point(72, 110), "Full name:", fontsize=11)
    page.insert_text(fitz.Point(72, 150), "Subscribe:", fontsize=11)
    page.insert_text(fitz.Point(72, 190), "Plan:", fontsize=11)

    text = fitz.Widget()
    text.field_name = "fullname"
    text.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    text.rect = fitz.Rect(160, 95, 420, 118)
    text.field_value = ""
    text.text_fontsize = 11
    page.add_widget(text)

    check = fitz.Widget()
    check.field_name = "subscribe"
    check.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    check.rect = fitz.Rect(160, 138, 178, 156)
    check.field_value = False
    page.add_widget(check)

    combo = fitz.Widget()
    combo.field_name = "plan"
    combo.field_type = fitz.PDF_WIDGET_TYPE_COMBOBOX
    combo.rect = fitz.Rect(160, 178, 320, 200)
    combo.choice_values = ["Basic", "Pro", "Enterprise"]
    combo.field_value = "Basic"
    page.add_widget(combo)

    doc.save(path)
    doc.close()
    return path


def build_doc(path, pages=6):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        size = 22 if i % 2 == 0 else 11
        page.insert_text(fitz.Point(72, 90), f"Heading {i + 1}", fontsize=size,
                         fontname="hebo" if i % 2 == 0 else "helv")
        page.insert_textbox(fitz.Rect(72, 130, 500, 300),
                            "Body copy that stays at the ordinary reading size so "
                            "the heading detector has something to contrast against.",
                            fontsize=11)
    doc.save(path)
    doc.close()
    return path


def main():
    # ------------------------------------------------------------- forms
    doc = PdfDocument()
    doc.open(build_form(os.path.join(TMP, "form.pdf")))
    assert doc.has_form, "form not detected"

    fields = doc.form_fields()
    assert len(fields) == 3, [f.name for f in fields]
    by_name = {f.name: f for f in fields}
    assert by_name["fullname"].kind == FIELD_TEXT
    assert by_name["subscribe"].kind == FIELD_CHECKBOX
    assert by_name["plan"].kind == FIELD_CHOICE
    assert by_name["plan"].choices == ["Basic", "Pro", "Enterprise"]
    print("form detection: ok")

    hit = doc.field_at(0, fitz.Point(200, 106))
    assert hit is not None and hit.name == "fullname", hit
    print("field hit-test: ok")

    assert doc.set_field_value(0, "fullname", "Ada Lovelace")
    assert doc.set_field_value(0, "subscribe", True)
    assert doc.set_field_value(0, "plan", "Pro")
    values = {f.name: f.value for f in doc.form_fields()}
    assert values["fullname"] == "Ada Lovelace", values
    assert str(values["subscribe"]).lower() not in ("off", "false"), values
    assert values["plan"] == "Pro", values
    print("form filling: ok")

    # values must survive a save/reopen cycle
    filled = os.path.join(TMP, "filled.pdf")
    doc.save(filled)
    reopened = PdfDocument()
    reopened.open(filled)
    assert {f.name: f.value for f in reopened.form_fields()}["fullname"] == "Ada Lovelace"
    print("form values persist through save: ok")

    doc.undo()
    doc.undo()
    doc.undo()
    assert doc.form_fields()[0].value in ("", None), "undo did not roll the form back"
    doc.redo(); doc.redo(); doc.redo()
    print("form undo/redo: ok")

    doc.reset_form()
    after_reset = {f.name: f.value for f in doc.form_fields()}
    assert after_reset["fullname"] in ("", None), after_reset
    assert str(after_reset["subscribe"]).lower() in ("off", "false"), after_reset
    # the cleared text must not still be painted on the page
    assert "Ada Lovelace" not in doc.page_text(0), "reset left the old text drawn"
    print("form reset clears values and appearance: ok")
    doc.undo()
    assert {f.name: f.value for f in doc.form_fields()}["fullname"] == "Ada Lovelace"

    # flatten: values become page content and the fields disappear
    doc.flatten_form()
    assert not doc.form_fields(), "fields survived flattening"
    text = doc.page_text(0)
    assert "Ada Lovelace" in text, text[:200]
    print("form flatten: ok")
    doc.undo()
    assert len(doc.form_fields()) == 3, "undo did not restore the fields"
    print("form flatten undo: ok")

    # --------------------------------------------------------- bookmarks
    doc2 = PdfDocument()
    doc2.open(build_doc(os.path.join(TMP, "doc.pdf")))

    assert doc2.set_toc([[1, "Alpha", 1], [2, "Alpha.1", 2], [1, "Beta", 3]])
    assert len(doc2.get_toc()) == 3
    assert doc2.add_bookmark("Inserted", page=1, level=2)
    titles = [row[1] for row in doc2.get_toc()]
    assert "Inserted" in titles, titles
    position = titles.index("Inserted")
    assert doc2.rename_bookmark(position, "Renamed")
    assert [r[1] for r in doc2.get_toc()][position] == "Renamed"
    assert doc2.shift_bookmark_level(position, -1)
    assert doc2.remove_bookmark(position)
    assert "Renamed" not in [r[1] for r in doc2.get_toc()]
    print("bookmark add/rename/level/remove: ok")

    # a level may never jump more than one deeper
    doc2.set_toc([[1, "A", 1], [5, "B", 2]])
    assert doc2.get_toc()[1][0] == 2, doc2.get_toc()
    print("bookmark level normalisation: ok")

    found = doc2.bookmarks_from_headings()
    assert found >= 3, f"heading detection found only {found}"
    generated = [r[1] for r in doc2.get_toc()]
    assert any("Heading 1" in t for t in generated), generated
    assert not any("Body copy" in t for t in generated), "body text became a bookmark"
    print(f"auto bookmarks from headings ({found} found): ok")

    # ------------------------------------------------------------- links
    doc2.add_uri_link(0, fitz.Rect(72, 400, 300, 420), "https://example.com")
    doc2.add_goto_link(0, fitz.Rect(72, 430, 300, 450), 3)
    links = doc2.page_links(0)
    assert len(links) == 2, links
    assert any(l.get("uri") == "https://example.com" for l in links)
    hit = doc2.link_at(0, fitz.Point(150, 410))
    assert hit is not None and hit.get("uri") == "https://example.com"
    assert doc2.remove_link(0, hit)
    assert len(doc2.page_links(0)) == 1
    print("links add/hit-test/remove: ok")

    # ------------------------------------------------------- attachments
    payload = os.path.join(TMP, "note.txt")
    open(payload, "w").write("attached content")
    assert doc2.attach_file(payload, desc="A note")
    listed = doc2.attachments()
    assert len(listed) == 1 and listed[0]["name"] == "note.txt", listed
    out = os.path.join(TMP, "extracted.txt")
    assert doc2.extract_attachment("note.txt", out)
    assert open(out).read() == "attached content"
    assert doc2.delete_attachment("note.txt")
    assert not doc2.attachments()
    print("attachments add/extract/delete: ok")

    # ------------------------------------------------------ page surgery
    original = doc2.page(0).rect
    doc2.crop_pages([0], fitz.Rect(50, 50, 400, 600))
    cropped = doc2.page(0).rect
    assert cropped.width < original.width, (original, cropped)
    doc2.reset_crop([0])
    assert abs(doc2.page(0).rect.width - original.width) < 0.1
    print("crop and reset: ok")

    doc2.scale_pages([1], 0.5)
    assert doc2.page(1).rect.width < original.width * 0.6
    doc2.undo()
    print("page scaling: ok")

    # split
    out_dir = os.path.join(TMP, "split")
    parts = doc2.split_to_files(out_dir, mode="every", size=2)
    assert len(parts) == 3, parts
    check = fitz.open(parts[0])
    assert check.page_count == 2
    check.close()
    ranged = doc2.split_to_files(os.path.join(TMP, "ranged"), mode="ranges",
                                 ranges=[(0, 0), (2, 4)], stem="range")
    assert len(ranged) == 2
    check = fitz.open(ranged[1])
    assert check.page_count == 3
    check.close()
    print("split every-N and by-ranges: ok")

    # images to pages
    png = os.path.join(TMP, "shot.png")
    doc2.export_page_image(0, png, zoom=1.0)
    before = doc2.page_count
    added = doc2.images_to_pages([png, png], at=0)
    assert added == 2 and doc2.page_count == before + 2
    assert doc2.page(0).get_images(), "image page has no image"
    doc2.undo()
    assert doc2.page_count == before
    print("images to pages: ok")

    # ------------------------------------------------------------ stamps
    rect = doc2.add_stamp(0, "APPROVED", fitz.Point(320, 700), rotate=12)
    assert rect.width > 40
    assert "APPROVED" in doc2.page_text(0)
    assert set(STAMP_PRESETS) >= {"APPROVED", "DRAFT", "CONFIDENTIAL"}
    print("stamps: ok")

    # ------------------------------------------------ annotations listing
    doc2.add_highlight(1, fitz.Rect(72, 82, 300, 100))
    doc2.add_note(1, fitz.Point(400, 200), "Check this figure")
    annots = doc2.all_annotations()
    assert len(annots) >= 2, annots
    note = next(a for a in annots if "Text" in a["type"] or a["content"])
    assert note["page"] == 1
    assert doc2.set_annot_content(1, note["xref"], "Updated comment")
    refreshed = [a for a in doc2.all_annotations() if a["xref"] == note["xref"]]
    assert refreshed and refreshed[0]["content"] == "Updated comment"
    print("annotation listing and editing: ok")

    count = doc2.flatten_annotations([1])
    assert count >= 2, count
    assert not [a for a in doc2.all_annotations() if a["page"] == 1]
    doc2.undo()
    assert [a for a in doc2.all_annotations() if a["page"] == 1]
    print("annotation flatten + undo: ok")

    # ------------------------------------------------------- page labels
    assert doc2.set_page_numbering(style="r", start=1)
    label = doc2.page_label(0)
    assert label in ("i", "1", ""), label
    print(f"page labels (page 1 shows {label!r}): ok")

    saved = os.path.join(TMP, "final.pdf")
    doc2.save(saved)
    assert os.path.getsize(saved) > 1000
    print("save with all features: ok")

    print("\nALL FEATURE TESTS PASSED")


if __name__ == "__main__":
    main()
