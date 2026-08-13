"""The central page widget: renders the current page and drives the edit tools.

The view holds two matrices supplied by the main window each render:
  fwd  — unrotated page coords -> logical view pixels
  inv  — logical view pixels   -> unrotated page coords
All commits back into the document are made in page coordinates.
"""

from __future__ import annotations

import fitz
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygon
from PySide6.QtWidgets import QWidget


class Tool:
    SELECT = "select"
    TEXT = "text"
    EDIT_TEXT = "edittext"
    HIGHLIGHT = "highlight"
    RECT = "rect"
    ELLIPSE = "ellipse"
    LINE = "line"
    ARROW = "arrow"
    INK = "ink"
    WHITEOUT = "whiteout"
    REDACT = "redact"
    IMAGE = "image"
    NOTE = "note"


RUBBER_TOOLS = {Tool.TEXT, Tool.HIGHLIGHT, Tool.RECT, Tool.ELLIPSE,
                Tool.WHITEOUT, Tool.REDACT, Tool.IMAGE}
LINE_TOOLS = {Tool.LINE, Tool.ARROW}
CLICK_TOOLS = {Tool.NOTE, Tool.EDIT_TEXT}

TOOL_CURSORS = {
    Tool.SELECT: Qt.ArrowCursor,
    Tool.EDIT_TEXT: Qt.IBeamCursor,
    Tool.NOTE: Qt.PointingHandCursor,
}

TOOL_HINTS = {
    Tool.SELECT: "Click an annotation to select it (Del deletes it) — drag empty space to pan",
    Tool.TEXT: "Drag a box (or click) to place text",
    Tool.EDIT_TEXT: "Click on existing text to edit it",
    Tool.HIGHLIGHT: "Drag over text to highlight it",
    Tool.RECT: "Drag to draw a rectangle",
    Tool.ELLIPSE: "Drag to draw an ellipse",
    Tool.LINE: "Drag to draw a line",
    Tool.ARROW: "Drag to draw an arrow",
    Tool.INK: "Draw freehand with the mouse",
    Tool.WHITEOUT: "Drag to white-out an area (removes the content underneath)",
    Tool.REDACT: "Drag to redact an area (permanently removes content, fills black)",
    Tool.IMAGE: "Drag a box (or click) to place an image",
    Tool.NOTE: "Click to place a sticky note",
}


