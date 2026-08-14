"""Side panels: page thumbnails, bookmarks, search results, and the inspector."""

from __future__ import annotations

import fitz
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox,
                               QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QMenu, QPushButton, QSpinBox,
                               QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from . import icons, theme
from .doc_features import STAMP_PRESETS

THUMB_W, THUMB_H = 116, 152


def _heading(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setProperty("heading", "true")
    return label


def _rule() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet(f"color: {theme.BORDER}; background: {theme.BORDER}; max-height:1px;")
    return line


class ThumbnailPanel(QListWidget):
    """Page thumbnails with drag-to-reorder and multi-select page operations."""

    def __init__(self, host):
        super().__init__()
        self.host = host
        self._pending: list[int] = []
        self._timer = QTimer(self)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._render_chunk)
        self._syncing = False

        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.TopToBottom)
        self.setWrapping(False)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Snap)
        self.setIconSize(QSize(THUMB_W, THUMB_H))
        self.setSpacing(8)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.currentRowChanged.connect(self._row_changed)
        self.model().rowsMoved.connect(self._rows_moved)
        self.setStyleSheet(
            f"QListWidget {{ background: {theme.BG_PANEL}; border: none; padding: 8px; }}"
            f"QListWidget::item {{ color: {theme.TEXT_DIM}; padding: 4px; }}"
            f"QListWidget::item:selected {{ background: {theme.ACCENT_DIM};"
            f"  border: 1px solid {theme.ACCENT}; border-radius: 6px; color: {theme.TEXT}; }}")

    def populate(self):
        self._timer.stop()
        self._syncing = True
        self.clear()
        doc = self.host.doc
        if doc.is_open():
            blank = self._blank()
            for i in range(doc.page_count):
                item = QListWidgetItem(f"{i + 1}")
                item.setIcon(blank)
                item.setTextAlignment(Qt.AlignHCenter)
                self.addItem(item)
            self._pending = list(range(doc.page_count))
            self._timer.start()
        self._syncing = False

    def refresh_page(self, index: int):
        if 0 <= index < self.count() and index not in self._pending:
            self._pending.insert(0, index)
            self._timer.start()

    def _blank(self) -> QPixmap:
        pix = QPixmap(THUMB_W, THUMB_H)
        pix.fill(QColor("#f2f3f5"))
        p = QPainter(pix)
        p.setPen(QColor("#c9ccd2"))
        p.drawRect(0, 0, THUMB_W - 1, THUMB_H - 1)
        p.end()
        return pix

    def _render_chunk(self):
        doc = self.host.doc
        if not doc.is_open() or not self._pending:
            self._timer.stop()
            return
        for _ in range(3):
            if not self._pending:
                break
            i = self._pending.pop(0)
            if i >= doc.page_count or i >= self.count():
                continue
            try:
                rect = doc.page(i).rect
                zoom = min(THUMB_W / max(1.0, rect.width), THUMB_H / max(1.0, rect.height))
                raw = doc.render(i, zoom)
                image = QImage(raw.samples, raw.width, raw.height, raw.stride,
                               QImage.Format_RGB888).copy()
                self.item(i).setIcon(QPixmap.fromImage(image))
            except Exception:
                pass
        if not self._pending:
            self._timer.stop()

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
        return sorted({self.row(i) for i in self.selectedItems()})

    def _row_changed(self, row: int):
        if not self._syncing and row >= 0:
            self.host.goto_page(row)

    def _rows_moved(self, _p, start, end, _dp, dest_row):
        if self._syncing:
            return
        if start != end:
            QTimer.singleShot(0, self.populate)
            return
        target = dest_row - 1 if dest_row > start else dest_row
        QTimer.singleShot(0, lambda: self.host.move_page(start, target))

    def _menu(self, pos):
        if not self.host.doc.is_open():
            return
        menu = QMenu(self)
        for action in self.host.page_context_actions():
            menu.addSeparator() if action is None else menu.addAction(action)
        menu.exec(self.mapToGlobal(pos))


