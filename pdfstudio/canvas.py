"""Continuous multi-page canvas — rendering, tools, and inline text editing.

Pages are stacked vertically and only the visible ones are rendered, so a
500-page file scrolls as smoothly as a one-pager. All direct manipulation
lives here: the caret, dragging text and annotations, resize handles, marquee
tools and text selection.
"""

from __future__ import annotations

from dataclasses import dataclass

import fitz
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QGuiApplication, QImage,
                           QKeyEvent, QPainter, QPen, QPixmap, QPolygon)
from PySide6.QtWidgets import QApplication, QWidget

from . import theme
from .textengine import EditableText

PAGE_GAP = 18
CANVAS_MARGIN = 20
HANDLE = 7


class Tool:
    SELECT = "select"
    TEXT_SELECT = "textselect"
    EDIT_TEXT = "edittext"
    TEXT = "text"
    HIGHLIGHT = "highlight"
    UNDERLINE = "underline"
    STRIKEOUT = "strikeout"
    RECT = "rect"
    ELLIPSE = "ellipse"
    LINE = "line"
    ARROW = "arrow"
    INK = "ink"
    WHITEOUT = "whiteout"
    REDACT = "redact"
    IMAGE = "image"
    NOTE = "note"
    STAMP = "stamp"
    SNAPSHOT = "snapshot"
    LINK = "link"
    CROP = "crop"


class ViewMode:
    CONTINUOUS = "continuous"
    SINGLE = "single"
    FACING = "facing"


MARQUEE_TOOLS = {Tool.RECT, Tool.ELLIPSE, Tool.WHITEOUT, Tool.REDACT,
                 Tool.IMAGE, Tool.TEXT, Tool.SNAPSHOT, Tool.LINK, Tool.CROP}
LINE_TOOLS = {Tool.LINE, Tool.ARROW}
TEXT_MARKUP_TOOLS = {Tool.HIGHLIGHT, Tool.UNDERLINE, Tool.STRIKEOUT}

CURSORS = {
    Tool.SELECT: Qt.ArrowCursor,
    Tool.TEXT_SELECT: Qt.IBeamCursor,
    Tool.EDIT_TEXT: Qt.IBeamCursor,
    Tool.NOTE: Qt.PointingHandCursor,
    Tool.STAMP: Qt.PointingHandCursor,
}

HINTS = {
    Tool.SELECT: "Click an object to select · drag to move · drag a handle to resize · space+drag to pan",
    Tool.TEXT_SELECT: "Drag across text to select it, then Ctrl+C to copy",
    Tool.EDIT_TEXT: "Click into any text to edit it · drag its border to move the block · Esc when done",
    Tool.TEXT: "Drag a box (or click) to add a new text box",
    Tool.HIGHLIGHT: "Drag across text to highlight it",
    Tool.UNDERLINE: "Drag across text to underline it",
    Tool.STRIKEOUT: "Drag across text to strike it through",
    Tool.RECT: "Drag to draw a rectangle",
    Tool.ELLIPSE: "Drag to draw an ellipse",
    Tool.LINE: "Drag to draw a line",
    Tool.ARROW: "Drag to draw an arrow",
    Tool.INK: "Draw freehand",
    Tool.WHITEOUT: "Drag to erase an area to white",
    Tool.REDACT: "Drag to permanently redact an area",
    Tool.IMAGE: "Drag a box (or click) to place an image",
    Tool.NOTE: "Click to drop a sticky note",
    Tool.STAMP: "Click to place the stamp chosen in the Properties panel",
    Tool.SNAPSHOT: "Drag a region to copy it to the clipboard as an image",
    Tool.LINK: "Drag a box to turn it into a clickable link",
    Tool.CROP: "Drag the area to keep, then confirm — crops the selected pages",
}


@dataclass
class PageSlot:
    index: int
    top: float            # y in canvas logical px
    width: float
    height: float
    left: float


