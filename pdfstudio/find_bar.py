"""Slim find bar (Ctrl+F) shown above the page view."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QToolButton, QWidget)


class FindBar(QWidget):
    find_requested = Signal(str, bool)   # (query, backward)
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(QLabel("Find:"))
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Search text…")
        self.edit.setClearButtonEnabled(True)
        layout.addWidget(self.edit, 1)
        prev_btn = QPushButton("Previous")
        next_btn = QPushButton("Next")
        self.count_label = QLabel("")
        close_btn = QToolButton()
        close_btn.setText("✕")
        layout.addWidget(prev_btn)
        layout.addWidget(next_btn)
        layout.addWidget(self.count_label)
        layout.addWidget(close_btn)

        self.edit.returnPressed.connect(lambda: self._emit(False))
        next_btn.clicked.connect(lambda: self._emit(False))
        prev_btn.clicked.connect(lambda: self._emit(True))
        close_btn.clicked.connect(self.hide_bar)
        QShortcut(QKeySequence("Escape"), self, self.hide_bar)
        self.hide()

    def _emit(self, backward: bool):
        text = self.edit.text().strip()
        if text:
            self.find_requested.emit(text, backward)

    def show_bar(self):
        self.show()
        self.edit.setFocus()
        self.edit.selectAll()

    def hide_bar(self):
        self.hide()
        self.count_label.setText("")
        self.closed.emit()

    def set_status(self, text: str):
        self.count_label.setText(text)
