"""Document capabilities beyond basic editing: forms, bookmarks, links,
attachments, stamps and page surgery.

These live in a mixin rather than in document.py so each file stays a
readable size. Everything here runs through PdfDocument._snapshot(), so all
of it participates in undo exactly like the drawing tools do.
"""

from __future__ import annotations

import os

import fitz

STAMP_PRESETS = {
    "APPROVED": (0.10, 0.55, 0.20),
    "REJECTED": (0.80, 0.13, 0.16),
    "DRAFT": (0.45, 0.47, 0.52),
    "CONFIDENTIAL": (0.80, 0.13, 0.16),
    "REVIEWED": (0.13, 0.40, 0.75),
    "FINAL": (0.10, 0.55, 0.20),
    "URGENT": (0.85, 0.35, 0.05),
    "COPY": (0.45, 0.47, 0.52),
}

FIELD_TEXT = "text"
FIELD_CHECKBOX = "checkbox"
FIELD_RADIO = "radio"
FIELD_CHOICE = "choice"
FIELD_SIGNATURE = "signature"
FIELD_BUTTON = "button"


class FormField:
    """A form field, decoupled from the live widget object.

    PyMuPDF widgets are bound to a Page and become unusable once that page is
    garbage collected, so the UI holds these plain snapshots instead and looks
    the widget back up by name when it is time to write a value.
    """

    def __init__(self, page: int, widget):
        self.page = page
        self.name = widget.field_name or ""
        self.label = widget.field_label or self.name
        self.value = widget.field_value
        self.rect = fitz.Rect(widget.rect)
        self.choices = list(widget.choice_values or [])
        self.read_only = bool(widget.field_flags & 1)
        self.max_len = getattr(widget, "text_maxlen", 0) or 0
        self.kind = self._classify(widget.field_type)

    @staticmethod
    def _classify(field_type: int) -> str:
        return {
            fitz.PDF_WIDGET_TYPE_TEXT: FIELD_TEXT,
            fitz.PDF_WIDGET_TYPE_CHECKBOX: FIELD_CHECKBOX,
            fitz.PDF_WIDGET_TYPE_RADIOBUTTON: FIELD_RADIO,
            fitz.PDF_WIDGET_TYPE_COMBOBOX: FIELD_CHOICE,
            fitz.PDF_WIDGET_TYPE_LISTBOX: FIELD_CHOICE,
            fitz.PDF_WIDGET_TYPE_SIGNATURE: FIELD_SIGNATURE,
        }.get(field_type, FIELD_BUTTON)

    @property
    def checked(self) -> bool:
        return str(self.value).lower() not in ("off", "false", "none", "", "0")

    def __repr__(self):
        return f"<FormField {self.name!r} {self.kind} p{self.page + 1}>"


