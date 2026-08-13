"""Document model: wraps a PyMuPDF document with undo/redo and all edit operations.

This module is GUI-free on purpose — everything here can be exercised headless.
All geometry passed in/out of this class is in *unrotated* page coordinates
(the space PyMuPDF uses for annotations, text extraction and search). The view
layer converts to/from screen space with display_matrix()/inverse_matrix().
"""

from __future__ import annotations

import fitz  # PyMuPDF

from .fonts import FontResolver
from .textengine import EditableText

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
        self.fonts: FontResolver | None = None
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
        self.fonts = FontResolver(doc)
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
        if self.fonts is None:
            self.fonts = FontResolver(self.doc)
        else:
            self.fonts.reset(self.doc)
        self.dirty = True
        self._notify(True)

    def _done(self, structural: bool):
        self.dirty = True
        if structural and self.fonts is not None:
            self.fonts.invalidate_pages()
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

    # -------------------------------------------------------- inline editing

    @staticmethod
    def _line_size(line: dict) -> float:
        sizes = [float(s.get("size", 11.0)) for s in line.get("spans", [])]
        return max(sizes) if sizes else 11.0

    @classmethod
    def _split_block(cls, block: dict) -> list[dict]:
        """Break a PyMuPDF block into natural paragraphs.

        PyMuPDF groups anything nearby into one block, so a heading and the
        paragraph beneath it often arrive fused. Editing the heading should not
        mean editing the body text too, so we split where the type size jumps or
        the leading opens up.
        """
        lines = [ln for ln in block.get("lines", []) if ln.get("spans")]
        if len(lines) <= 1:
            return [block] if lines else []

        groups: list[list[dict]] = [[lines[0]]]
        for prev, cur in zip(lines, lines[1:]):
            prev_size, cur_size = cls._line_size(prev), cls._line_size(cur)
            try:
                gap = cur["spans"][0]["origin"][1] - prev["spans"][0]["origin"][1]
            except Exception:
                gap = 0.0
            size_jump = abs(cur_size - prev_size) / max(prev_size, cur_size, 1.0)
            big_gap = gap > max(prev_size, cur_size) * 1.75
            if size_jump > 0.18 or big_gap:
                groups.append([cur])
            else:
                groups[-1].append(cur)

        if len(groups) == 1:
            return [block]
        result = []
        for group in groups:
            rect = fitz.Rect(group[0]["bbox"])
            for line in group[1:]:
                rect |= fitz.Rect(line["bbox"])
            result.append({"type": 0, "bbox": tuple(rect), "lines": group})
        return result

    def raw_blocks(self, index: int) -> list[dict]:
        """Text blocks with per-character geometry, split into paragraphs."""
        try:
            data = self.doc[index].get_text("rawdict")
        except Exception:
            return []
        blocks = []
        for block in data.get("blocks", []):
            if block.get("type") == 0 and block.get("lines"):
                blocks.extend(self._split_block(block))
        return blocks

    def editable_at(self, index: int, point: fitz.Point,
                    slack: float = 2.0) -> EditableText | None:
        """The text block under `point`, ready to put a caret in."""
        page_rect = self.doc[index].rect
        best = None
        for block in self.raw_blocks(index):
            rect = fitz.Rect(block["bbox"]) + (-slack, -slack, slack, slack)
            if rect.contains(point) and (best is None or abs(rect) < abs(best[0])):
                best = (rect, block)
        if best is None:
            return None
        editable = EditableText.from_block(best[1], self.fonts, index, page_rect)
        editable.page_index = index
        return editable

    def editable_blocks(self, index: int) -> list[tuple[fitz.Rect, dict]]:
        return [(fitz.Rect(b["bbox"]), b) for b in self.raw_blocks(index)]

    def erase_text_in(self, page: fitz.Page, rect: fitz.Rect):
        """Remove glyphs inside rect, leaving images and vector art untouched."""
        page.add_redact_annot(rect)
        for kwargs in (
            {"images": fitz.PDF_REDACT_IMAGE_NONE,
             "graphics": getattr(fitz, "PDF_REDACT_LINE_ART_NONE", 0)},
            {"images": fitz.PDF_REDACT_IMAGE_NONE},
            {},
        ):
            try:
                page.apply_redactions(**kwargs)
                return
            except (TypeError, AttributeError):
                continue
        page.apply_redactions()

    def commit_text(self, index: int, editable: EditableText,
                    erase_rect: fitz.Rect | None = None, snapshot: bool = True):
        """Write an edited block back into the page.

        The original glyphs are erased and the block is redrawn from our layout,
        reusing the embedded font wherever the text came from one.
        """
        if snapshot:
            self._snapshot()
        page = self.doc[index]
        if erase_rect is not None:
            self.erase_text_in(page, fitz.Rect(erase_rect) + (-1.0, -1.0, 1.0, 1.0))
        for run in editable.draw_runs():
            style = run.style
            font = style.font
            fontname = font.install(page, self.fonts) if font else "helv"
            try:
                page.insert_text(fitz.Point(run.x, run.baseline), run.text,
                                 fontsize=style.size, fontname=fontname,
                                 color=style.color, render_mode=0)
            except Exception:
                page.insert_text(fitz.Point(run.x, run.baseline), run.text,
                                 fontsize=style.size, fontname="helv",
                                 color=style.color)
        self._done(False)

    def delete_text_block(self, index: int, rect: fitz.Rect):
        self._snapshot()
        self.erase_text_in(self.doc[index], fitz.Rect(rect) + (-1.0, -1.0, 1.0, 1.0))
        self._done(False)

    # --------------------------------------------------- annotation geometry

    @staticmethod
    def _apply_annot_rect(annot, target: fitz.Rect):
        """Place an annotation at exactly `target`.

        set_rect() grows the stored rect by the border width, so a naive
        move would fatten the shape a little on every drag. Measure what we
        actually got and correct once — the error is a constant offset, so a
        single compensating pass lands it precisely.
        """
        target = fitz.Rect(target)
        annot.set_rect(target)
        got = fitz.Rect(annot.rect)
        deltas = (got.x0 - target.x0, got.y0 - target.y0,
                  got.x1 - target.x1, got.y1 - target.y1)
        if max(abs(d) for d in deltas) > 0.01:
            annot.set_rect(fitz.Rect(target.x0 - deltas[0], target.y0 - deltas[1],
                                     target.x1 - deltas[2], target.y1 - deltas[3]))
        annot.update()

    def move_annot(self, index: int, xref: int, dx: float, dy: float):
        page = self.doc[index]
        for annot in page.annots():
            if annot.xref == xref:
                target = fitz.Rect(annot.rect) + (dx, dy, dx, dy)
                self._snapshot()
                try:
                    self._apply_annot_rect(annot, target)
                except Exception:
                    return
                self._done(False)
                return

    def resize_annot(self, index: int, xref: int, rect: fitz.Rect):
        page = self.doc[index]
        for annot in page.annots():
            if annot.xref == xref:
                self._snapshot()
                try:
                    self._apply_annot_rect(annot, rect)
                except Exception:
                    return
                self._done(False)
                return

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

    def search_page(self, index: int, needle: str, case_sensitive: bool = False,
                    whole_words: bool = False) -> list[fitz.Rect]:
        if not needle:
            return []
        try:
            page = self.doc[index]
            hits = page.search_for(needle) or []
        except Exception:
            return []
        if not (case_sensitive or whole_words):
            return hits

        result = []
        words = None
        for rect in hits:
            if case_sensitive:
                try:
                    if needle not in page.get_textbox(rect):
                        continue
                except Exception:
                    pass
            if whole_words:
                if words is None:
                    try:
                        words = page.get_text("words")
                    except Exception:
                        words = []
                probe = fitz.Rect(rect)
                matched = False
                for word in words:
                    wr = fitz.Rect(word[:4])
                    if wr.intersects(probe):
                        token = word[4]
                        if (token == needle if case_sensitive
                                else token.lower() == needle.lower()):
                            matched = True
                            break
                if not matched:
                    continue
            result.append(rect)
        return result

    def get_toc(self) -> list:
        try:
            return self.doc.get_toc() or []
        except Exception:
            return []

    def add_text_markup(self, index: int, kind: str, rects: list[fitz.Rect],
                        color=HIGHLIGHT_YELLOW):
        """Highlight / underline / strike out a run of text."""
        if not rects:
            return
        self._snapshot()
        page = self.doc[index]
        adder = {"highlight": page.add_highlight_annot,
                 "underline": page.add_underline_annot,
                 "strikeout": page.add_strikeout_annot}.get(kind)
        if adder is None:
            return
        annot = adder(rects)
        if annot:
            annot.set_colors(stroke=color)
            annot.update()
        self._done(False)

    def page_text(self, index: int) -> str:
        return self.doc[index].get_text()

    def export_page_image(self, index: int, path: str, zoom: float = 2.0):
        self.doc[index].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).save(path)
