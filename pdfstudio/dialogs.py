"""Small dialogs: text entry, passwords, watermark, page numbers, properties."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QFrame, QLabel, QLineEdit,
                               QPlainTextEdit, QSlider, QSpinBox, QVBoxLayout)

from .doc_features import COMPRESS_PRESETS
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


class SplitDialog(QDialog):
    """How to break a document into pieces."""

    def __init__(self, parent, page_count: int, has_bookmarks: bool):
        super().__init__(parent)
        self.setWindowTitle("Split document")
        self.page_count = page_count
        layout = QVBoxLayout(self)

        self.mode = QComboBox()
        self.mode.addItem(f"Every N pages (document has {page_count})", "every")
        self.mode.addItem("Custom page ranges", "ranges")
        if has_bookmarks:
            self.mode.addItem("At each top-level bookmark", "bookmarks")
        layout.addWidget(QLabel("Split:"))
        layout.addWidget(self.mode)

        form = QFormLayout()
        self.size = QSpinBox()
        self.size.setRange(1, max(1, page_count))
        self.size.setValue(1)
        form.addRow("Pages per file:", self.size)
        self.ranges = QLineEdit()
        self.ranges.setPlaceholderText("e.g. 1-3, 4-8, 9")
        form.addRow("Ranges:", self.ranges)
        layout.addLayout(form)

        self.hint = QLabel("")
        self.hint.setProperty("dim", "true")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        layout.addWidget(_buttons(self))

        self.mode.currentIndexChanged.connect(self._sync)
        self._sync()

    def _sync(self):
        mode = self.mode.currentData()
        self.size.setEnabled(mode == "every")
        self.ranges.setEnabled(mode == "ranges")
        self.hint.setText({
            "every": "Each file gets the given number of pages, in order.",
            "ranges": "Page numbers start at 1. Separate ranges with commas.",
            "bookmarks": "A new file starts at every top-level bookmark.",
        }.get(mode, ""))

    def parse_ranges(self):
        result = []
        for chunk in self.ranges.text().replace(";", ",").split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                if "-" in chunk:
                    a, b = chunk.split("-", 1)
                    start, end = int(a) - 1, int(b) - 1
                else:
                    start = end = int(chunk) - 1
            except ValueError:
                continue
            if 0 <= start <= end < self.page_count:
                result.append((start, end))
        return result

    def accept(self):
        if self.mode.currentData() == "ranges" and not self.parse_ranges():
            self.hint.setText("Enter at least one valid range, such as 1-3.")
            return
        super().accept()

    def values(self):
        return self.mode.currentData(), self.size.value(), self.parse_ranges()


class PageLabelDialog(QDialog):
    """Page labels are what a reader shows in its page box (i, ii, A-1...)."""

    STYLES = [("1, 2, 3 (decimal)", "D"), ("i, ii, iii (roman lower)", "r"),
              ("I, II, III (roman upper)", "R"), ("a, b, c (letters lower)", "a"),
              ("A, B, C (letters upper)", "A")]

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Page labels")
        form = QFormLayout(self)
        self.style = QComboBox()
        for label, code in self.STYLES:
            self.style.addItem(label, code)
        self.prefix = QLineEdit()
        self.prefix.setPlaceholderText("optional, e.g. A-")
        self.start = QSpinBox()
        self.start.setRange(1, 9999)
        self.start.setValue(1)
        form.addRow("Numbering:", self.style)
        form.addRow("Prefix:", self.prefix)
        form.addRow("Start at:", self.start)
        note = QLabel("Labels change what a PDF reader displays as the page "
                      "number. They do not print onto the page — use Add Page "
                      "Numbers for that.")
        note.setWordWrap(True)
        note.setProperty("dim", "true")
        form.addRow(note)
        form.addRow(_buttons(self))

    def values(self):
        return self.style.currentData(), self.prefix.text(), self.start.value()


def human_size(n: int) -> str:
    if n >= 1048576:
        return f"{n / 1048576:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} bytes"


class CompressDialog(QDialog):
    """Reduce file size, with an honest up-front look at what is achievable."""

    def __init__(self, parent, report: dict):
        super().__init__(parent)
        self.setWindowTitle("Reduce file size")
        self.report = report
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ---- what this document is made of
        current = human_size(report.get("total_bytes", 0))
        count = report.get("count", 0)
        share = report.get("share", 0.0)
        max_dpi = report.get("max_dpi", 0.0)
        if count and share > 0.2:
            verdict = (f"This document is {current}, and about {share:.0%} of that is "
                       f"{count} image{'s' if count != 1 else ''} at up to "
                       f"{max_dpi:.0f} dpi. Resampling them is where the saving is.")
        elif count:
            verdict = (f"This document is {current} with {count} "
                       f"image{'s' if count != 1 else ''}, but images are only "
                       f"{share:.0%} of it, so expect a modest saving.")
        else:
            verdict = (f"This document is {current} and contains no images. It is "
                       f"mostly text, so there is little to reclaim — the file is "
                       f"probably already near its smallest.")
        summary = QLabel(verdict)
        summary.setWordWrap(True)
        layout.addWidget(summary)

        # ---- presets
        layout.addWidget(QLabel("How much should quality be traded for size?"))
        self.preset = QComboBox()
        for key, label, _desc, _opts in COMPRESS_PRESETS:
            self.preset.addItem(label, key)
        self.preset.setCurrentIndex(2)          # balanced
        layout.addWidget(self.preset)
        self.desc = QLabel("")
        self.desc.setWordWrap(True)
        self.desc.setProperty("dim", "true")
        layout.addWidget(self.desc)

        # ---- fine control
        form = QFormLayout()
        self.dpi = QSpinBox()
        self.dpi.setRange(0, 600)
        self.dpi.setSingleStep(10)
        self.dpi.setSuffix(" dpi")
        self.dpi.setSpecialValueText("leave images alone")
        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.quality.setSuffix(" %")
        form.addRow("Resample images above:", self.dpi)
        form.addRow("Image quality:", self.quality)
        layout.addLayout(form)

        self.grayscale = QCheckBox("Convert images to greyscale")
        self.subset = QCheckBox("Subset embedded fonts (keeps only glyphs used)")
        self.strip = QCheckBox("Remove metadata, thumbnails and JavaScript")
        self.flatten = QCheckBox("Flatten annotations and form fields")
        self.flatten.setToolTip("Bakes them into the page — they can no longer be edited")
        for box in (self.grayscale, self.subset, self.strip, self.flatten):
            layout.addWidget(box)

        note = QLabel("Text, vector graphics and page layout are never altered. "
                      "The change is applied to the open document so you can look "
                      "at it, and Undo puts the originals back.")
        note.setWordWrap(True)
        note.setProperty("dim", "true")
        layout.addWidget(note)
        layout.addWidget(_buttons(self))

        self.preset.currentIndexChanged.connect(self._apply_preset)
        self._apply_preset()

    def _apply_preset(self):
        key = self.preset.currentData()
        for pkey, _label, desc, opts in COMPRESS_PRESETS:
            if pkey != key:
                continue
            self.desc.setText(desc)
            self.dpi.setValue(int(opts.get("image_dpi", 0)))
            self.quality.setValue(int(opts.get("quality", 75) or 75))
            self.grayscale.setChecked(bool(opts.get("grayscale")))
            self.subset.setChecked(bool(opts.get("subset_fonts", True)))
            self.strip.setChecked(bool(opts.get("strip_metadata")))
            return

    def values(self) -> dict:
        return {
            "image_dpi": self.dpi.value(),
            "quality": self.quality.value(),
            "grayscale": self.grayscale.isChecked(),
            "subset_fonts": self.subset.isChecked(),
            "strip_metadata": self.strip.isChecked(),
            "flatten_annotations": self.flatten.isChecked(),
        }