class DocumentFeatures:
    """Mixin for PdfDocument. Relies on self.doc, self._snapshot(), self._done()."""

    # --------------------------------------------------------------- forms

    @property
    def has_form(self) -> bool:
        try:
            return bool(self.doc.is_form_pdf)
        except Exception:
            return False

    def form_fields(self, index: int | None = None) -> list[FormField]:
        """Every fillable field, or just those on one page."""
        pages = [index] if index is not None else range(self.page_count)
        fields: list[FormField] = []
        for pno in pages:
            try:
                page = self.doc[pno]
                for widget in page.widgets():
                    fields.append(FormField(pno, widget))
            except Exception:
                continue
        return fields

    def field_at(self, index: int, point: fitz.Point) -> FormField | None:
        best = None
        for field in self.form_fields(index):
            if field.rect.contains(point) and (best is None or abs(field.rect) < abs(best.rect)):
                best = field
        return best

    def _clear_text_widget(self, page: fitz.Page, name: str) -> bool:
        """Empty a text field.

        PyMuPDF silently ignores assigning "" or None to a text widget — the
        old value simply survives — so the value key is cleared on the PDF
        object itself and the appearance stream is then regenerated from the
        now-empty widget. Without that second step the field reads as empty
        while the page still visibly draws the old text.
        """
        target = next((w for w in page.widgets() if w.field_name == name), None)
        if target is None:
            return False
        try:
            self.doc.xref_set_key(target.xref, "V", "()")
        except Exception:
            return False
        refreshed = next((w for w in page.widgets() if w.field_name == name), None)
        if refreshed is not None:
            try:
                refreshed.update()
            except Exception:
                pass
        return True

    def set_field_value(self, index: int, name: str, value, snapshot: bool = True) -> bool:
        page = self.doc[index]      # keep the page alive while widgets are used
        widget = next((w for w in page.widgets() if w.field_name == name), None)
        if widget is None:
            return False
        if snapshot:
            self._snapshot()
        try:
            if widget.field_type in (fitz.PDF_WIDGET_TYPE_CHECKBOX,
                                     fitz.PDF_WIDGET_TYPE_RADIOBUTTON):
                widget.field_value = bool(value)
                widget.update()
            elif value in (None, "") and widget.field_type == fitz.PDF_WIDGET_TYPE_TEXT:
                if not self._clear_text_widget(page, name):
                    return False
            else:
                widget.field_value = str(value)
                widget.update()
        except Exception:
            return False
        self._done(False)
        return True

    def reset_form(self):
        """Clear every field back to empty/unticked."""
        self._snapshot()
        for pno in range(self.page_count):
            page = self.doc[pno]    # keep the page alive while widgets are used
            names_to_clear = []
            for widget in page.widgets():
                try:
                    if widget.field_type in (fitz.PDF_WIDGET_TYPE_CHECKBOX,
                                             fitz.PDF_WIDGET_TYPE_RADIOBUTTON):
                        widget.field_value = False
                        widget.update()
                    elif widget.field_type == fitz.PDF_WIDGET_TYPE_TEXT:
                        names_to_clear.append(widget.field_name)
                    elif widget.field_type in (fitz.PDF_WIDGET_TYPE_COMBOBOX,
                                               fitz.PDF_WIDGET_TYPE_LISTBOX):
                        # A choice field can only hold one of its own options,
                        # so "empty" means the first choice unless one is blank.
                        choices = list(widget.choice_values or [])
                        blank = next((c for c in choices if not str(c).strip()), None)
                        if blank is not None or choices:
                            widget.field_value = blank if blank is not None else choices[0]
                            widget.update()
                except Exception:
                    continue
            for name in names_to_clear:
                self._clear_text_widget(page, name)
        self._done(False)

    def flatten_form(self):
        """Burn field values into the page and remove the fields.

        Produces a document that shows the same content but can no longer be
        edited or re-submitted — what you want before sending a filled form on.
        """
        self._snapshot()
        for pno in range(self.page_count):
            page = self.doc[pno]
            for widget in list(page.widgets()):
                value = widget.field_value
                rect = fitz.Rect(widget.rect)
                kind = FormField._classify(widget.field_type)
                try:
                    page.delete_widget(widget)
                except Exception:
                    continue
                if kind in (FIELD_CHECKBOX, FIELD_RADIO):
                    if str(value).lower() not in ("off", "false", "none", "", "0"):
                        self._draw_tick(page, rect)
                elif value:
                    size = min(11.0, max(6.0, rect.height * 0.62))
                    box = fitz.Rect(rect.x0 + 2, rect.y0, rect.x1, rect.y1 + 2)
                    try:
                        page.insert_textbox(box, str(value), fontsize=size,
                                            fontname="helv", color=(0, 0, 0))
                    except Exception:
                        pass
        self._done(False)

    @staticmethod
    def _draw_tick(page: fitz.Page, rect: fitz.Rect):
        inset = rect.width * 0.22
        p1 = fitz.Point(rect.x0 + inset, rect.y0 + rect.height * 0.55)
        p2 = fitz.Point(rect.x0 + rect.width * 0.44, rect.y1 - inset)
        p3 = fitz.Point(rect.x1 - inset * 0.7, rect.y0 + inset)
        shape = page.new_shape()
        shape.draw_line(p1, p2)
        shape.draw_line(p2, p3)
        shape.finish(color=(0, 0, 0), width=max(1.0, rect.width * 0.09))
        shape.commit()

    # ----------------------------------------------------------- bookmarks

    def set_toc(self, toc: list) -> bool:
        self._snapshot()
        try:
            self.doc.set_toc(toc)
        except Exception:
            return False
        self._done(False)
        return True

    def add_bookmark(self, title: str, page: int, level: int = 1) -> bool:
        toc = self.get_toc()
        entry = [max(1, level), title or "Untitled", page + 1]
        for i, row in enumerate(toc):
            if row[2] > page + 1:
                toc.insert(i, entry)
                break
        else:
            toc.append(entry)
        return self.set_toc(self._normalise_toc(toc))

    def remove_bookmark(self, position: int) -> bool:
        toc = self.get_toc()
        if not (0 <= position < len(toc)):
            return False
        del toc[position]
        return self.set_toc(self._normalise_toc(toc))

    def rename_bookmark(self, position: int, title: str) -> bool:
        toc = self.get_toc()
        if not (0 <= position < len(toc)):
            return False
        toc[position][1] = title
        return self.set_toc(toc)

    def shift_bookmark_level(self, position: int, delta: int) -> bool:
        toc = self.get_toc()
        if not (0 <= position < len(toc)):
            return False
        toc[position][0] = max(1, toc[position][0] + delta)
        return self.set_toc(self._normalise_toc(toc))

    @staticmethod
    def _normalise_toc(toc: list) -> list:
        """A level may only ever be one deeper than the entry above it."""
        cleaned = []
        previous = 0
        for level, title, page in ([r[0], r[1], r[2]] for r in toc):
            level = max(1, min(level, previous + 1))
            cleaned.append([level, title, page])
            previous = level
        return cleaned

    def bookmarks_from_headings(self, min_size_ratio: float = 1.25) -> int:
        """Build a table of contents from text that looks like headings.

        Anything set noticeably larger than the document's body size, and short
        enough to be a title, becomes a bookmark.
        """
        sizes: dict[float, int] = {}
        for pno in range(self.page_count):
            for block in self.raw_blocks(pno):
                for line in block["lines"]:
                    for span in line["spans"]:
                        size = round(float(span.get("size", 0)), 1)
                        count = sum(len(s.get("chars", [])) for s in line["spans"])
                        sizes[size] = sizes.get(size, 0) + count
        if not sizes:
            return 0
        body = max(sizes.items(), key=lambda kv: kv[1])[0]
        threshold = body * min_size_ratio

        toc, seen = [], set()
        for pno in range(self.page_count):
            for block in self.raw_blocks(pno):
                text, size = [], 0.0
                for line in block["lines"]:
                    for span in line["spans"]:
                        size = max(size, float(span.get("size", 0)))
                        text.append("".join(c.get("c", "") for c in span.get("chars", [])))
                title = " ".join("".join(text).split())
                if size >= threshold and 2 <= len(title) <= 90:
                    key = (title, pno)
                    if key not in seen:
                        seen.add(key)
                        level = 1 if size >= threshold * 1.25 else 2
                        toc.append([level, title, pno + 1])
        if not toc:
            return 0
        self.set_toc(self._normalise_toc(toc))
        return len(toc)

    # --------------------------------------------------------------- links

    def page_links(self, index: int) -> list[dict]:
        try:
            return self.doc[index].get_links() or []
        except Exception:
            return []

    def add_uri_link(self, index: int, rect: fitz.Rect, uri: str):
        self._snapshot()
        self.doc[index].insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(rect),
                                     "uri": uri})
        self._done(False)

    def add_goto_link(self, index: int, rect: fitz.Rect, target_page: int):
        self._snapshot()
        self.doc[index].insert_link({"kind": fitz.LINK_GOTO, "from": fitz.Rect(rect),
                                     "page": target_page})
        self._done(False)

    def link_at(self, index: int, point: fitz.Point) -> dict | None:
        for link in self.page_links(index):
            if fitz.Rect(link["from"]).contains(point):
                return link
        return None

    def remove_link(self, index: int, link: dict) -> bool:
        page = self.doc[index]
        target = fitz.Rect(link["from"])
        for existing in page.get_links():
            if fitz.Rect(existing["from"]) == target:
                self._snapshot()
                try:
                    page.delete_link(existing)
                except Exception:
                    return False
                self._done(False)
                return True
        return False

    # --------------------------------------------------------- attachments

    def attachments(self) -> list[dict]:
        result = []
        try:
            for name in self.doc.embfile_names():
                info = self.doc.embfile_info(name)
                result.append({"name": name,
                               "filename": info.get("filename", name),
                               "desc": info.get("desc", ""),
                               "size": info.get("size", 0)})
        except Exception:
            pass
        return result

    def attach_file(self, path: str, desc: str = "") -> bool:
        with open(path, "rb") as fh:
            data = fh.read()
        name = os.path.basename(path)
        self._snapshot()
        try:
            self.doc.embfile_add(name, data, filename=name, desc=desc or name)
        except Exception:
            return False
        self._done(False)
        return True

    def extract_attachment(self, name: str, out_path: str) -> bool:
        try:
            data = self.doc.embfile_get(name)
        except Exception:
            return False
        with open(out_path, "wb") as fh:
            fh.write(data)
        return True

    def delete_attachment(self, name: str) -> bool:
        self._snapshot()
        try:
            self.doc.embfile_del(name)
        except Exception:
            return False
        self._done(False)
        return True

    # ------------------------------------------------------- page surgery

    def crop_pages(self, indices: list[int], rect: fitz.Rect):
        self._snapshot()
        for i in indices:
            page = self.doc[i]
            box = fitz.Rect(rect) & page.mediabox
            if box.is_empty or box.width < 10 or box.height < 10:
                continue
            try:
                page.set_cropbox(box)
            except Exception:
                continue
        self._done(True)

    def reset_crop(self, indices: list[int]):
        self._snapshot()
        for i in indices:
            try:
                self.doc[i].set_cropbox(self.doc[i].mediabox)
            except Exception:
                continue
        self._done(True)

    def split_to_files(self, out_dir: str, mode: str = "every",
                       size: int = 1, ranges: list[tuple[int, int]] | None = None,
                       stem: str = "part") -> list[str]:
        """Split into several PDFs. mode: 'every' | 'ranges' | 'bookmarks'."""
        os.makedirs(out_dir, exist_ok=True)
        chunks: list[tuple[int, int]] = []
        if mode == "ranges" and ranges:
            chunks = [(max(0, a), min(self.page_count - 1, b)) for a, b in ranges]
        elif mode == "bookmarks":
            starts = sorted({max(0, row[2] - 1) for row in self.get_toc() if row[0] == 1})
            if not starts:
                starts = [0]
            if starts[0] != 0:
                starts.insert(0, 0)
            for i, start in enumerate(starts):
                end = (starts[i + 1] - 1) if i + 1 < len(starts) else self.page_count - 1
                if end >= start:
                    chunks.append((start, end))
        else:
            step = max(1, int(size))
            for start in range(0, self.page_count, step):
                chunks.append((start, min(start + step - 1, self.page_count - 1)))

        written = []
        for n, (start, end) in enumerate(chunks, 1):
            out = fitz.open()
            try:
                out.insert_pdf(self.doc, from_page=start, to_page=end)
                path = os.path.join(out_dir, f"{stem}-{n:03d}.pdf")
                out.save(path, garbage=3, deflate=True)
                written.append(path)
            finally:
                out.close()
        return written

    def scale_pages(self, indices: list[int], factor: float):
        """Resize pages, keeping content proportional."""
        if abs(factor - 1.0) < 0.001:
            return
        self._snapshot()
        for i in indices:
            page = self.doc[i]
            rect = page.rect
            target = fitz.Rect(0, 0, rect.width * factor, rect.height * factor)
            try:
                page.set_mediabox(target)
            except Exception:
                continue
        self._done(True)

    def images_to_pages(self, image_paths: list[str], at: int | None = None,
                        page_size: tuple[float, float] | None = None,
                        margin: float = 0.0) -> int:
        """Add each image as its own page."""
        if not image_paths:
            return 0
        self._snapshot()
        insert_at = self.page_count if at is None else at
        added = 0
        for path in image_paths:
            try:
                pix = fitz.Pixmap(path)
            except Exception:
                continue
            if page_size:
                width, height = page_size
            else:
                width, height = float(pix.width), float(pix.height)
            page = self.doc.new_page(pno=insert_at, width=width, height=height)
            box = fitz.Rect(margin, margin, width - margin, height - margin)
            try:
                page.insert_image(box, filename=path, keep_proportion=True)
            except Exception:
                pass
            insert_at += 1
            added += 1
        self._done(True)
        return added

    # ------------------------------------------------------------- stamps

    def add_stamp(self, index: int, text: str, point: fitz.Point,
                  fontsize: float = 26.0, color=None, rotate: float = 0.0):
        """A bordered text stamp, the APPROVED / DRAFT kind."""
        colour = color or STAMP_PRESETS.get(text.upper(), (0.80, 0.13, 0.16))
        self._snapshot()
        page = self.doc[index]
        length = fitz.get_text_length(text, fontname="hebo", fontsize=fontsize)
        pad_x, pad_y = fontsize * 0.5, fontsize * 0.38
        rect = fitz.Rect(point.x, point.y,
                         point.x + length + pad_x * 2,
                         point.y + fontsize + pad_y * 2)
        morph = None
        if rotate:
            centre = fitz.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
            morph = (centre, fitz.Matrix(1, 1).prerotate(rotate))
        shape = page.new_shape()
        shape.draw_rect(rect)
        shape.finish(color=colour, width=max(1.6, fontsize * 0.07), fill=None,
                     morph=morph)
        shape.insert_text(fitz.Point(rect.x0 + pad_x, rect.y0 + pad_y + fontsize * 0.82),
                          text, fontsize=fontsize, fontname="hebo", color=colour,
                          morph=morph)
        shape.commit()
        self._done(False)
        return rect

    # ------------------------------------------------- annotation handling

    def all_annotations(self) -> list[dict]:
        """Every annotation in the document, for the comments panel."""
        result = []
        for pno in range(self.page_count):
            try:
                page = self.doc[pno]
            except Exception:
                continue
            for annot in page.annots():
                try:
                    info = annot.info
                    result.append({
                        "page": pno,
                        "xref": annot.xref,
                        "type": annot.type[1],
                        "rect": fitz.Rect(annot.rect),
                        "content": (info.get("content") or "").strip(),
                        "author": (info.get("title") or "").strip(),
                        "modified": info.get("modDate", ""),
                    })
                except Exception:
                    continue
        return result

    def set_annot_content(self, index: int, xref: int, text: str) -> bool:
        page = self.doc[index]
        for annot in page.annots():
            if annot.xref == xref:
                self._snapshot()
                try:
                    info = annot.info
                    info["content"] = text
                    annot.set_info(info)
                    annot.update()
                except Exception:
                    return False
                self._done(False)
                return True
        return False

    def flatten_annotations(self, indices: list[int] | None = None) -> int:
        """Bake annotations into the page content so they cannot be edited."""
        pages = indices if indices is not None else list(range(self.page_count))
        self._snapshot()
        flattened = 0
        for pno in pages:
            page = self.doc[pno]
            annots = list(page.annots())
            if not annots:
                continue
            for annot in annots:
                try:
                    pix = annot.get_pixmap(alpha=True)
                    rect = fitz.Rect(annot.rect)
                    page.delete_annot(annot)
                    if pix.width and pix.height:
                        page.insert_image(rect, pixmap=pix, overlay=True)
                    flattened += 1
                except Exception:
                    continue
        self._done(False)
        return flattened

    # -------------------------------------------------------- page labels

    def set_page_numbering(self, style: str = "D", prefix: str = "",
                           start: int = 1, from_page: int = 0) -> bool:
        """Set the page labels shown in a reader's page box (i, ii, A-1, ...)."""
        self._snapshot()
        try:
            self.doc.set_page_labels([{"startpage": from_page, "prefix": prefix,
                                       "style": style, "firstpagenum": start}])
        except Exception:
            return False
        self._done(False)
        return True

    def page_label(self, index: int) -> str:
        try:
            return self.doc[index].get_label() or ""
        except Exception:
            return ""
