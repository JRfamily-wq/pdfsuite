"""Page thumbnail sidebar: navigation, selection for page ops, drag-reorder."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QListView, QListWidget,
                               QListWidgetItem, QMenu)

THUMB_WIDTH = 110
THUMB_HEIGHT = 150


class ThumbnailPanel(QListWidget):
    """host must provide: doc, goto_page(i), move_page(src, dest),
    page_context_actions() -> list[QAction]."""

    def __init__(self, host):
        super().__init__()
        self.host = host
        self._pending: list[int] = []
        self._timer = QTimer(self)
        self._timer.setInterval(25)
        self._timer.timeout.connect(self._render_chunk)
        self._syncing = False

        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.TopToBottom)
        self.setWrapping(False)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Snap)
        self.setIconSize(QSize(THUMB_WIDTH, THUMB_HEIGHT))
        self.setSpacing(10)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setFixedWidth(THUMB_WIDTH + 60)
        self.setStyleSheet(
            "QListWidget { background: #3a3d42; border: none; padding: 6px; }"
            "QListWidget::item { color: #d7d9dd; }"
            "QListWidget::item:selected { background: #2a6db5; border-radius: 4px; }")

        self.currentRowChanged.connect(self._row_changed)
        self.model().rowsMoved.connect(self._rows_moved)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    # ------------------------------------------------------------ populate

    def populate(self):
        self._timer.stop()
        self._syncing = True
        self.clear()
        doc = self.host.doc
        if doc.is_open():
            placeholder = self._placeholder()
            for i in range(doc.page_count):
                item = QListWidgetItem(f"Page {i + 1}")
                item.setIcon(placeholder)
                item.setTextAlignment(Qt.AlignHCenter)
                self.addItem(item)
            self._pending = list(range(doc.page_count))
            self._timer.start()
        self._syncing = False

    def refresh_page(self, index: int):
        if 0 <= index < self.count():
            if index not in self._pending:
                self._pending.insert(0, index)
            self._timer.start()

    def _placeholder(self) -> QPixmap:
        pix = QPixmap(THUMB_WIDTH, THUMB_HEIGHT)
        pix.fill(QColor(230, 231, 233))
        painter = QPainter(pix)
        painter.setPen(QColor(180, 182, 186))
        painter.drawRect(0, 0, THUMB_WIDTH - 1, THUMB_HEIGHT - 1)
        painter.end()
        return pix

    def _render_chunk(self):
        doc = self.host.doc
        if not doc.is_open() or not self._pending:
            self._timer.stop()
            return
        for _ in range(4):
            if not self._pending:
                break
            i = self._pending.pop(0)
            if i >= doc.page_count or i >= self.count():
                continue
            try:
                page = doc.page(i)
                zoom = min(THUMB_WIDTH / max(1.0, page.rect.width),
                           THUMB_HEIGHT / max(1.0, page.rect.height))
                pix = doc.render(i, zoom)
                image = QImage(pix.samples, pix.width, pix.height, pix.stride,
                               QImage.Format_RGB888).copy()
                self.item(i).setIcon(QPixmap.fromImage(image))
            except Exception:
                pass
        if not self._pending:
            self._timer.stop()

    # ----------------------------------------------------------- selection

    def sync_current(self, index: int):
        if self._syncing:
            return
        self._syncing = True
        try:
            if 0 <= index < self.count() and self.currentRow() != index:
                self.setCurrentRow(index)
        finally:
            self._syncing = False

    def selected_pages(self) -> list[int]:
        rows = sorted({self.row(item) for item in self.selectedItems()})
        return rows

    def _row_changed(self, row: int):
        if self._syncing or row < 0:
            return
        self.host.goto_page(row)

    def _rows_moved(self, _parent, start, end, _dest_parent, dest_row):
        if self._syncing:
            return
        # Defer: this signal fires mid-drop, and the document update repopulates
        # the list — mutating it re-entrantly here can crash the item view.
        if start != end:
            QTimer.singleShot(0, self.populate)  # multi-item move: resync only
            return
        target = dest_row - 1 if dest_row > start else dest_row
        QTimer.singleShot(0, lambda: self.host.move_page(start, target))

    def _context_menu(self, pos):
        if not self.host.doc.is_open():
            return
        menu = QMenu(self)
        for action in self.host.page_context_actions():
            if action is None:
                menu.addSeparator()
            else:
                menu.addAction(action)
        menu.exec(self.mapToGlobal(pos))