class PageCanvas(QWidget):
    """host provides: doc, plus the commit_* callbacks (see MainWindow)."""

    page_changed = Signal(int)
    selection_changed = Signal()
    edit_state_changed = Signal()
    status_message = Signal(str)

    def __init__(self, host):
        super().__init__()
        self.host = host
        self.zoom = 1.0
        self.fit_mode = "width"
        self.tool = Tool.SELECT
        self.color = QColor(220, 50, 50)
        self.stroke_width = 2.0
        self.font_size = 14
        self.view_mode = ViewMode.CONTINUOUS
        self.night_mode = False
        self.stamp_text = "APPROVED"
        self.slots: list[PageSlot] = []
        self._cache: dict[tuple, QPixmap] = {}
        self._current_page = 0
        self.active_field = None        # form field being edited
        self._field_buffer = ""

        # interaction state
        self._press_pos: QPoint | None = None
        self._drag_pos: QPoint | None = None
        self._press_page: int | None = None
        self._ink: list[QPoint] = []
        self._space_pan = False
        self._panning = False
        self._pan_origin = (0, 0)
        self._mode = None            # None|'marquee'|'line'|'ink'|'move'|'resize'|'textsel'|'caret'|'blockmove'
        self._handle = None

        # selected annotation
        self.sel_annot: tuple[int, int] | None = None      # (page, xref)
        self.sel_rect: fitz.Rect | None = None

        # inline text editing
        self.edit: EditableText | None = None
        self.edit_page: int | None = None
        self.edit_origin_rect: fitz.Rect | None = None
        self.edit_bg: QColor = QColor(255, 255, 255)
        self._caret_on = True
        self._caret_timer = QTimer(self)
        self._caret_timer.setInterval(530)
        self._caret_timer.timeout.connect(self._blink)
        self._hover_block: tuple[int, fitz.Rect] | None = None

        # document text selection
        self.text_sel: list[tuple[int, fitz.Rect]] = []
        self._text_sel_start = None
        self.search_hits: dict[int, list[fitz.Rect]] = {}
        self.search_current: tuple[int, int] | None = None

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    # ------------------------------------------------------------- geometry

    @property
    def doc(self):
        return self.host.doc

    def viewport_width(self) -> int:
        area = self.parentWidget()
        while area is not None and not hasattr(area, "viewport"):
            area = area.parentWidget()
        if area is None:
            return max(400, self.width())
        return area.viewport().width()

    def viewport_height(self) -> int:
        area = self.parentWidget()
        while area is not None and not hasattr(area, "viewport"):
            area = area.parentWidget()
        if area is None:
            return max(300, self.height())
        return area.viewport().height()

    def clamp_current(self):
        """Keep the current page valid after pages are removed."""
        if not self.doc.is_open():
            self._current_page = 0
            return
        limit = self.doc.page_count - 1
        if self._current_page > limit or self._current_page < 0:
            self._current_page = max(0, min(self._current_page, limit))

    def compute_fit(self):
        if not self.doc.is_open() or not self.fit_mode:
            return
        self.clamp_current()
        page = self.doc.page(self._current_page)
        avail_w = max(120, self.viewport_width() - 2 * CANVAS_MARGIN - 16)
        avail_h = max(120, self.viewport_height() - 2 * CANVAS_MARGIN)
        # Facing pages share the width between two sheets plus the gutter.
        columns = 2 if self.view_mode == ViewMode.FACING else 1
        if columns == 2:
            avail_w = (avail_w - PAGE_GAP) / 2
        zw = avail_w / max(1.0, page.rect.width)
        if self.fit_mode == "page":
            zh = avail_h / max(1.0, page.rect.height)
            self.zoom = min(zw, zh)
        else:
            self.zoom = zw
        self.zoom = max(0.08, min(self.zoom, 8.0))

    def visible_pages(self) -> list[int]:
        """Which page indices the current view mode puts on screen."""
        count = self.doc.page_count
        if self.view_mode == ViewMode.CONTINUOUS:
            return list(range(count))
        if self.view_mode == ViewMode.SINGLE:
            return [self._current_page]
        # Facing: keep page 1 alone on the right, like a printed book.
        current = self._current_page
        left = current if current % 2 == 1 else current - 1
        pair = [p for p in (left, left + 1) if 0 <= p < count]
        return pair or [current]

    def relayout(self):
        self.slots.clear()
        if not self.doc.is_open():
            self._current_page = 0
            self.setFixedSize(400, 300)
            self.update()
            return
        self.clamp_current()
        # A page that disappeared cannot stay selected or under the caret.
        if self.edit is not None and (self.edit_page is None
                                      or self.edit_page >= self.doc.page_count):
            self.cancel_edit()
        if self.sel_annot is not None and self.sel_annot[0] >= self.doc.page_count:
            self.sel_annot = None
            self.sel_rect = None
        self.compute_fit()
        pages = self.visible_pages()
        sizes = []
        for i in pages:
            rect = self.doc.page(i).rect
            sizes.append((i, rect.width * self.zoom, rect.height * self.zoom))

        if self.view_mode == ViewMode.FACING and len(sizes) == 2:
            spread_w = sizes[0][1] + PAGE_GAP + sizes[1][1]
            canvas_w = max(spread_w + 2 * CANVAS_MARGIN, self.viewport_width())
            x = (canvas_w - spread_w) / 2
            top = float(CANVAS_MARGIN)
            for index, w, h in sizes:
                self.slots.append(PageSlot(index, top, w, h, x))
                x += w + PAGE_GAP
            total_h = top + max(s[2] for s in sizes) + CANVAS_MARGIN
        else:
            widest = max((s[1] for s in sizes), default=0.0)
            canvas_w = max(widest + 2 * CANVAS_MARGIN, self.viewport_width())
            y = float(CANVAS_MARGIN)
            for index, w, h in sizes:
                self.slots.append(PageSlot(index, y, w, h, (canvas_w - w) / 2))
                y += h + PAGE_GAP
            total_h = y - PAGE_GAP + CANVAS_MARGIN

        self.setFixedSize(int(canvas_w), int(max(total_h, 100)))
        self.update()

    def set_view_mode(self, mode: str):
        self.view_mode = mode
        self.relayout()
        if mode != ViewMode.CONTINUOUS:
            area = self._scroll_area()
            if area is not None:
                area.verticalScrollBar().setValue(0)

    def set_night_mode(self, on: bool):
        self.night_mode = bool(on)
        self.invalidate_cache()
        self.update()

    def slot(self, index: int) -> PageSlot | None:
        """Slot for a *page* index. In single/facing modes only some pages are
        laid out, so this cannot index self.slots positionally."""
        for slot in self.slots:
            if slot.index == index:
                return slot
        return None

    def page_at(self, pos: QPoint):
        """(page index, page-space point) for a canvas point, or (None, None)."""
        for slot in self.slots:
            if slot.top - PAGE_GAP / 2 <= pos.y() <= slot.top + slot.height + PAGE_GAP / 2:
                return slot.index, self.to_page(slot.index, pos)
        if self.slots:
            slot = self.slots[0] if pos.y() < self.slots[0].top else self.slots[-1]
            return slot.index, self.to_page(slot.index, pos)
        return None, None

    def to_page(self, index: int, pos: QPoint) -> fitz.Point:
        slot = self.slot(index)
        if slot is None:
            return fitz.Point(0, 0)
        local = fitz.Point(pos.x() - slot.left, pos.y() - slot.top)
        return local * self.doc.inverse_matrix(index, self.zoom)

    def to_canvas(self, index: int, point: fitz.Point) -> QPointF:
        slot = self.slot(index)
        if slot is None:
            return QPointF()
        mapped = fitz.Point(point) * self.doc.display_matrix(index, self.zoom)
        return QPointF(mapped.x + slot.left, mapped.y + slot.top)

    def rect_to_canvas(self, index: int, rect: fitz.Rect) -> QRectF:
        slot = self.slot(index)
        if slot is None:
            return QRectF()
        mapped = fitz.Rect(rect) * self.doc.display_matrix(index, self.zoom)
        mapped.normalize()
        return QRectF(mapped.x0 + slot.left, mapped.y0 + slot.top,
                      max(1.0, mapped.width), max(1.0, mapped.height))

    def visible_rect(self) -> QRect:
        area = self.parentWidget()
        while area is not None and not hasattr(area, "viewport"):
            area = area.parentWidget()
        if area is None:
            return self.rect()
        origin = self.mapFrom(area.viewport(), QPoint(0, 0))
        return QRect(origin, area.viewport().size())

    # -------------------------------------------------------------- caching

    def invalidate_cache(self, index: int | None = None):
        if index is None:
            self._cache.clear()
        else:
            for key in [k for k in self._cache if k[0] == index]:
                del self._cache[key]
        self.update()

    def pixmap_for(self, index: int) -> QPixmap | None:
        dpr = self.devicePixelRatioF() or 1.0
        key = (index, round(self.zoom, 4), round(dpr, 2), self.night_mode)
        pix = self._cache.get(key)
        if pix is not None:
            return pix
        try:
            raw = self.doc.render(index, min(self.zoom * dpr, 8.0))
        except Exception:
            return None
        image = QImage(raw.samples, raw.width, raw.height, raw.stride,
                       QImage.Format_RGB888).copy()
        if self.night_mode:
            image.invertPixels()
        pix = QPixmap.fromImage(image)
        pix.setDevicePixelRatio(dpr)
        if len(self._cache) > 24:
            self._cache.clear()
        self._cache[key] = pix
        return pix

    # ----------------------------------------------------------------- zoom

    def set_zoom(self, zoom: float, fit_mode=None, anchor: QPoint | None = None):
        old_zoom = self.zoom
        self.fit_mode = fit_mode
        self.zoom = max(0.08, min(zoom, 8.0))
        if self.fit_mode:
            self.compute_fit()
        ratio = self.zoom / old_zoom if old_zoom else 1.0
        self.invalidate_cache()
        self.relayout()
        area = self._scroll_area()
        if area is not None and anchor is not None and ratio != 1.0:
            hbar, vbar = area.horizontalScrollBar(), area.verticalScrollBar()
            hbar.setValue(int(anchor.x() * ratio - (anchor.x() - hbar.value())))
            vbar.setValue(int(anchor.y() * ratio - (anchor.y() - vbar.value())))

    def _scroll_area(self):
        area = self.parentWidget()
        while area is not None and not hasattr(area, "verticalScrollBar"):
            area = area.parentWidget()
        return area

    def scroll_to_page(self, index: int, smooth_top: bool = True):
        index = max(0, min(index, self.doc.page_count - 1)) if self.doc.is_open() else 0
        # Single and facing modes show a different set of pages entirely, so
        # moving to a page means re-laying out rather than scrolling.
        if self.view_mode != ViewMode.CONTINUOUS:
            self._current_page = index
            self.relayout()
            area = self._scroll_area()
            if area is not None:
                area.verticalScrollBar().setValue(0)
            self.page_changed.emit(index)
            return
        slot = self.slot(index)
        area = self._scroll_area()
        if slot is None or area is None:
            return
        area.verticalScrollBar().setValue(int(slot.top - CANVAS_MARGIN / 2))
        self._current_page = index
        self.page_changed.emit(index)

    def ensure_visible_rect(self, index: int, rect: fitz.Rect, margin: int = 90):
        area = self._scroll_area()
        if area is None:
            return
        box = self.rect_to_canvas(index, rect)
        vbar, hbar = area.verticalScrollBar(), area.horizontalScrollBar()
        view = self.visible_rect()
        if box.top() < view.top() + margin or box.bottom() > view.bottom() - margin:
            vbar.setValue(int(box.center().y() - area.viewport().height() / 2))
        if box.left() < view.left() + margin or box.right() > view.right() - margin:
            hbar.setValue(int(box.center().x() - area.viewport().width() / 2))

    def update_current_page(self):
        if self.view_mode != ViewMode.CONTINUOUS:
            return          # the layout, not the scrollbar, decides the page
        view = self.visible_rect()
        centre = view.center().y()
        best, best_dist = self._current_page, None
        for slot in self.slots:
            mid = slot.top + slot.height / 2
            dist = abs(mid - centre)
            if best_dist is None or dist < best_dist:
                best, best_dist = slot.index, dist
        if best != self._current_page:
            self._current_page = best
            self.page_changed.emit(best)

    @property
    def current_page(self) -> int:
        return self._current_page

    # ---------------------------------------------------------------- tools

    def set_tool(self, tool: str):
        if self.edit is not None and tool != Tool.EDIT_TEXT:
            self.commit_edit()
        self.tool = tool
        self.clear_text_selection()
        self.setCursor(CURSORS.get(tool, Qt.CrossCursor))
        self.status_message.emit(HINTS.get(tool, ""))
        self.update()

    # ------------------------------------------------------- inline editing

    def begin_edit(self, index: int, point: fitz.Point) -> bool:
        editable = self.doc.editable_at(index, point)
        if editable is None:
            return False
        self.commit_edit()
        self.edit = editable
        self.edit_page = index
        self.edit_origin_rect = fitz.Rect(editable.source_rect)
        self.edit_bg = self._sample_background(index, self.edit_origin_rect)
        editable.set_caret(editable.hit_test(point))
        self._caret_on = True
        self._caret_timer.start()
        self.edit_state_changed.emit()
        self.update()
        return True

    def begin_new_text(self, index: int, rect: fitz.Rect):
        self.commit_edit()
        resolver = self.doc.fonts
        width = rect.width if rect.width > 20 else 300.0
        editable = EditableText.blank(
            resolver, (rect.x0, rect.y0), width, size=float(self.font_size),
            color=(self.color.redF(), self.color.greenF(), self.color.blueF()))
        editable.page_index = index
        editable.source_rect = fitz.Rect(rect.x0, rect.y0, rect.x0 + width,
                                         rect.y0 + self.font_size * 1.4)
        self.edit = editable
        self.edit_page = index
        self.edit_origin_rect = None          # nothing to erase; brand new text
        self.edit_bg = QColor(0, 0, 0, 0)
        self._caret_on = True
        self._caret_timer.start()
        self.edit_state_changed.emit()
        self.update()

    def commit_edit(self):
        if self.edit is None:
            return
        editable, index = self.edit, self.edit_page
        origin = self.edit_origin_rect
        self.edit = None
        self.edit_page = None
        self.edit_origin_rect = None
        self._caret_timer.stop()
        moved = getattr(editable, "_moved", False)
        if editable.dirty or moved:
            try:
                if editable.is_empty() and origin is not None:
                    self.doc.delete_text_block(index, origin)
                else:
                    self.doc.commit_text(index, editable, erase_rect=origin)
            except Exception as exc:
                self.status_message.emit(f"Could not apply the edit: {exc}")
        self.edit_state_changed.emit()
        self.update()

    def cancel_edit(self):
        self.edit = None
        self.edit_page = None
        self.edit_origin_rect = None
        self._caret_timer.stop()
        self.edit_state_changed.emit()
        self.update()

    def _blink(self):
        self._caret_on = not self._caret_on
        if self.edit is not None:
            self.update()

    def _sample_background(self, index: int, rect: fitz.Rect) -> QColor:
        """Guess the paper colour just outside a text block."""
        pix = self.pixmap_for(index)
        if pix is None:
            return QColor(255, 255, 255)
        image = pix.toImage()
        dpr = pix.devicePixelRatio() or 1.0
        box = fitz.Rect(rect) * self.doc.display_matrix(index, self.zoom)
        box.normalize()
        counts: dict[int, int] = {}
        samples = [
            (box.x0 - 3, box.y0 - 3), (box.x1 + 3, box.y0 - 3),
            (box.x0 - 3, box.y1 + 3), (box.x1 + 3, box.y1 + 3),
            (box.x0 - 3, (box.y0 + box.y1) / 2), (box.x1 + 3, (box.y0 + box.y1) / 2),
            ((box.x0 + box.x1) / 2, box.y0 - 3), ((box.x0 + box.x1) / 2, box.y1 + 3),
        ]
        for sx, sy in samples:
            px, py = int(sx * dpr), int(sy * dpr)
            if 0 <= px < image.width() and 0 <= py < image.height():
                rgb = image.pixel(px, py)
                counts[rgb] = counts.get(rgb, 0) + 1
        if not counts:
            return QColor(255, 255, 255)
        return QColor(max(counts.items(), key=lambda kv: kv[1])[0])

    def edit_handles(self) -> dict:
        """Move bar and resize grip for the block being edited (canvas coords)."""
        if self.edit is None:
            return {}
        bounds = self.edit.bounds()
        box = self.rect_to_canvas(self.edit_page, bounds)
        pad = 5
        outer = box.adjusted(-pad, -pad, pad, pad)
        return {
            "outer": outer,
            "move": QRectF(outer.left(), outer.top() - 15, outer.width(), 15),
            "resize": QRectF(outer.right() - HANDLE, outer.center().y() - HANDLE,
                             HANDLE * 2, HANDLE * 2),
        }

    # ------------------------------------------------- annotation selection

    def select_annot_at(self, index: int, point: fitz.Point) -> bool:
        hit = self.doc.annot_at(index, point)
        if hit is None:
            return False
        self.sel_annot = (index, hit[0])
        self.sel_rect = fitz.Rect(hit[1])
        self.selection_changed.emit()
        self.update()
        return True

    def clear_annot_selection(self):
        if self.sel_annot is not None:
            self.sel_annot = None
            self.sel_rect = None
            self.selection_changed.emit()
            self.update()

    def annot_handles(self) -> dict:
        if self.sel_annot is None or self.sel_rect is None:
            return {}
        index = self.sel_annot[0]
        box = self.rect_to_canvas(index, self.sel_rect)
        h = HANDLE
        return {
            "nw": QRectF(box.left() - h, box.top() - h, h * 2, h * 2),
            "ne": QRectF(box.right() - h, box.top() - h, h * 2, h * 2),
            "sw": QRectF(box.left() - h, box.bottom() - h, h * 2, h * 2),
            "se": QRectF(box.right() - h, box.bottom() - h, h * 2, h * 2),
        }

    # ------------------------------------------------------ text selection

    def clear_text_selection(self):
        if self.text_sel:
            self.text_sel = []
            self.update()

    def selected_document_text(self) -> str:
        if not self.text_sel:
            return ""
        parts = []
        for index, rect in self.text_sel:
            try:
                parts.append(self.doc.page(index).get_textbox(rect))
            except Exception:
                pass
        return "\n".join(p for p in parts if p.strip())

    def _update_text_selection(self, index: int, start: fitz.Point, end: fitz.Point):
        try:
            page = self.doc.page(index)
            rects = page.get_text("words")
        except Exception:
            return
        box = fitz.Rect(min(start.x, end.x), min(start.y, end.y),
                        max(start.x, end.x), max(start.y, end.y))
        # Treat the drag as a reading-order sweep, not a rectangle.
        ordered = sorted(rects, key=lambda w: (round(w[3], 1), w[0]))
        first = last = None
        for i, word in enumerate(ordered):
            wr = fitz.Rect(word[:4])
            if wr.intersects(box):
                if first is None:
                    first = i
                last = i
        self.text_sel = []
        if first is None:
            return
        for word in ordered[first:last + 1]:
            self.text_sel.append((index, fitz.Rect(word[:4])))
        self.update()

    # ---------------------------------------------------------- form fields

    def begin_field(self, index: int, field) -> bool:
        """Start editing a form field, or toggle it if it is a tick box."""
        from .doc_features import (FIELD_CHECKBOX, FIELD_CHOICE, FIELD_RADIO,
                                   FIELD_TEXT)
        if field.read_only:
            self.status_message.emit(f"'{field.label}' is read-only")
            return False
        if field.kind in (FIELD_CHECKBOX, FIELD_RADIO):
            self.commit_field()
            self.doc.set_field_value(index, field.name, not field.checked)
            self.invalidate_cache(index)
            self.status_message.emit(
                f"{field.label}: {'ticked' if not field.checked else 'cleared'}")
            return True
        if field.kind == FIELD_CHOICE:
            self.host.choose_field_option(index, field)
            return True
        if field.kind != FIELD_TEXT:
            return False
        self.commit_field()
        self.active_field = (index, field)
        self._field_buffer = str(field.value or "")
        self._caret_on = True
        self._caret_timer.start()
        self.edit_state_changed.emit()
        self.update()
        return True

    def commit_field(self):
        if self.active_field is None:
            return
        index, field = self.active_field
        buffer = self._field_buffer
        self.active_field = None
        self._field_buffer = ""
        self._caret_timer.stop()
        if buffer != str(field.value or ""):
            self.doc.set_field_value(index, field.name, buffer)
            self.invalidate_cache(index)
        self.edit_state_changed.emit()
        self.update()

    def cancel_field(self):
        self.active_field = None
        self._field_buffer = ""
        self._caret_timer.stop()
        self.update()

    def _handle_field_key(self, event: QKeyEvent) -> bool:
        index, field = self.active_field
        key = event.key()
        self._caret_on = True
        if key == Qt.Key_Escape:
            self.cancel_field()
        elif key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
            self.commit_field()
            if key == Qt.Key_Tab:
                self.focus_next_field(index, field)
        elif key == Qt.Key_Backspace:
            self._field_buffer = self._field_buffer[:-1]
        elif event.modifiers() & Qt.ControlModifier and key == Qt.Key_V:
            self._field_buffer += QApplication.clipboard().text().replace("\n", " ")
        elif event.text() and event.text().isprintable():
            if not field.max_len or len(self._field_buffer) < field.max_len:
                self._field_buffer += event.text()
        else:
            return False
        self.update()
        return True

    def focus_next_field(self, index: int, field):
        fields = [f for f in self.doc.form_fields() if not f.read_only]
        order = sorted(fields, key=lambda f: (f.page, round(f.rect.y0, 1), f.rect.x0))
        for i, candidate in enumerate(order):
            if candidate.name == field.name and candidate.page == index:
                nxt = order[(i + 1) % len(order)]
                self.scroll_to_page(nxt.page)
                self.begin_field(nxt.page, nxt)
                self.ensure_visible_rect(nxt.page, nxt.rect)
                return

    # --------------------------------------------------------- mouse events

    def mousePressEvent(self, event):
        self.setFocus()
        pos = event.position().toPoint()
        if event.button() == Qt.MiddleButton or self._space_pan:
            self._start_pan(pos)
            return
        if event.button() != Qt.LeftButton or not self.doc.is_open():
            return

        index, page_pt = self.page_at(pos)
        if index is None:
            return
        self._press_pos = self._drag_pos = pos
        self._press_page = index

        # 1. interacting with the block currently being edited
        if self.edit is not None and index == self.edit_page:
            handles = self.edit_handles()
            if handles:
                if handles["resize"].contains(QPointF(pos)):
                    self._mode = "resize_block"
                    return
                if handles["move"].contains(QPointF(pos)):
                    self._mode = "blockmove"
                    self._block_ref = (self.edit.x, self.edit.y)
                    return
                if handles["outer"].contains(QPointF(pos)):
                    self._mode = "caret"
                    if event.type() == event.Type.MouseButtonDblClick:
                        self.edit.select_word_at(self.edit.hit_test(page_pt))
                    else:
                        self.edit.set_caret(self.edit.hit_test(page_pt),
                                            extend=bool(event.modifiers() & Qt.ShiftModifier))
                    self._caret_on = True
                    self.update()
                    return
            self.commit_edit()

        # 2. a form field always wins a plain click — filling a form should
        #    never require hunting for the right tool first
        if self.tool in (Tool.SELECT, Tool.EDIT_TEXT, Tool.TEXT_SELECT):
            field = self.doc.field_at(index, page_pt) if self.doc.has_form else None
            if field is not None:
                if self.active_field and self.active_field[1].name == field.name:
                    return
                self.begin_field(index, field)
                return
        if self.active_field is not None:
            self.commit_field()

        # 3. tool-specific behaviour
        if self.tool == Tool.STAMP:
            self.host.commit_stamp(index, page_pt)
            return

        if self.tool == Tool.EDIT_TEXT:
            if self.begin_edit(index, page_pt):
                self._mode = "caret"
            else:
                self.status_message.emit("No editable text there — drag with the Text tool to add some")
            return

        if self.tool == Tool.SELECT:
            handles = self.annot_handles()
            for name, rect in handles.items():
                if rect.contains(QPointF(pos)):
                    self._mode = "resize"
                    self._handle = name
                    self._orig_rect = fitz.Rect(self.sel_rect)
                    return
            if self.select_annot_at(index, page_pt):
                self._mode = "move"
                self._orig_rect = fitz.Rect(self.sel_rect)
                return
            self.clear_annot_selection()
            link = self.doc.link_at(index, page_pt)
            if link is not None and self.host.follow_link(index, link):
                return
            block = self.doc.editable_at(index, page_pt)
            if block is not None:
                # Clicking text with the arrow tool jumps straight into editing.
                if self.begin_edit(index, page_pt):
                    self._mode = "caret"
                    return
            self._start_pan(pos)
            return

        if self.tool == Tool.TEXT_SELECT:
            self._mode = "textsel"
            self._text_sel_start = (index, page_pt)
            return

        if self.tool in TEXT_MARKUP_TOOLS:
            self._mode = "textsel"
            self._text_sel_start = (index, page_pt)
            return

        if self.tool == Tool.INK:
            self._mode = "ink"
            self._ink = [pos]
            return

        if self.tool in LINE_TOOLS:
            self._mode = "line"
            return

        if self.tool == Tool.NOTE:
            self.host.commit_click(Tool.NOTE, index, page_pt)
            return

        if self.tool in MARQUEE_TOOLS:
            self._mode = "marquee"
            return

    def mouseDoubleClickEvent(self, event):
        pos = event.position().toPoint()
        index, page_pt = self.page_at(pos)
        if index is None or not self.doc.is_open():
            return
        if self.edit is not None and index == self.edit_page:
            self.edit.select_word_at(self.edit.hit_test(page_pt))
            self.update()
            return
        if self.tool in (Tool.SELECT, Tool.EDIT_TEXT, Tool.TEXT_SELECT):
            if self.begin_edit(index, page_pt):
                self.edit.select_word_at(self.edit.hit_test(page_pt))
                self._mode = "caret"
                self.update()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self._panning:
            delta = pos - self._press_pos
            area = self._scroll_area()
            if area is not None:
                area.horizontalScrollBar().setValue(self._pan_origin[0] - delta.x())
                area.verticalScrollBar().setValue(self._pan_origin[1] - delta.y())
            return

        if self._mode is None:
            self._update_hover(pos)
            return

        self._drag_pos = pos
        index = self._press_page
        page_pt = self.to_page(index, pos)

        if self._mode == "caret" and self.edit is not None:
            self.edit.set_caret(self.edit.hit_test(page_pt), extend=True)
            self._caret_on = True
        elif self._mode == "blockmove" and self.edit is not None:
            start = self.to_page(index, self._press_pos)
            dx, dy = page_pt.x - start.x, page_pt.y - start.y
            self.edit.x = self._block_ref[0] + dx
            self.edit.y = self._block_ref[1] + dy
            base = getattr(self.edit, "_base_baselines", None)
            if base is None:
                self.edit._base_baselines = (
                    self.edit.first_baseline,
                    list(getattr(self.edit, "source_baselines", []) or []))
                base = self.edit._base_baselines
            if base[0] is not None:
                self.edit.first_baseline = base[0] + dy
            if base[1]:
                self.edit.source_baselines = [b + dy for b in base[1]]
            self.edit._moved = True
            self.edit.invalidate()
        elif self._mode == "resize_block" and self.edit is not None:
            self.edit.set_wrap_width(page_pt.x - self.edit.x)
        elif self._mode == "move" and self.sel_rect is not None:
            start = self.to_page(index, self._press_pos)
            self.sel_rect = fitz.Rect(self._orig_rect) + (
                page_pt.x - start.x, page_pt.y - start.y,
                page_pt.x - start.x, page_pt.y - start.y)
        elif self._mode == "resize" and self.sel_rect is not None:
            rect = fitz.Rect(self._orig_rect)
            if self._handle in ("nw", "sw"):
                rect.x0 = min(page_pt.x, rect.x1 - 6)
            else:
                rect.x1 = max(page_pt.x, rect.x0 + 6)
            if self._handle in ("nw", "ne"):
                rect.y0 = min(page_pt.y, rect.y1 - 6)
            else:
                rect.y1 = max(page_pt.y, rect.y0 + 6)
            self.sel_rect = rect
        elif self._mode == "ink":
            self._ink.append(pos)
        elif self._mode == "textsel" and self._text_sel_start:
            self._update_text_selection(self._text_sel_start[0],
                                        self._text_sel_start[1], page_pt)
        self.update()

    def mouseReleaseEvent(self, event):
        if self._panning:
            self._panning = False
            self.setCursor(CURSORS.get(self.tool, Qt.CrossCursor))
            self._mode = None
            return
        if event.button() != Qt.LeftButton or self._mode is None:
            return

        pos = event.position().toPoint()
        index = self._press_page
        mode = self._mode
        start_pt = self.to_page(index, self._press_pos) if self._press_pos else None
        end_pt = self.to_page(index, pos)
        travel = (pos - self._press_pos).manhattanLength() if self._press_pos else 0
        self._mode = None
        self._handle = None

        if mode == "move" and self.sel_annot and travel > 2:
            start = self.to_page(index, self._press_pos)
            self.doc.move_annot(index, self.sel_annot[1],
                                end_pt.x - start.x, end_pt.y - start.y)
            self.sel_rect = self.doc.annot_rect(index, self.sel_annot[1])
        elif mode == "resize" and self.sel_annot and travel > 2:
            self.doc.resize_annot(index, self.sel_annot[1], self.sel_rect)
            self.sel_rect = self.doc.annot_rect(index, self.sel_annot[1])
        elif mode == "ink":
            points = [self.to_page(index, p) for p in self._ink]
            self._ink = []
            if len(points) > 1:
                self.host.commit_ink(index, [(p.x, p.y) for p in points])
        elif mode == "line" and travel > 3:
            self.host.commit_line(self.tool, index, start_pt, end_pt)
        elif mode == "marquee":
            rect = fitz.Rect(min(start_pt.x, end_pt.x), min(start_pt.y, end_pt.y),
                             max(start_pt.x, end_pt.x), max(start_pt.y, end_pt.y))
            if self.tool == Tool.TEXT:
                if rect.width < 10:
                    rect = fitz.Rect(rect.x0, rect.y0, rect.x0 + 300,
                                     rect.y0 + self.font_size * 1.4)
                self.begin_new_text(index, rect)
            elif self.tool == Tool.SNAPSHOT and travel > 4:
                self.take_snapshot(index, rect)
            elif travel > 4:
                self.host.commit_marquee(self.tool, index, rect)
            elif self.tool == Tool.IMAGE:
                self.host.commit_marquee(self.tool, index,
                                         fitz.Rect(rect.x0, rect.y0,
                                                   rect.x0 + 240, rect.y0 + 180))
        elif mode == "textsel":
            if self.tool in TEXT_MARKUP_TOOLS and self.text_sel:
                rects = [r for _, r in self.text_sel]
                self.host.commit_markup(self.tool, index, rects)
                self.clear_text_selection()
        self.update()

    def take_snapshot(self, index: int, rect: fitz.Rect, zoom: float = 3.0) -> QImage:
        """Copy a region of the page to the clipboard as a crisp image.

        Rendered fresh at high resolution rather than lifted off the screen
        pixmap, so the copy is sharp no matter the current zoom.
        """
        try:
            page = self.doc.page(index)
            clip = fitz.Rect(rect) & page.rect
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
        except Exception as exc:
            self.status_message.emit(f"Could not copy that region: {exc}")
            return QImage()
        image = QImage(pix.samples, pix.width, pix.height, pix.stride,
                       QImage.Format_RGB888).copy()
        QGuiApplication.clipboard().setImage(image)
        self.status_message.emit(
            f"Copied a {pix.width}×{pix.height} image to the clipboard")
        return image

    def _start_pan(self, pos: QPoint):
        area = self._scroll_area()
        self._panning = True
        self._press_pos = pos
        if area is not None:
            self._pan_origin = (area.horizontalScrollBar().value(),
                                area.verticalScrollBar().value())
        self.setCursor(Qt.ClosedHandCursor)

    def _update_hover(self, pos: QPoint):
        """Outline the text block under the pointer in the editing tools."""
        if self.tool not in (Tool.EDIT_TEXT, Tool.SELECT) or not self.doc.is_open():
            if self._hover_block:
                self._hover_block = None
                self.update()
            return
        index, page_pt = self.page_at(pos)
        found = None
        if index is not None:
            for rect, _ in self.doc.editable_blocks(index):
                if (rect + (-2, -2, 2, 2)).contains(page_pt):
                    found = (index, rect)
                    break
        if found != self._hover_block:
            self._hover_block = found
            self.update()
        if self.tool == Tool.SELECT:
            self.setCursor(Qt.IBeamCursor if found else Qt.ArrowCursor)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            steps = event.angleDelta().y() / 120.0
            anchor = event.position().toPoint()
            factor = 1.15 ** steps
            self.set_zoom(self.zoom * factor, fit_mode=None, anchor=anchor)
            event.accept()
        else:
            event.ignore()

    # ------------------------------------------------------ keyboard events

    def keyPressEvent(self, event: QKeyEvent):
        if self.active_field is not None and self._handle_field_key(event):
            return
        if (event.key() == Qt.Key_Space and not event.isAutoRepeat()
                and self.edit is None and self.active_field is None):
            self._space_pan = True
            self.setCursor(Qt.OpenHandCursor)
            return
        if self.edit is not None and self._handle_edit_key(event):
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_pan = False
            self.setCursor(CURSORS.get(self.tool, Qt.CrossCursor))
        super().keyReleaseEvent(event)

    def _handle_edit_key(self, event: QKeyEvent) -> bool:
        editable = self.edit
        key = event.key()
        mods = event.modifiers()
        shift = bool(mods & Qt.ShiftModifier)
        ctrl = bool(mods & Qt.ControlModifier)
        self._caret_on = True

        if key == Qt.Key_Escape:
            self.commit_edit()
            return True
        if key in (Qt.Key_Left, Qt.Key_Right):
            editable.move_horizontal(1 if key == Qt.Key_Right else -1, shift, ctrl)
        elif key in (Qt.Key_Up, Qt.Key_Down):
            editable.move_vertical(1 if key == Qt.Key_Down else -1, shift)
        elif key == Qt.Key_Home:
            if ctrl:
                editable.move_document_edge(False, shift)
            else:
                editable.move_line_edge(False, shift)
        elif key == Qt.Key_End:
            if ctrl:
                editable.move_document_edge(True, shift)
            else:
                editable.move_line_edge(True, shift)
        elif key == Qt.Key_Backspace:
            editable.backspace()
        elif key == Qt.Key_Delete:
            editable.delete_forward()
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            editable.insert("\n")
        elif key == Qt.Key_Tab:
            editable.insert("    ")
        elif ctrl and key == Qt.Key_A:
            editable.select_all()
        elif ctrl and key == Qt.Key_C:
            QApplication.clipboard().setText(editable.selected_text())
        elif ctrl and key == Qt.Key_X:
            QApplication.clipboard().setText(editable.selected_text())
            editable.delete_selection()
        elif ctrl and key == Qt.Key_V:
            text = QApplication.clipboard().text()
            if text:
                editable.insert(text.replace("\r\n", "\n").replace("\r", "\n"))
        elif ctrl and key == Qt.Key_B:
            self.toggle_edit_style("bold")
        elif ctrl and key == Qt.Key_I:
            self.toggle_edit_style("italic")
        elif event.text() and event.text().isprintable():
            editable.insert(event.text())
        else:
            return False
        self.edit_state_changed.emit()
        if editable is self.edit:
            self.ensure_visible_rect(self.edit_page, editable.caret_rect(), margin=60)
        self.update()
        return True

    def toggle_edit_style(self, which: str):
        if self.edit is None:
            return
        style = self.edit.pending_style
        span = self.edit.selection_range()
        if span:
            style = self.edit.style_at(span[0])
        font = style.font
        current = font.bold if which == "bold" else font.italic
        self.edit.apply_style(**{which: not current, "resolver": self.doc.fonts})
        self.edit_state_changed.emit()
        self.update()

    def apply_edit_style(self, **changes):
        if self.edit is None:
            return
        changes.setdefault("resolver", self.doc.fonts)
        self.edit.apply_style(**changes)
        self.edit_state_changed.emit()
        self.update()

    # -------------------------------------------------------------- painting

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor(theme.CANVAS))
        if not self.doc.is_open():
            painter.setPen(QColor(theme.TEXT_DIM))
            font = QFont()
            font.setPointSize(13)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "No document open\n\nCtrl+O to open a PDF, or drag one here")
            painter.end()
            return

        painter.setRenderHint(QPainter.Antialiasing)
        view = event.rect()
        for slot in self.slots:
            box = QRectF(slot.left, slot.top, slot.width, slot.height)
            if not box.intersects(QRectF(view).adjusted(-2, -PAGE_GAP, 2, PAGE_GAP)):
                continue
            painter.fillRect(box.adjusted(3, 3, 3, 3), theme.PAGE_SHADOW)
            pix = self.pixmap_for(slot.index)
            if pix is not None:
                painter.drawPixmap(box.topLeft(), pix)
            else:
                painter.fillRect(box, QColor("#ffffff"))
            painter.setPen(QPen(QColor(0, 0, 0, 90), 1))
            painter.drawRect(box)
            self._paint_overlays(painter, slot)

        self._paint_live_gesture(painter)
        painter.end()

    def _paint_overlays(self, painter: QPainter, slot: PageSlot):
        index = slot.index

        # search hits
        for i, rect in enumerate(self.search_hits.get(index, [])):
            box = self.rect_to_canvas(index, rect)
            current = self.search_current == (index, i)
            painter.fillRect(box, theme.SEARCH_CURRENT if current else theme.SEARCH_HIT)
            if current:
                painter.setPen(QPen(QColor(200, 110, 0), 1.5))
                painter.drawRect(box)

        # document text selection
        for pno, rect in self.text_sel:
            if pno == index:
                painter.fillRect(self.rect_to_canvas(index, rect), theme.TEXT_SEL)

        # hovered text block
        if self._hover_block and self._hover_block[0] == index and self.edit is None:
            painter.setPen(QPen(theme.BLOCK_HOVER, 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.rect_to_canvas(index, self._hover_block[1])
                             .adjusted(-3, -3, 3, 3))

        # selected annotation + handles
        if self.sel_annot and self.sel_annot[0] == index and self.sel_rect is not None:
            box = self.rect_to_canvas(index, self.sel_rect)
            painter.setPen(QPen(theme.BLOCK_OUTLINE, 1.6, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(box)
            painter.setPen(QPen(theme.HANDLE_EDGE, 1.4))
            painter.setBrush(theme.HANDLE_FILL)
            for rect in self.annot_handles().values():
                painter.drawRect(rect)

        # form fields: outline them so a fillable PDF announces itself
        if self.doc.has_form and self.tool in (Tool.SELECT, Tool.EDIT_TEXT,
                                               Tool.TEXT_SELECT):
            self._paint_fields(painter, index)

        # the block being edited
        if self.edit is not None and self.edit_page == index:
            self._paint_edit(painter)

    def _paint_fields(self, painter: QPainter, index: int):
        """Tint fillable fields, and draw the one being typed into."""
        active_name = (self.active_field[1].name
                       if self.active_field and self.active_field[0] == index else None)
        for field in self.doc.form_fields(index):
            box = self.rect_to_canvas(index, field.rect)
            if field.name == active_name:
                painter.fillRect(box, QColor(255, 255, 255))
                painter.setPen(QPen(theme.CARET_COLOR, 1.6))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(box)
                font = QFont("DejaVu Sans")
                font.setPixelSize(max(8, int(min(box.height() * 0.62, 11 * self.zoom))))
                painter.setFont(font)
                painter.setPen(QColor(10, 10, 10))
                metrics = QFontMetricsF(font)
                text = self._field_buffer
                inner = box.adjusted(4, 0, -4, 0)
                while text and metrics.horizontalAdvance(text) > inner.width():
                    text = text[1:]
                baseline = box.center().y() + metrics.ascent() / 2 - 1
                painter.drawText(QPointF(inner.left(), baseline), text)
                if self._caret_on:
                    cx = inner.left() + metrics.horizontalAdvance(text)
                    painter.setPen(QPen(theme.CARET_COLOR, 1.6))
                    painter.drawLine(QPointF(cx, box.top() + 3),
                                     QPointF(cx, box.bottom() - 3))
            else:
                painter.setPen(QPen(QColor(90, 150, 235, 170), 1))
                painter.setBrush(QColor(90, 150, 235, 38))
                painter.drawRect(box)
                if field.read_only:
                    painter.setBrush(QColor(140, 140, 140, 30))
                    painter.drawRect(box)

    def _paint_edit(self, painter: QPainter):
        editable = self.edit
        index = self.edit_page

        # cover the original glyphs so live text does not double-print
        if self.edit_origin_rect is not None and self.edit_bg.alpha():
            cover = self.rect_to_canvas(index, self.edit_origin_rect)
            painter.fillRect(cover.adjusted(-1.5, -1.5, 1.5, 1.5), self.edit_bg)

        # selection behind the text
        for rect in editable.selection_rects():
            painter.fillRect(self.rect_to_canvas(index, rect), theme.TEXT_SEL)

        # live text in the document's own typeface
        for run in editable.draw_runs():
            style = run.style
            font = QFont(style.font.qt_family() if style.font else "Sans")
            font.setPixelSize(max(1, int(round(style.size * self.zoom))))
            font.setBold(bool(style.font and style.font.bold))
            font.setItalic(bool(style.font and style.font.italic))
            painter.setFont(font)
            colour = QColor.fromRgbF(*style.color) if style.color else QColor("black")
            painter.setPen(colour)
            origin = self.to_canvas(index, fitz.Point(run.x, run.baseline))
            painter.drawText(origin, run.text)

        handles = self.edit_handles()
        if handles:
            painter.setPen(QPen(theme.BLOCK_OUTLINE, 1.4, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(handles["outer"])
            # move bar
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(76, 141, 255, 200))
            bar = handles["move"]
            painter.drawRoundedRect(bar, 3, 3)
            painter.setPen(QColor(255, 255, 255, 230))
            small = QFont()
            small.setPixelSize(10)
            painter.setFont(small)
            painter.drawText(bar, Qt.AlignCenter, "drag to move")
            # resize grip
            painter.setPen(QPen(theme.HANDLE_EDGE, 1.4))
            painter.setBrush(theme.HANDLE_FILL)
            painter.drawEllipse(handles["resize"])

        # caret
        if self._caret_on:
            box = self.rect_to_canvas(index, editable.caret_rect())
            painter.setPen(QPen(theme.CARET_COLOR, 1.8))
            painter.drawLine(box.topLeft(), QPointF(box.left(), box.bottom()))

    def _paint_live_gesture(self, painter: QPainter):
        if self._mode not in ("marquee", "line", "ink") or self._press_pos is None:
            return
        band = QRectF(QPointF(self._press_pos), QPointF(self._drag_pos)).normalized()
        pen = QPen(self.color, max(1.0, self.stroke_width * self.zoom))
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        if self._mode == "ink" and len(self._ink) > 1:
            painter.drawPolyline(QPolygon(self._ink))
        elif self._mode == "line":
            painter.drawLine(QPointF(self._press_pos), QPointF(self._drag_pos))
            if self.tool == Tool.ARROW:
                self._draw_arrow_head(painter, QPointF(self._press_pos),
                                      QPointF(self._drag_pos))
        elif self.tool == Tool.ELLIPSE:
            painter.drawEllipse(band)
        elif self.tool == Tool.WHITEOUT:
            painter.fillRect(band, QColor(255, 255, 255, 210))
            painter.setPen(QPen(QColor(150, 150, 150), 1, Qt.DashLine))
            painter.drawRect(band)
        elif self.tool == Tool.REDACT:
            painter.fillRect(band, QColor(15, 15, 15, 210))
        elif self.tool == Tool.TEXT:
            painter.setPen(QPen(theme.BLOCK_OUTLINE, 1.4, Qt.DashLine))
            painter.drawRect(band)
        else:
            painter.drawRect(band)

    @staticmethod
    def _draw_arrow_head(painter, start: QPointF, end: QPointF):
        import math
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        size = 12.0
        for offset in (2.6, -2.6):
            painter.drawLine(end, QPointF(end.x() - size * math.cos(angle + offset / 3),
                                          end.y() - size * math.sin(angle + offset / 3)))
