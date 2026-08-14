"""Side panels for comments, bookmarks, forms and attachments."""

from __future__ import annotations

import os

import fitz
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
                               QFileDialog, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPlainTextEdit, QPushButton,
                               QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from . import icons, theme
from .doc_features import (FIELD_CHECKBOX, FIELD_CHOICE, FIELD_RADIO,
                           FIELD_SIGNATURE, FIELD_TEXT)

ANNOT_LABELS = {
    "Highlight": "Highlight", "Underline": "Underline", "StrikeOut": "Strikeout",
    "Square": "Rectangle", "Circle": "Ellipse", "Line": "Line", "Ink": "Drawing",
    "Text": "Note", "FreeText": "Text box", "Stamp": "Stamp",
}


def _heading(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setProperty("heading", "true")
    return label


class CommentsPanel(QWidget):
    """Every annotation in the document, in one reviewable list."""

    def __init__(self, host):
        super().__init__()
        self.host = host
        self.entries: list[dict] = []
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        row = QHBoxLayout()
        self.filter = QComboBox()
        self.filter.addItem("All comments", None)
        for key, label in [("Highlight", "Highlights"), ("Text", "Notes"),
                           ("Square", "Shapes"), ("Ink", "Drawings")]:
            self.filter.addItem(label, key)
        self.filter.currentIndexChanged.connect(self.populate)
        row.addWidget(self.filter, 1)
        refresh = QToolButton()
        refresh.setText("⟳")
        refresh.setToolTip("Refresh")
        refresh.clicked.connect(self.populate)
        row.addWidget(refresh)
        layout.addLayout(row)

        self.summary = QLabel("")
        self.summary.setProperty("dim", "true")
        layout.addWidget(self.summary)

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._selected)
        self.list.itemDoubleClicked.connect(lambda _: self._goto())
        layout.addWidget(self.list, 1)

        layout.addWidget(_heading("Comment"))
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText("Select a comment to read or edit its note…")
        self.note.setFixedHeight(84)
        layout.addWidget(self.note)

        buttons = QHBoxLayout()
        save = QPushButton("Save note")
        save.clicked.connect(self._save_note)
        goto = QPushButton("Go to")
        goto.clicked.connect(self._goto)
        delete = QPushButton("Delete")
        delete.clicked.connect(self._delete)
        for b in (goto, save, delete):
            buttons.addWidget(b)
        layout.addLayout(buttons)

    def populate(self):
        if self._loading:
            return
        self._loading = True
        try:
            self.list.clear()
            self.entries = []
            if not self.host.doc.is_open():
                self.summary.setText("")
                return
            wanted = self.filter.currentData()
            for entry in self.host.doc.all_annotations():
                if wanted and entry["type"] != wanted:
                    continue
                self.entries.append(entry)
                label = ANNOT_LABELS.get(entry["type"], entry["type"])
                preview = entry["content"] or self._page_snippet(entry)
                item = QListWidgetItem(f"p{entry['page'] + 1}  {label}"
                                       + (f" — {preview}" if preview else ""))
                item.setToolTip(preview or label)
                self.list.addItem(item)
            total = len(self.entries)
            self.summary.setText(
                f"{total} comment{'s' if total != 1 else ''}" if total else "No comments yet")
        finally:
            self._loading = False

    def _page_snippet(self, entry: dict, limit: int = 42) -> str:
        try:
            text = self.host.doc.page(entry["page"]).get_textbox(entry["rect"])
        except Exception:
            return ""
        text = " ".join(text.split())
        return text[:limit] + ("…" if len(text) > limit else "")

    def _current(self) -> dict | None:
        row = self.list.currentRow()
        return self.entries[row] if 0 <= row < len(self.entries) else None

    def _selected(self, _row):
        entry = self._current()
        self.note.setPlainText(entry["content"] if entry else "")

    def _goto(self):
        entry = self._current()
        if entry:
            self.host.goto_page(entry["page"])
            self.host.canvas.ensure_visible_rect(entry["page"], entry["rect"])
            self.host.canvas.sel_annot = (entry["page"], entry["xref"])
            self.host.canvas.sel_rect = fitz.Rect(entry["rect"])
            self.host.canvas.update()

    def _save_note(self):
        entry = self._current()
        if not entry:
            return
        if self.host.doc.set_annot_content(entry["page"], entry["xref"],
                                           self.note.toPlainText()):
            self.populate()
            self.host.statusBar().showMessage("Comment saved", 2500)

    def _delete(self):
        entry = self._current()
        if not entry:
            return
        self.host.canvas.clear_annot_selection()
        self.host.doc.delete_annot(entry["page"], entry["xref"])
        self.populate()