class PageView(QWidget):
    """host must provide:
        commit_rubber(tool, fitz.Rect), commit_line(tool, p1, p2),
        commit_ink(points), commit_click(tool, fitz.Point),
        select_annot_at(fitz.Point) -> bool, clear_selection(),
        begin_pan(), pan_move(dx, dy), zoom_steps(steps)
    """

    def __init__(self, host):
        super().__init__()
        self.host = host
        self._pixmap: QPixmap | None = None
        self._fwd: fitz.Matrix | None = None
        self._inv: fitz.Matrix | None = None
        self.tool = Tool.SELECT
        self.color = QColor(200, 40, 40)

        self._pressed = False
        self._panning = False
        self._start = QPoint()
        self._current = QPoint()
        self._ink_points: list[QPoint] = []
        self._ink_points_cache: list[QPoint] = []
        self._selection: QRect | None = None
        self._search_rects: list[QRect] = []

        self.setMouseTracking(False)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)

    # ------------------------------------------------------------- state

    def set_content(self, pixmap: QPixmap | None, fwd=None, inv=None):
        self._pixmap = pixmap
        self._fwd, self._inv = fwd, inv
        self._selection = None
        if pixmap is not None:
            dpr = pixmap.devicePixelRatio() or 1.0
            self.setFixedSize(int(pixmap.width() / dpr), int(pixmap.height() / dpr))
        else:
            self.setFixedSize(200, 200)
        self.update()

    def set_tool(self, tool: str):
        self.tool = tool
        self.setCursor(TOOL_CURSORS.get(tool, Qt.CrossCursor))
        self._reset_gesture()
        self.update()

    def set_selection(self, rect: QRect | None):
        self._selection = rect
        self.update()

    def set_search_rects(self, rects: list[QRect]):
        self._search_rects = rects
        self.update()

    # -------------------------------------------------------- coordinates

    def to_page_point(self, pos: QPoint) -> fitz.Point:
        return fitz.Point(pos.x(), pos.y()) * self._inv

    def to_page_rect(self, view_rect: QRect) -> fitz.Rect:
        p1 = self.to_page_point(view_rect.topLeft())
        p2 = self.to_page_point(view_rect.bottomRight())
        rect = fitz.Rect(min(p1.x, p2.x), min(p1.y, p2.y),
                         max(p1.x, p2.x), max(p1.y, p2.y))
        return rect

    def from_page_rect(self, rect: fitz.Rect) -> QRect:
        transformed = fitz.Rect(rect) * self._fwd
        transformed.normalize()
        return QRect(int(transformed.x0), int(transformed.y0),
                     max(1, int(transformed.width)), max(1, int(transformed.height)))

    # ------------------------------------------------------------- events

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self._pixmap is None:
            return
        pos = event.position().toPoint()
        self._start = self._current = pos
        if self.tool == Tool.SELECT:
            if not self.host.select_annot_at(self.to_page_point(pos)):
                self.host.clear_selection()
                self._panning = True
                self.host.begin_pan()
                self.setCursor(Qt.ClosedHandCursor)
            return
        self._pressed = True
        if self.tool == Tool.INK:
            self._ink_points = [pos]
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self._panning:
            delta = pos - self._start
            self.host.pan_move(delta.x(), delta.y())
            return
        if not self._pressed:
            return
        self._current = pos
        if self.tool == Tool.INK:
            self._ink_points.append(pos)
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self._panning:
            self._panning = False
            self.setCursor(TOOL_CURSORS.get(self.tool, Qt.CrossCursor))
            return
        if not self._pressed:
            return
        self._pressed = False
        pos = event.position().toPoint()
        start, tool = self._start, self.tool
        drag = (pos - start).manhattanLength()
        self._reset_gesture()
        self.update()

        if tool in CLICK_TOOLS:
            self.host.commit_click(tool, self.to_page_point(pos))
        elif tool in LINE_TOOLS:
            if drag >= 4:
                self.host.commit_line(tool, self.to_page_point(start),
                                      self.to_page_point(pos))
        elif tool == Tool.INK:
            points = [self.to_page_point(p) for p in self._ink_points_cache]
            self.host.commit_ink([(p.x, p.y) for p in points])
        elif tool in RUBBER_TOOLS:
            if drag < 4 and tool in (Tool.TEXT, Tool.IMAGE):
                # Plain click: hand the host a degenerate rect, it applies a default size
                self.host.commit_rubber(tool, self.to_page_rect(QRect(pos, pos)))
            elif drag >= 4:
                self.host.commit_rubber(tool, self.to_page_rect(QRect(start, pos).normalized()))

    def _reset_gesture(self):
        self._ink_points_cache = list(self._ink_points)
        self._ink_points = []
        self._pressed = False

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            steps = event.angleDelta().y() / 120.0
            self.host.zoom_steps(steps)
            event.accept()
        else:
            event.ignore()

    # ------------------------------------------------------------ painting

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._pixmap is None:
            painter.fillRect(self.rect(), QColor(82, 86, 92))
            painter.end()
            return
        painter.drawPixmap(0, 0, self._pixmap)

        # search hits
        if self._search_rects:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 200, 0, 90))
            for rect in self._search_rects:
                painter.drawRect(rect)

        # selected annotation
        if self._selection:
            pen = QPen(QColor(30, 120, 255), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self._selection.adjusted(-2, -2, 2, 2))

        # live gesture preview
        if self._pressed:
            color = QColor(self.color)
            pen = QPen(color, 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            band = QRect(self._start, self._current).normalized()
            if self.tool == Tool.INK and len(self._ink_points) > 1:
                painter.drawPolyline(QPolygon(self._ink_points))
            elif self.tool in LINE_TOOLS:
                painter.drawLine(self._start, self._current)
            elif self.tool == Tool.HIGHLIGHT:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 214, 0, 110))
                painter.drawRect(band)
            elif self.tool == Tool.WHITEOUT:
                painter.setBrush(QColor(255, 255, 255, 200))
                painter.setPen(QPen(QColor(150, 150, 150), 1, Qt.DashLine))
                painter.drawRect(band)
            elif self.tool == Tool.REDACT:
                painter.setBrush(QColor(20, 20, 20, 200))
                painter.drawRect(band)
            elif self.tool == Tool.ELLIPSE:
                painter.drawEllipse(band)
            elif self.tool in RUBBER_TOOLS:
                painter.drawRect(band)
        painter.end()
