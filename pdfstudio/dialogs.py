"""Small dialogs: text entry, passwords, watermark, page numbers, properties."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QLabel, QLineEdit, QPlainTextEdit, QSlider,
                               QSpinBox, QVBoxLayout)

from .document import PAGE_SIZES


def _buttons(dialog: QDialog) -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


class TextEntryDialog(QDialog):
    """Multi-line text entry used by the Text, Note and Edit Text tools."""

    def __init__(self, parent, title: str, initial: str = "", label: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(420, 260)
        layout = QVBoxLayout(self)
        if label:
            layout.addWidget(QLabel(label))
        self.editor = QPlainTextEdit(initial)
        layout.addWidget(self.editor)
        layout.addWidget(_buttons(self))
        self.editor.setFocus()
        self.editor.selectAll()

    def text(self) -> str:
        return self.editor.toPlainText()


class NewDocumentDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("New PDF")
        form = QFormLayout(self)
        self.size_combo = QComboBox()
        self.size_combo.addItems(list(PAGE_SIZES.keys()))
        self.pages_spin = QSpinBox()
        self.pages_spin.setRange(1, 500)
        self.pages_spin.setValue(1)
        form.addRow("Page size:", self.size_combo)
        form.addRow("Pages:", self.pages_spin)
        form.addRow(_buttons(self))

    def values(self):
        return PAGE_SIZES[self.size_combo.currentText()], self.pages_spin.value()


class PasswordDialog(QDialog):
    """Set a password (asks twice)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Set password")
        form = QFormLayout(self)
        self.pw1 = QLineEdit()
        self.pw1.setEchoMode(QLineEdit.Password)
        self.pw2 = QLineEdit()
        self.pw2.setEchoMode(QLineEdit.Password)
        self.error = QLabel("")
        self.error.setStyleSheet("color: #c62828;")
        form.addRow("Password:", self.pw1)
        form.addRow("Confirm:", self.pw2)
        form.addRow(self.error)
        form.addRow(_buttons(self))

    def accept(self):
        if not self.pw1.text():
            self.error.setText("Password cannot be empty.")
            return
        if self.pw1.text() != self.pw2.text():
            self.error.setText("Passwords do not match.")
            return
        super().accept()

    def password(self) -> str:
        return self.pw1.text()


class WatermarkDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Add watermark")
        form = QFormLayout(self)
        self.text_edit = QLineEdit("CONFIDENTIAL")
        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 144)
        self.size_spin.setValue(48)
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(5, 80)
        self.opacity.setValue(18)
        form.addRow("Text:", self.text_edit)
        form.addRow("Font size:", self.size_spin)
        form.addRow("Opacity %:", self.opacity)
        form.addRow(_buttons(self))

    def values(self):
        return (self.text_edit.text(), float(self.size_spin.value()),
                self.opacity.value() / 100.0)


class PageNumbersDialog(QDialog):
    POSITIONS = ["bottom-center", "bottom-left", "bottom-right"]

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Add page numbers")
        form = QFormLayout(self)
        self.pos_combo = QComboBox()
        self.pos_combo.addItems(self.POSITIONS)
        self.fmt_edit = QLineEdit("{n} / {total}")
        self.start_spin = QSpinBox()
        self.start_spin.setRange(1, 9999)
        self.start_spin.setValue(1)
        form.addRow("Position:", self.pos_combo)
        form.addRow("Format:", self.fmt_edit)
        form.addRow("Start at:", self.start_spin)
        form.addRow(QLabel("Format placeholders: {n} = page number, {total} = page count"))
        form.addRow(_buttons(self))

    def values(self):
        return (self.fmt_edit.text() or "{n}", self.pos_combo.currentText(),
                self.start_spin.value())


class PropertiesDialog(QDialog):
    FIELDS = [("title", "Title"), ("author", "Author"),
              ("subject", "Subject"), ("keywords", "Keywords")]

    def __init__(self, parent, metadata: dict, info: str):
        super().__init__(parent)
        self.setWindowTitle("Document properties")
        self.resize(420, 0)
        form = QFormLayout(self)
        self.edits = {}
        for key, label in self.FIELDS:
            edit = QLineEdit(metadata.get(key) or "")
            self.edits[key] = edit
            form.addRow(label + ":", edit)
        info_label = QLabel(info)
        info_label.setStyleSheet("color: #666;")
        form.addRow(info_label)
        form.addRow(_buttons(self))

    def values(self) -> dict:
        return {key: edit.text() for key, edit in self.edits.items()}