class BookmarksPanel(QWidget):
    """Bookmarks you can actually edit, not just follow."""

    def __init__(self, host):
        super().__init__()
        self.host = host
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.tree, 1)

        self.empty = QLabel("No bookmarks. Add one for the current page, or "
                            "generate them from the document's headings.")
        self.empty.setWordWrap(True)
        self.empty.setProperty("dim", "true")
        layout.addWidget(self.empty)

        row1 = QHBoxLayout()
        add = QPushButton("Add here")
        add.setToolTip("Bookmark the page you are on")
        add.clicked.connect(self._add)
        rename = QPushButton("Rename")
        rename.clicked.connect(self._rename)
        remove = QPushButton("Delete")
        remove.clicked.connect(self._remove)
        for b in (add, rename, remove):
            row1.addWidget(b)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        promote = QToolButton()
        promote.setText("←")
        promote.setToolTip("Promote (less indented)")
        promote.clicked.connect(lambda: self._shift(-1))
        demote = QToolButton()
        demote.setText("→")
        demote.setToolTip("Demote (more indented)")
        demote.clicked.connect(lambda: self._shift(1))
        auto = QPushButton("From headings")
        auto.setToolTip("Build a contents list by finding headings in the document")
        auto.clicked.connect(self._auto)
        row2.addWidget(promote)
        row2.addWidget(demote)
        row2.addWidget(auto, 1)
        layout.addLayout(row2)

    def populate(self):
        self._loading = True
        try:
            self.tree.clear()
            toc = self.host.doc.get_toc() if self.host.doc.is_open() else []
            self.empty.setVisible(not toc)
            self.tree.setVisible(bool(toc))
            stack: list[tuple[int, QTreeWidgetItem]] = []
            for position, (level, title, page) in enumerate(
                    (r[0], r[1], r[2]) for r in toc):
                item = QTreeWidgetItem([title.strip() or "(untitled)"])
                item.setData(0, Qt.UserRole, position)
                item.setData(0, Qt.UserRole + 1, max(0, page - 1))
                while stack and stack[-1][0] >= level:
                    stack.pop()
                (stack[-1][1].addChild(item) if stack
                 else self.tree.addTopLevelItem(item))
                stack.append((level, item))
            self.tree.expandAll()
        finally:
            self._loading = False

    def _position(self) -> int | None:
        item = self.tree.currentItem()
        return None if item is None else int(item.data(0, Qt.UserRole))

    def _clicked(self, item, _col):
        if self._loading:
            return
        page = item.data(0, Qt.UserRole + 1)
        if page is not None:
            self.host.goto_page(int(page))

    def _add(self):
        page = self.host.canvas.current_page
        suggestion = self._suggest_title(page)
        title, ok = QInputDialog.getText(self, "Add bookmark",
                                         f"Title for page {page + 1}:",
                                         text=suggestion)
        if ok and title.strip():
            self.host.doc.add_bookmark(title.strip(), page)
            self.populate()

    def _suggest_title(self, page: int) -> str:
        """Offer the largest line on the page as the bookmark name."""
        try:
            best, size = "", 0.0
            for block in self.host.doc.raw_blocks(page):
                for line in block["lines"]:
                    text, line_size = [], 0.0
                    for span in line["spans"]:
                        line_size = max(line_size, float(span.get("size", 0)))
                        text.append("".join(c.get("c", "") for c in span.get("chars", [])))
                    joined = " ".join("".join(text).split())
                    if line_size > size and 2 <= len(joined) <= 80:
                        best, size = joined, line_size
            return best
        except Exception:
            return ""

    def _rename(self):
        position = self._position()
        if position is None:
            return
        current = self.tree.currentItem().text(0)
        title, ok = QInputDialog.getText(self, "Rename bookmark", "Title:", text=current)
        if ok and title.strip():
            self.host.doc.rename_bookmark(position, title.strip())
            self.populate()

    def _remove(self):
        position = self._position()
        if position is not None:
            self.host.doc.remove_bookmark(position)
            self.populate()

    def _shift(self, delta: int):
        position = self._position()
        if position is not None:
            self.host.doc.shift_bookmark_level(position, delta)
            self.populate()

    def _auto(self):
        if not self.host.doc.is_open():
            return
        existing = self.host.doc.get_toc()
        if existing:
            answer = QMessageBox.question(
                self, "Generate bookmarks",
                f"This replaces the {len(existing)} bookmark(s) already here. Continue?",
                QMessageBox.Yes | QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        found = self.host.doc.bookmarks_from_headings()
        self.populate()
        self.host.statusBar().showMessage(
            f"Created {found} bookmark(s) from headings" if found
            else "No headings stood out from the body text", 5000)


class FormPanel(QWidget):
    """Lists a fillable form's fields and lets you fill them from here."""

    KIND_LABELS = {FIELD_TEXT: "Text", FIELD_CHECKBOX: "Tick box",
                   FIELD_RADIO: "Option", FIELD_CHOICE: "Choice",
                   FIELD_SIGNATURE: "Signature"}

    def __init__(self, host):
        super().__init__()
        self.host = host
        self.fields = []
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setProperty("dim", "true")
        layout.addWidget(self.status)

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._selected)
        layout.addWidget(self.list, 1)

        self.editor_label = QLabel("Value")
        self.editor_label.setProperty("heading", "true")
        layout.addWidget(self.editor_label)
        self.text_value = QLineEdit()
        self.text_value.returnPressed.connect(self._apply)
        layout.addWidget(self.text_value)
        self.choice_value = QComboBox()
        layout.addWidget(self.choice_value)
        self.check_value = QCheckBox("Ticked")
        layout.addWidget(self.check_value)

        buttons = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply)
        goto = QPushButton("Go to")
        goto.clicked.connect(self._goto)
        buttons.addWidget(goto)
        buttons.addWidget(apply_btn)
        layout.addLayout(buttons)

        actions = QHBoxLayout()
        reset = QPushButton("Reset form")
        reset.setToolTip("Clear every field")
        reset.clicked.connect(self._reset)
        flatten = QPushButton("Flatten")
        flatten.setToolTip("Burn the answers in so the form can no longer be edited")
        flatten.clicked.connect(self._flatten)
        actions.addWidget(reset)
        actions.addWidget(flatten)
        layout.addLayout(actions)

    def populate(self):
        self._loading = True
        try:
            self.list.clear()
            self.fields = []
            if not self.host.doc.is_open() or not self.host.doc.has_form:
                self.status.setText("This document has no fillable form fields.")
                for w in (self.list, self.text_value, self.choice_value,
                          self.check_value):
                    w.setVisible(False)
                return
            for w in (self.list, self.text_value):
                w.setVisible(True)
            self.fields = self.host.doc.form_fields()
            for field in self.fields:
                kind = self.KIND_LABELS.get(field.kind, field.kind)
                shown = ("✓" if field.checked else "—") if field.kind in (
                    FIELD_CHECKBOX, FIELD_RADIO) else (str(field.value or "") or "—")
                item = QListWidgetItem(f"p{field.page + 1}  {field.label}"
                                       f"  ({kind})   {shown}")
                if field.read_only:
                    item.setToolTip("Read-only")
                self.list.addItem(item)
            filled = sum(1 for f in self.fields
                         if (f.checked if f.kind in (FIELD_CHECKBOX, FIELD_RADIO)
                             else str(f.value or "").strip()))
            self.status.setText(f"{len(self.fields)} field(s), {filled} filled in")
            self._selected(self.list.currentRow())
        finally:
            self._loading = False

    def _current(self):
        row = self.list.currentRow()
        return self.fields[row] if 0 <= row < len(self.fields) else None

    def _selected(self, _row):
        field = self._current()
        is_choice = bool(field and field.kind == FIELD_CHOICE)
        is_check = bool(field and field.kind in (FIELD_CHECKBOX, FIELD_RADIO))
        self.text_value.setVisible(bool(field) and not is_choice and not is_check)
        self.choice_value.setVisible(is_choice)
        self.check_value.setVisible(is_check)
        if not field:
            return
        if is_choice:
            self.choice_value.clear()
            self.choice_value.addItems([str(c) for c in field.choices])
            at = self.choice_value.findText(str(field.value or ""))
            if at >= 0:
                self.choice_value.setCurrentIndex(at)
        elif is_check:
            self.check_value.setChecked(field.checked)
        else:
            self.text_value.setText(str(field.value or ""))

    def _apply(self):
        field = self._current()
        if not field or self._loading:
            return
        if field.kind == FIELD_CHOICE:
            value = self.choice_value.currentText()
        elif field.kind in (FIELD_CHECKBOX, FIELD_RADIO):
            value = self.check_value.isChecked()
        else:
            value = self.text_value.text()
        if self.host.doc.set_field_value(field.page, field.name, value):
            self.host.canvas.invalidate_cache(field.page)
            row = self.list.currentRow()
            self.populate()
            self.list.setCurrentRow(row)
        else:
            self.host.statusBar().showMessage(
                f"Could not set '{field.label}' — it may be read-only", 4000)

    def _goto(self):
        field = self._current()
        if field:
            self.host.goto_page(field.page)
            self.host.canvas.ensure_visible_rect(field.page, field.rect)

    def _reset(self):
        if QMessageBox.question(self, "Reset form", "Clear every field?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.host.doc.reset_form()
            self.host.canvas.invalidate_cache()
            self.populate()

    def _flatten(self):
        if QMessageBox.question(
                self, "Flatten form",
                "This writes the answers into the page and removes the fields, "
                "so the form can no longer be filled in.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.host.doc.flatten_form()
        self.host.canvas.invalidate_cache()
        self.populate()
        self.host.statusBar().showMessage("Form flattened", 4000)


class AttachmentsPanel(QWidget):
    """Files carried inside the PDF."""

    def __init__(self, host):
        super().__init__()
        self.host = host
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.status = QLabel("")
        self.status.setProperty("dim", "true")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.list = QListWidget()
        layout.addWidget(self.list, 1)

        buttons = QHBoxLayout()
        add = QPushButton("Attach…")
        add.clicked.connect(self._add)
        save = QPushButton("Save as…")
        save.clicked.connect(self._save)
        remove = QPushButton("Remove")
        remove.clicked.connect(self._remove)
        for b in (add, save, remove):
            buttons.addWidget(b)
        layout.addLayout(buttons)

    def populate(self):
        self.list.clear()
        if not self.host.doc.is_open():
            self.status.setText("")
            return
        items = self.host.doc.attachments()
        for entry in items:
            size = entry.get("size", 0)
            human = f"{size / 1024:.0f} KB" if size >= 1024 else f"{size} bytes"
            item = QListWidgetItem(f"{entry['filename']}   ({human})")
            item.setData(Qt.UserRole, entry["name"])
            item.setToolTip(entry.get("desc", ""))
            self.list.addItem(item)
        self.status.setText(f"{len(items)} file(s) embedded in this PDF"
                            if items else "Nothing attached to this PDF.")

    def _add(self):
        path, _ = QFileDialog.getOpenFileName(self, "Attach a file to this PDF",
                                              self.host._last_dir())
        if not path:
            return
        if self.host.doc.attach_file(path):
            self.populate()
            self.host.statusBar().showMessage(
                f"Attached {os.path.basename(path)}", 3000)

    def _save(self):
        item = self.list.currentItem()
        if item is None:
            return
        name = item.data(Qt.UserRole)
        path, _ = QFileDialog.getSaveFileName(self, "Save attachment as",
                                              os.path.join(self.host._last_dir(), name))
        if path and self.host.doc.extract_attachment(name, path):
            self.host.statusBar().showMessage("Attachment saved", 3000)

    def _remove(self):
        item = self.list.currentItem()
        if item is None:
            return
        if self.host.doc.delete_attachment(item.data(Qt.UserRole)):
            self.populate()