class OutlinePanel(QWidget):
    """Document bookmarks."""

    def __init__(self, host):
        super().__init__()
        self.host = host
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        self.empty = QLabel("This document has no bookmarks.")
        self.empty.setProperty("dim", "true")
        self.empty.setWordWrap(True)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._clicked)
        layout.addWidget(self.empty)
        layout.addWidget(self.tree, 1)

    def populate(self):
        self.tree.clear()
        toc = self.host.doc.get_toc() if self.host.doc.is_open() else []
        self.empty.setVisible(not toc)
        self.tree.setVisible(bool(toc))
        stack: list[tuple[int, QTreeWidgetItem]] = []
        for level, title, page in toc:
            item = QTreeWidgetItem([title.strip() or "(untitled)"])
            item.setData(0, Qt.UserRole, max(0, page - 1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                stack[-1][1].addChild(item)
            else:
                self.tree.addTopLevelItem(item)
            stack.append((level, item))
        self.tree.expandToDepth(1)

    def _clicked(self, item, _col):
        page = item.data(0, Qt.UserRole)
        if page is not None:
            self.host.goto_page(int(page))


class SearchPanel(QWidget):
    """Whole-document search with a results list."""

    def __init__(self, host):
        super().__init__()
        self.host = host
        self.results: list[tuple[int, fitz.Rect]] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        row = QHBoxLayout()
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Search document…")
        self.entry.returnPressed.connect(self.run)
        button = QToolButton()
        button.setIcon(icons.icon("find"))
        button.clicked.connect(self.run)
        row.addWidget(self.entry, 1)
        row.addWidget(button)
        layout.addLayout(row)

        options = QHBoxLayout()
        self.case = QCheckBox("Match case")
        self.whole = QCheckBox("Whole words")
        options.addWidget(self.case)
        options.addWidget(self.whole)
        options.addStretch(1)
        layout.addLayout(options)

        self.summary = QLabel("")
        self.summary.setProperty("dim", "true")
        layout.addWidget(self.summary)

        self.list = QListWidget()
        self.list.itemClicked.connect(self._go)
        layout.addWidget(self.list, 1)

    def focus_entry(self):
        self.entry.setFocus()
        self.entry.selectAll()

    def run(self):
        needle = self.entry.text().strip()
        self.list.clear()
        self.results.clear()
        doc = self.host.doc
        if not needle or not doc.is_open():
            self.summary.setText("")
            self.host.canvas.search_hits = {}
            self.host.canvas.update()
            return
        hits: dict[int, list[fitz.Rect]] = {}
        for pno in range(doc.page_count):
            found = doc.search_page(pno, needle, case_sensitive=self.case.isChecked(),
                                    whole_words=self.whole.isChecked())
            if not found:
                continue
            hits[pno] = found
            context = doc.page_text(pno)
            for rect in found:
                self.results.append((pno, rect))
                snippet = self._snippet(context, needle)
                item = QListWidgetItem(f"Page {pno + 1}   {snippet}")
                item.setData(Qt.UserRole, len(self.results) - 1)
                self.list.addItem(item)
            if len(self.results) > 900:
                break
        self.host.canvas.search_hits = hits
        self.host.canvas.search_current = None
        self.host.canvas.update()
        pages = len(hits)
        self.summary.setText(
            f"{len(self.results)} match{'es' if len(self.results) != 1 else ''} "
            f"on {pages} page{'s' if pages != 1 else ''}" if self.results else "No matches")
        if self.results:
            self.list.setCurrentRow(0)
            self._jump(0)

    @staticmethod
    def _snippet(text: str, needle: str, width: int = 44) -> str:
        low, target = text.lower(), needle.lower()
        at = low.find(target)
        if at < 0:
            return ""
        start = max(0, at - width // 3)
        piece = text[start:start + width].replace("\n", " ").strip()
        return ("…" if start else "") + piece

    def _go(self, item):
        self._jump(int(item.data(Qt.UserRole)))

    def _jump(self, ordinal: int):
        if not (0 <= ordinal < len(self.results)):
            return
        pno, rect = self.results[ordinal]
        hits = self.host.canvas.search_hits.get(pno, [])
        local = next((i for i, r in enumerate(hits) if r == rect), 0)
        self.host.canvas.search_current = (pno, local)
        self.host.goto_page(pno)
        self.host.canvas.ensure_visible_rect(pno, rect)
        self.host.canvas.update()

    def step(self, delta: int):
        if not self.results:
            return
        row = self.list.currentRow() + delta
        row = max(0, min(row, len(self.results) - 1))
        self.list.setCurrentRow(row)
        self._jump(row)

    def clear(self):
        self.entry.clear()
        self.list.clear()
        self.results.clear()
        self.summary.setText("")
        self.host.canvas.search_hits = {}
        self.host.canvas.search_current = None
        self.host.canvas.update()


class InspectorPanel(QWidget):
    """Contextual formatting panel — changes with what you have selected."""

    changed = Signal(str, object)

    FAMILIES = [("Sans (Helvetica)", "helv"), ("Serif (Times)", "tiro"),
                ("Mono (Courier)", "cour")]

    def __init__(self, host):
        super().__init__()
        self.host = host
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)

        self.context = QLabel("Nothing selected")
        self.context.setWordWrap(True)
        self.context.setProperty("dim", "true")
        layout.addWidget(self.context)
        layout.addWidget(_rule())

        # ---- text formatting
        self.text_group = QWidget()
        tg = QVBoxLayout(self.text_group)
        tg.setContentsMargins(0, 0, 0, 0)
        tg.setSpacing(7)
        tg.addWidget(_heading("Text"))

        self.family = QComboBox()
        for label, code in self.FAMILIES:
            self.family.addItem(label, code)
        self.family.currentIndexChanged.connect(
            lambda: self._emit("family", self.family.currentData()))
        tg.addWidget(self.family)

        row = QHBoxLayout()
        self.size = QDoubleSpinBox()
        self.size.setRange(4, 400)
        self.size.setDecimals(1)
        self.size.setSingleStep(1.0)
        self.size.setValue(14.0)
        self.size.valueChanged.connect(lambda v: self._emit("size", float(v)))
        self.bold = QToolButton()
        self.bold.setIcon(icons.icon("bold"))
        self.bold.setCheckable(True)
        self.bold.setToolTip("Bold (Ctrl+B)")
        self.bold.clicked.connect(lambda: self._emit("bold", self.bold.isChecked()))
        self.italic = QToolButton()
        self.italic.setIcon(icons.icon("italic"))
        self.italic.setCheckable(True)
        self.italic.setToolTip("Italic (Ctrl+I)")
        self.italic.clicked.connect(lambda: self._emit("italic", self.italic.isChecked()))
        row.addWidget(QLabel("Size"))
        row.addWidget(self.size, 1)
        row.addWidget(self.bold)
        row.addWidget(self.italic)
        tg.addLayout(row)

        self.text_color = QPushButton("Text colour")
        self.text_color.clicked.connect(lambda: self._emit("pick_text_color", None))
        tg.addWidget(self.text_color)
        layout.addWidget(self.text_group)

        # ---- drawing defaults
        self.draw_group = QWidget()
        dg = QVBoxLayout(self.draw_group)
        dg.setContentsMargins(0, 0, 0, 0)
        dg.setSpacing(7)
        dg.addWidget(_heading("Drawing"))
        self.stroke_color = QPushButton("Stroke colour")
        self.stroke_color.clicked.connect(lambda: self._emit("pick_color", None))
        dg.addWidget(self.stroke_color)
        wrow = QHBoxLayout()
        self.width = QDoubleSpinBox()
        self.width.setRange(0.5, 24.0)
        self.width.setSingleStep(0.5)
        self.width.setValue(2.0)
        self.width.valueChanged.connect(lambda v: self._emit("width", float(v)))
        wrow.addWidget(QLabel("Thickness"))
        wrow.addWidget(self.width, 1)
        dg.addLayout(wrow)
        self.fill_shapes = QCheckBox("Fill shapes")
        self.fill_shapes.toggled.connect(lambda v: self._emit("fill", bool(v)))
        dg.addWidget(self.fill_shapes)
        layout.addWidget(self.draw_group)

        # ---- stamp chooser, shown only while the stamp tool is active
        self.stamp_group = QWidget()
        sg = QVBoxLayout(self.stamp_group)
        sg.setContentsMargins(0, 0, 0, 0)
        sg.setSpacing(7)
        sg.addWidget(_heading("Stamp"))
        self.stamp = QComboBox()
        for name in STAMP_PRESETS:
            self.stamp.addItem(name.title(), name)
        self.stamp.setEditable(True)
        self.stamp.currentTextChanged.connect(
            lambda t: self._emit("stamp", t.upper()))
        sg.addWidget(self.stamp)
        stamp_hint = QLabel("Pick a preset or type your own, then click the page.")
        stamp_hint.setWordWrap(True)
        stamp_hint.setProperty("dim", "true")
        sg.addWidget(stamp_hint)
        layout.addWidget(self.stamp_group)

        # ---- selected annotation
        self.annot_group = QWidget()
        ag = QVBoxLayout(self.annot_group)
        ag.setContentsMargins(0, 0, 0, 0)
        ag.setSpacing(7)
        ag.addWidget(_heading("Selected object"))
        self.annot_delete = QPushButton("Delete object")
        self.annot_delete.clicked.connect(lambda: self._emit("delete_annot", None))
        ag.addWidget(self.annot_delete)
        layout.addWidget(self.annot_group)

        layout.addStretch(1)
        self.hint = QLabel("")
        self.hint.setProperty("dim", "true")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

    def _emit(self, key, value):
        if not self._loading:
            self.changed.emit(key, value)

    def refresh(self):
        canvas = self.host.canvas
        self._loading = True
        try:
            editing = canvas.edit is not None
            selected = canvas.sel_annot is not None
            self.text_group.setVisible(editing or canvas.tool in ("text", "edittext"))
            self.annot_group.setVisible(selected)
            self.stamp_group.setVisible(canvas.tool == "stamp")
            self.draw_group.setVisible(not editing and canvas.tool != "stamp")

            if editing:
                style = canvas.edit.pending_style
                span = canvas.edit.selection_range()
                if span:
                    style = canvas.edit.style_at(span[0])
                self.size.setValue(round(style.size, 1))
                font = style.font
                if font is not None:
                    self.bold.setChecked(font.bold)
                    self.italic.setChecked(font.italic)
                    code = font.base14_family_code()
                    at = self.family.findData(code)
                    if at >= 0:
                        self.family.setCurrentIndex(at)
                    name = font.display_name
                    where = "embedded in the file" if font.embedded else "standard font"
                    self.context.setText(f"Editing text · {name} ({where})")
                self.hint.setText("Esc commits the edit. Drag the blue bar to move the "
                                  "block, the round grip to change its width.")
            elif selected:
                self.context.setText("Object selected — drag it, drag a corner to "
                                     "resize, or press Delete.")
                self.hint.setText("")
            else:
                self.context.setText(f"Tool: {canvas.tool}")
                self.hint.setText("")
                self.size.setValue(float(canvas.font_size))
                self.width.setValue(float(canvas.stroke_width))
        finally:
            self._loading = False
