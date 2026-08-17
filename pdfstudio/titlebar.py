"""Custom window frame: title bar with integrated menus and window controls.

The OS frame is dropped (Qt.FramelessWindowHint) and rebuilt here, VS Code
style — app icon, the menu bar, the document title, then minimise /
maximise-restore / close drawn by hand. Losing the native frame also loses
dragging, edge resizing, double-click-maximise and snap, so each of those is
reimplemented:

  * dragging       — startSystemMove(), which keeps OS snap-to-edge working;
                     dragging a maximised window first restores it under the
                     cursor, the way native frames behave
  * edge resizing  — eight invisible grip widgets around the window calling
                     startSystemResize(), with a manual-geometry fallback for
                     platforms where that returns False
  * double-click   — toggles maximise, on the bar and on empty menu-bar space
  * right-click    — the usual Restore / Minimise / Maximise / Close menu

macOS keeps the native frame by default (custom decorations fight the
traffic-light conventions there); PDFSTUDIO_NATIVE_FRAME=1 forces the native
frame anywhere, as an escape hatch for window managers that dislike frameless.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel, QMenu,
                               QMenuBar, QSizePolicy, QWidget)

from . import theme
from .icons import app_icon

BAR_HEIGHT = 40
BUTTON_WIDTH = 46
DRAG_THRESHOLD = 4


def use_custom_frame() -> bool:
    env = os.environ.get("PDFSTUDIO_NATIVE_FRAME", "").strip().lower()
    if env in ("1", "true", "yes"):
        return False
    if env in ("0", "false", "no"):
        return True
    return sys.platform != "darwin"


class WindowButton(QAbstractButton):
    """Minimise / maximise-restore / close, drawn by hand.

    kind is "min", "max" or "close". The max button flips to the two-rectangle
    restore glyph while the window is maximised.
    """

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.restore_mode = False
        self._hover = False
        self.setFixedSize(BUTTON_WIDTH, BAR_HEIGHT)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip({"min": "Minimise", "max": "Maximise",
                         "close": "Close"}[kind])

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        glyph = QColor(theme.TEXT)
        if self.kind == "close":
            if self.isDown():
                painter.fillRect(self.rect(), QColor("#b50f1e"))
                glyph = QColor("white")
            elif self._hover:
                painter.fillRect(self.rect(), QColor("#e81123"))
                glyph = QColor("white")
        elif self.isDown():
            painter.fillRect(self.rect(), QColor(theme.BG_ACTIVE))
        elif self._hover:
            painter.fillRect(self.rect(), QColor(theme.BG_HOVER))

        pen = QPen(glyph)
        pen.setWidthF(1.2)
        painter.setPen(pen)
        cx, cy = self.width() / 2, self.height() / 2

        if self.kind == "min":
            painter.drawLine(QPoint(int(cx - 5), int(cy)),
                             QPoint(int(cx + 5), int(cy)))
        elif self.kind == "max":
            if self.restore_mode:
                # back rectangle peeking out behind the front one
                painter.drawRect(int(cx - 3), int(cy - 5), 8, 8)
                painter.fillRect(int(cx - 5) + 1, int(cy - 3) + 1, 7, 7,
                                 QColor(self.palette().window().color())
                                 if not (self._hover or self.isDown())
                                 else QColor(theme.BG_HOVER if not self.isDown()
                                             else theme.BG_ACTIVE))
                painter.drawRect(int(cx - 5), int(cy - 3), 8, 8)
            else:
                painter.drawRect(int(cx - 5), int(cy - 5), 10, 10)
        elif self.kind == "close":
            painter.setRenderHint(QPainter.Antialiasing)
            pen.setWidthF(1.4)
            painter.setPen(pen)
            painter.drawLine(QPoint(int(cx - 5), int(cy - 5)),
                             QPoint(int(cx + 5), int(cy + 5)))
            painter.drawLine(QPoint(int(cx - 5), int(cy + 5)),
                             QPoint(int(cx + 5), int(cy - 5)))
        painter.end()


class DragMenuBar(QMenuBar):
    """A menu bar whose empty space behaves like title bar: drag to move the
    window, double-click to maximise. Clicks on actual menus work as normal."""

    def __init__(self, bar: "TitleBar"):
        super().__init__()
        self._bar = bar
        self.setObjectName("titleMenuBar")
        self.setNativeMenuBar(False)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def _over_menu(self, pos) -> bool:
        return self.actionAt(pos) is not None

    def mousePressEvent(self, event):
        if (event.button() == Qt.LeftButton
                and not self._over_menu(event.position().toPoint())):
            self._bar.press_from_child(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._bar.maybe_system_move(event.globalPosition().toPoint(),
                                       event.buttons()):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if (event.button() == Qt.LeftButton
                and not self._over_menu(event.position().toPoint())):
            self._bar.toggle_max_restore()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class TitleBar(QWidget):
    """The bar itself: [icon] [menus] ... [title] ... [min][max][close]."""

    def __init__(self, window, menu_bar: QMenuBar):
        super().__init__(window)
        self._window = window
        self._press_global: QPoint | None = None
        self._full_title = ""
        self.setObjectName("titleBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(BAR_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(8)

        icon = QLabel()
        icon.setPixmap(app_icon().pixmap(QSize(18, 18)))
        icon.setFixedSize(20, 20)
        layout.addWidget(icon)

        layout.addWidget(menu_bar)

        layout.addStretch(1)
        self.title_label = QLabel("")
        self.title_label.setObjectName("titleTitle")
        self.title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label, 2)
        layout.addStretch(1)

        self.btn_min = WindowButton("min", self)
        self.btn_max = WindowButton("max", self)
        self.btn_close = WindowButton("close", self)
        self.btn_min.clicked.connect(window.showMinimized)
        self.btn_max.clicked.connect(self.toggle_max_restore)
        self.btn_close.clicked.connect(window.close)
        for button in (self.btn_min, self.btn_max, self.btn_close):
            layout.addWidget(button)

    # ------------------------------------------------------------------ title

    def refresh_title(self):
        raw = self._window.windowTitle()
        marker = " ●" if self._window.isWindowModified() else ""
        self._full_title = raw.replace("[*]", marker)
        self._elide()

    def _elide(self):
        metrics = self.title_label.fontMetrics()
        width = max(40, self.title_label.width() - 8)
        self.title_label.setText(metrics.elidedText(self._full_title,
                                                    Qt.ElideMiddle, width))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    # ------------------------------------------------------------- max state

    def sync_max(self):
        self.btn_max.restore_mode = (self._window.isMaximized()
                                     or self._window.isFullScreen())
        self.btn_max.setToolTip("Restore" if self.btn_max.restore_mode
                                else "Maximise")
        self.btn_max.update()

    def toggle_max_restore(self):
        if self._window.isFullScreen():
            self._window.showNormal()
        elif self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    # ------------------------------------------------------------------ drag

    def press_from_child(self, global_pos: QPoint):
        self._press_global = global_pos

    def maybe_system_move(self, global_pos: QPoint, buttons) -> bool:
        """Start an OS move once the press has travelled past the threshold."""
        if self._press_global is None or not (buttons & Qt.LeftButton):
            return False
        if (global_pos - self._press_global).manhattanLength() < DRAG_THRESHOLD:
            return False
        window = self._window
        if window.isMaximized():
            # Restore first, keeping the cursor at the same relative position,
            # so the window does not jump out from under the pointer.
            ratio = 0.5
            if self.width():
                local_x = self.mapFromGlobal(global_pos).x()
                ratio = min(max(local_x / self.width(), 0.05), 0.95)
            window.showNormal()
            window.move(global_pos.x() - int(window.width() * ratio),
                        max(0, global_pos.y() - BAR_HEIGHT // 2))
        self._press_global = None
        handle = window.windowHandle()
        if handle is not None:
            handle.startSystemMove()
        return True

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_global = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.maybe_system_move(event.globalPosition().toPoint(),
                                  event.buttons()):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_global = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_max_restore()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        restore = menu.addAction("Restore")
        restore.setEnabled(self._window.isMaximized() or self._window.isFullScreen())
        restore.triggered.connect(self._window.showNormal)
        menu.addAction("Minimise").triggered.connect(self._window.showMinimized)
        maximise = menu.addAction("Maximise")
        maximise.setEnabled(not self._window.isMaximized())
        maximise.triggered.connect(self._window.showMaximized)
        menu.addSeparator()
        close = menu.addAction("Close    Alt+F4")
        close.triggered.connect(self._window.close)
        menu.exec(event.globalPos())


# --------------------------------------------------------------- edge resize

EDGE_THICKNESS = 5
CORNER_SIZE = 10

_GRIP_SPECS = [
    (Qt.LeftEdge, Qt.SizeHorCursor),
    (Qt.RightEdge, Qt.SizeHorCursor),
    (Qt.TopEdge, Qt.SizeVerCursor),
    (Qt.BottomEdge, Qt.SizeVerCursor),
    (Qt.TopEdge | Qt.LeftEdge, Qt.SizeFDiagCursor),
    (Qt.BottomEdge | Qt.RightEdge, Qt.SizeFDiagCursor),
    (Qt.TopEdge | Qt.RightEdge, Qt.SizeBDiagCursor),
    (Qt.BottomEdge | Qt.LeftEdge, Qt.SizeBDiagCursor),
]


class ResizeGrip(QWidget):
    """An invisible strip along one window edge (or corner) that resizes the
    frameless window. Prefers the OS resize; falls back to moving the window
    geometry itself where startSystemResize is unsupported."""

    MIN_W, MIN_H = 520, 360

    def __init__(self, window, edges, cursor):
        super().__init__(window)
        self._window = window
        self.edges = edges
        self.setCursor(cursor)
        self.setStyleSheet("background: transparent;")
        self._manual_origin: QPoint | None = None
        self._manual_geometry: QRect | None = None

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        handle = self._window.windowHandle()
        started = False
        if handle is not None and not os.environ.get("PDFSTUDIO_FORCE_MANUAL_RESIZE"):
            try:
                started = bool(handle.startSystemResize(self.edges))
            except Exception:
                started = False
        if not started:
            self._manual_origin = event.globalPosition().toPoint()
            self._manual_geometry = QRect(self._window.geometry())

    def mouseMoveEvent(self, event):
        if self._manual_origin is None or self._manual_geometry is None:
            return
        delta = event.globalPosition().toPoint() - self._manual_origin
        rect = QRect(self._manual_geometry)
        if self.edges & Qt.LeftEdge:
            rect.setLeft(min(rect.left() + delta.x(), rect.right() - self.MIN_W))
        if self.edges & Qt.RightEdge:
            rect.setRight(max(rect.right() + delta.x(), rect.left() + self.MIN_W))
        if self.edges & Qt.TopEdge:
            rect.setTop(min(rect.top() + delta.y(), rect.bottom() - self.MIN_H))
        if self.edges & Qt.BottomEdge:
            rect.setBottom(max(rect.bottom() + delta.y(), rect.top() + self.MIN_H))
        self._window.setGeometry(rect)

    def mouseReleaseEvent(self, _event):
        self._manual_origin = None
        self._manual_geometry = None


def install_grips(window) -> list[ResizeGrip]:
    return [ResizeGrip(window, edges, cursor) for edges, cursor in _GRIP_SPECS]


def position_grips(window, grips: list[ResizeGrip]):
    w, h = window.width(), window.height()
    t, c = EDGE_THICKNESS, CORNER_SIZE
    boxes = {
        Qt.LeftEdge: QRect(0, c, t, h - 2 * c),
        Qt.RightEdge: QRect(w - t, c, t, h - 2 * c),
        Qt.TopEdge: QRect(c, 0, w - 2 * c, t),
        Qt.BottomEdge: QRect(c, h - t, w - 2 * c, t),
        Qt.TopEdge | Qt.LeftEdge: QRect(0, 0, c, c),
        Qt.BottomEdge | Qt.RightEdge: QRect(w - c, h - c, c, c),
        Qt.TopEdge | Qt.RightEdge: QRect(w - c, 0, c, c),
        Qt.BottomEdge | Qt.LeftEdge: QRect(0, h - c, c, c),
    }
    for grip in grips:
        grip.setGeometry(boxes[grip.edges])
        grip.raise_()
