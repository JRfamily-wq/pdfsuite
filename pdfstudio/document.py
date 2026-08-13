"""Document model: wraps a PyMuPDF document with undo/redo and all edit operations.

This module is GUI-free on purpose — everything here can be exercised headless.
All geometry passed in/out of this class is in *unrotated* page coordinates
(the space PyMuPDF uses for annotations, text extraction and search). The view
layer converts to/from screen space with display_matrix()/inverse_matrix().
"""

from __future__ import annotations

import fitz  # PyMuPDF

A4 = (595.0, 842.0)
LETTER = (612.0, 792.0)
LEGAL = (612.0, 1008.0)
PAGE_SIZES = {"A4": A4, "Letter": LETTER, "Legal": LEGAL}

BLACK = (0.0, 0.0, 0.0)
WHITE = (1.0, 1.0, 1.0)
HIGHLIGHT_YELLOW = (1.0, 0.85, 0.0)


class PdfError(Exception):
    pass


class PdfDocument:
    """A PDF document with snapshot-based undo/redo.

    The document is always held fully in memory (opened from bytes), so saving
    never fights the OS over an open file handle and undo snapshots are cheap
    to restore.
    """

    MAX_UNDO = 15
    # Documents bigger than this only keep a couple of undo steps to bound RAM.
    BIG_DOC_BYTES = 120 * 1024 * 1024

    def __init__(self):
        self.doc: fitz.Document | None = None
        self.path: str | None = None
        self.dirty = False
        self._undo: list[bytes] = []
        self._redo: list[bytes] = []
        # callback(structural: bool) — structural means page count/order/size changed
        self.on_changed = None

    # ------------------------------------------------------------- lifecycle

    def is_open(self) -> bool:
        return self.doc is not None

    @property
    def page_count(self) -> int:
        return self.doc.page_count if self.doc else 0

    def page(self, index: int) -> fitz.Page:
        return self.doc[index]

    def new(self, pages: int = 1, size: tuple[float, float] = A4):
        doc = fitz.open()
        width, height = size
        for _ in range(max(1, int(pages))):
            doc.new_page(width=width, height=height)
        self._replace_doc(doc, path=None, dirty=True)

    def open(self, path: str, password: str | None = None) -> str:
        """Returns 'ok', 'needs_password' or 'bad_password'."""
        with open(path, "rb") as fh:
            data = fh.read()
        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise PdfError(f"Could not open file: {exc}") from exc
        if doc.needs_pass:
            if not password:
                doc.close()
                return "needs_password"
            if not doc.authenticate(password):
                doc.close()
                return "bad_password"
        self._replace_doc(doc, path=path, dirty=False)
        return "ok"

    def _replace_doc(self, doc: fitz.Document, path: str | None, dirty: bool):
        if self.doc is not None:
            try:
                self.doc.close()
            except Exception:
                pass
        self.doc = doc
        self.path = path
        self.dirty = dirty
        self._undo.clear()
        self._redo.clear()
        self._notify(True)

    def save(self, path: str | None = None, optimize: bool = False,
             user_pw: str | None = None, owner_pw: str | None = None):
        path = path or self.path
        if not path:
            raise PdfError("No file name given")
        kwargs = {"garbage": 4 if optimize else 3, "deflate": True}
        if optimize:
            kwargs["clean"] = True
        if user_pw or owner_pw:
            kwargs.update(
                encryption=fitz.PDF_ENCRYPT_AES_256,
                user_pw=user_pw or "",
                owner_pw=owner_pw or user_pw or "",
            )
        data = self.doc.tobytes(**kwargs)
        with open(path, "wb") as fh:
            fh.write(data)
        self.path = path
        self.dirty = False
        self._notify(False)

    # ------------------------------------------------------------ undo/redo

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def _snapshot(self):
        try:
            data = self.doc.tobytes()
        except Exception:
            return  # snapshot failure should never block an edit
        limit = 2 if len(data) > self.BIG_DOC_BYTES else self.MAX_UNDO
        self._undo.append(data)
        while len(self._undo) > limit:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        try:
            self._redo.append(self.doc.tobytes())
        except Exception:
            pass
        self._load_bytes(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        try:
            self._undo.append(self.doc.tobytes())
        except Exception:
            pass
        self._load_bytes(self._redo.pop())
        return True

    def _load_bytes(self, data: bytes):
        old = self.doc
        self.doc = fitz.open(stream=data, filetype="pdf")
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
        self.dirty = True
        self._notify(True)

    def _done(self, structural: bool):
        self.dirty = True
        self._notify(structural)

    def _notify(self, structural: bool):
        if self.on_changed:
            self.on_changed(structural)

    # ------------------------------------------------------------- rendering

    def render(self, index: int, zoom: float) -> fitz.Pixmap:
        return self.doc[index].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)

    def display_matrix(self, index: int, zoom: float) -> fitz.Matrix:
        """Unrotated page coords -> rendered pixel coords."""
        return self.doc[index].rotation_matrix * fitz.Matrix(zoom, zoom)

    def inverse_matrix(self, index: int, zoom: float) -> fitz.Matrix:
        """Rendered pixel coords -> unrotated page coords."""
        return fitz.Matrix(1 / zoom, 1 / zoom) * self.doc[index].derotation_matrix

    # ------------------------------------------------------------- page ops

    def rotate_pages(self, indices: list[int], delta: int):
        self._snapshot()
        for i in indices:
            page = self.doc[i]
            page.set_rotation((page.rotation + delta) % 360)
        self._done(True)

    def delete_pages(self, indices: list[int]):
        indices = sorted(set(indices))
        if len(indices) >= self.page_count:
            raise PdfError("A document must keep at least one page.")
        self._snapshot()
        for i in reversed(indices):
            self.doc.delete_page(i)
        self._done(True)

    def move_page(self, src: int, dest: int):
        """Move page `src` so it ends up at index `dest`."""
        if src == dest:
            return
        self._snapshot()
        # fitz semantics: move_page(pno, to) inserts pno *before* position `to`
        # (to = -1 appends after the last page). Landing at final index `dest`
        # when moving down therefore needs to = dest + 1, or -1 for the end.
        if dest > src:
            if dest >= self.page_count - 1:
                self.doc.move_page(src, -1)
            else:
                self.doc.move_page(src, dest + 1)
        else:
            self.doc.move_page(src, dest)
        self._done(True)

    def insert_blank_page(self, at: int, like: int | None = None,
                          size: tuple[float, float] | None = None):
        self._snapshot()
        if size is None:
            ref = self.doc[like if like is not None else max(0, at - 1)]
            size = (ref.rect.width, ref.rect.height)
        self.doc.new_page(pno=at, width=size[0], height=size[1])
        self._done(True)

    def insert_pdf_file(self, path: str, at: int | None = None) -> int:
        src = fitz.open(path)
        try:
            if src.needs_pass:
                raise PdfError("That PDF is password protected — open it first and save an unlocked copy.")
            count = src.page_count
            self._snapshot()
            if at is None:
                self.doc.insert_pdf(src)
            else:
                self.doc.insert_pdf(src, start_at=at)
        finally:
            src.close()
        self._done(True)
        return count

    def extract_pages(self, indices: list[int], out_path: str):
        out = fitz.open()
        try:
            for i in indices:
                out.insert_pdf(self.doc, from_page=i, to_page=i)
            out.save(out_path, garbage=2, deflate=True)
        finally:
            out.close()

    # ----------------------------------------------------------- annotations

    def add_highlight(self, index: int, rect: fitz.Rect):
        self._snapshot()
        page = self.doc[index]  # keep the page alive while the annot is used
        annot = page.add_highlight_annot(rect)
        if annot:
            annot.set_colors(stroke=HIGHLIGHT_YELLOW)
            annot.update()
        self._done(False)

    def add_shape(self, index: int, kind: str, rect: fitz.Rect,
                  color=BLACK, width: float = 2.0, fill=None):
        self._snapshot()
        page = self.doc[index]
        annot = page.add_rect_annot(rect) if kind == "rect" else page.add_circle_annot(rect)
        annot.set_border(width=width)
        annot.set_colors(stroke=color, fill=fill)
        annot.update()
        self._done(False)

    def add_line(self, index: int, p1: fitz.Point, p2: fitz.Point,
                 color=BLACK, width: float = 2.0, arrow: bool = False):
        self._snapshot()
        page = self.doc[index]
        annot = page.add_line_annot(p1, p2)
        annot.set_border(width=width)
        annot.set_colors(stroke=color)
        if arrow:
            try:
                annot.set_line_ends(fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_OPEN_ARROW)
            except Exception:
                pass
        annot.update()
        self._done(False)

    def add_ink(self, index: int, points: list[tuple[float, float]],
                color=BLACK, width: float = 2.0):
        if len(points) < 2:
            return
        self._snapshot()
        page = self.doc[index]
        annot = page.add_ink_annot([points])
        annot.set_border(width=width)
        annot.set_colors(stroke=color)
        annot.update()
        self._done(False)

    def add_textbox(self, index: int, rect: fitz.Rect, text: str,
                    fontsize: float = 14.0, color=BLACK):
        self._snapshot()
        page = self.doc[index]
        try:
            annot = page.add_freetext_annot(
                rect, text, fontsize=fontsize, fontname="helv",
                text_color=color, fill_color=None, border_color=None)
        except TypeError:  # older/newer signature differences
            annot = page.add_freetext_annot(rect, text, fontsize=fontsize,
                                            text_color=color)
        annot.update()
        self._done(False)

    def add_note(self, index: int, point: fitz.Point, text: str):
        self._snapshot()
        page = self.doc[index]
        annot = page.add_text_annot(point, text, icon="Comment")
        annot.update()
        self._done(False)

    def add_image(self, index: int, rect: fitz.Rect, image_path: str):
        self._snapshot()
        self.doc[index].insert_image(rect, filename=image_path, keep_proportion=True)
        self._done(False)

    @staticmethod
    def image_size(image_path: str) -> tuple[int, int]:
        pix = fitz.Pixmap(image_path)
        return pix.width, pix.height

    def redact_area(self, index: int, rect: fitz.Rect, fill=BLACK):
        """Permanently removes text/vector content under rect and paints fill.

        fill=WHITE is the 'whiteout' tool, fill=BLACK is true redaction.
        """
        self._snapshot()
        page = self.doc[index]
        page.add_redact_annot(rect, fill=fill)
        try:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        except TypeError:
            page.apply_redactions()
        self._done(False)

    def annot_at(self, index: int, point: fitz.Point):
        """Smallest annotation whose rect contains point -> (xref, rect) or None."""
        best = None
        for annot in self.doc[index].annots():
            rect = fitz.Rect(annot.rect)
            if rect.contains(point) and (best is None or abs(rect) < abs(best[1])):
                best = (annot.xref, rect)
        return best

    def annot_rect(self, index: int, xref: int) -> fitz.Rect | None:
        for annot in self.doc[index].annots():
            if annot.xref == xref:
                return fitz.Rect(annot.rect)
        return None

    def delete_annot(self, index: int, xref: int) -> bool:
        page = self.doc[index]
        target = None
        for annot in page.annots():
            if annot.xref == xref:
                target = annot
                break
        if target is None:
            return False
        self._snapshot()
        page.delete_annot(target)
        self._done(False)
        return True

    # ------------------------------------------------------------- text edit

    def block_at(self, index: int, point: fitz.Point):
        """Text block under point (dict with 'bbox' and 'lines'), or None."""
        data = self.doc[index].get_text("dict")
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            if fitz.Rect(block["bbox"]).contains(point):
                return block
        return None

    @staticmethod
    def block_text(block) -> str:
        lines = []
        for line in block.get("lines", []):
            lines.append("".join(span.get("text", "") for span in line.get("spans", [])))
        return "\n".join(lines)

    def replace_block_text(self, index: int, block, new_text: str):
        """Approximate text editing: redact the block, re-insert new text in its
        place at the detected font size/colour. Uses Helvetica, so exotic fonts
        will change appearance — good enough for corrections and small edits."""
        self._snapshot()
        page = self.doc[index]
        rect = fitz.Rect(block["bbox"])
        fontsize, color = 11.0, BLACK
        try:
            span = block["lines"][0]["spans"][0]
            fontsize = float(span.get("size", 11.0))
            color = fitz.sRGB_to_pdf(span.get("color", 0))
        except Exception:
            pass
        shrink = fitz.Rect(rect.x0 + 0.5, rect.y0 + 0.5, rect.x1 - 0.5, rect.y1 - 0.5)
        page.add_redact_annot(shrink)
        try:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        except TypeError:
            page.apply_redactions()
        if new_text.strip():
            box = fitz.Rect(rect.x0, rect.y0, rect.x1 + 2, rect.y1 + 2)
            size = fontsize
            while size >= 6.0:
                try:
                    leftover = page.insert_textbox(box, new_text, fontsize=size,
                                                   fontname="helv", color=color)
                except ValueError:
                    leftover = -1
                if leftover >= 0:
                    break
                size -= 0.5
            else:
                # Still doesn't fit: allow the box to grow downward.
                tall = fitz.Rect(rect.x0, rect.y0, rect.x1 + 2,
                                 rect.y1 + 6 * fontsize)
                page.insert_textbox(tall, new_text, fontsize=6.0,
                                    fontname="helv", color=color)
        self._done(False)

    # ------------------------------------------------------------ doc tools

    def add_watermark(self, text: str, fontsize: float = 48.0,
                      color=(0.6, 0.6, 0.6), opacity: float = 0.18):
        self._snapshot()
        for page in self.doc:
            rect = page.rect
            center = fitz.Point((rect.x0 + rect.x1) / 2,
                                (rect.y0 + rect.y1) / 2) * page.derotation_matrix
            length = fitz.get_text_length(text, fontname="helv", fontsize=fontsize)
            pos = fitz.Point(center.x - length / 2, center.y)
            morph = (center, fitz.Matrix(1, 1).prerotate(45))
            try:
                page.insert_text(pos, text, fontsize=fontsize, fontname="helv",
                                 color=color, fill_opacity=opacity, morph=morph)
            except TypeError:
                page.insert_text(pos, text, fontsize=fontsize, fontname="helv",
                                 color=color, morph=morph)
        self._done(False)

    def add_page_numbers(self, fmt: str = "{n} / {total}",
                         position: str = "bottom-center", start: int = 1):
        self._snapshot()
        total = self.page_count
        for i, page in enumerate(self.doc):
            label = fmt.format(n=i + start, total=total)
            length = fitz.get_text_length(label, fontname="helv", fontsize=10)
            rect = page.rect
            y = rect.y1 - 20
            if position.endswith("left"):
                x = rect.x0 + 36
            elif position.endswith("right"):
                x = rect.x1 - 36 - length
            else:
                x = (rect.x0 + rect.x1 - length) / 2
            point = fitz.Point(x, y) * page.derotation_matrix
            page.insert_text(point, label, fontsize=10, fontname="helv",
                             color=(0.25, 0.25, 0.25), rotate=page.rotation)
        self._done(False)

    def get_metadata(self) -> dict:
        return dict(self.doc.metadata or {})

    def set_metadata(self, updates: dict):
        self._snapshot()
        meta = self.get_metadata()
        meta.update(updates)
        self.doc.set_metadata(meta)
        self._done(False)

    def search_page(self, index: int, needle: str) -> list[fitz.Rect]:
        try:
            return self.doc[index].search_for(needle) or []
        except Exception:
            return []

    def page_text(self, index: int) -> str:
        return self.doc[index].get_text()

    def export_page_image(self, index: int, path: str, zoom: float = 2.0):
        self.doc[index].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).save(path)
