"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from . import APP_NAME
from .icons import app_icon
from .main_window import MainWindow

STYLE = """
QToolBar { spacing: 3px; padding: 3px; }
QToolButton { padding: 3px; border-radius: 4px; }
QStatusBar QLabel { color: #555; }
"""


def main():
    QCoreApplication.setOrganizationName("PDFStudio")
    QCoreApplication.setApplicationName(APP_NAME)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setWindowIcon(app_icon())

    window = MainWindow()
    window.show()
    if len(sys.argv) > 1:
        window.open_path(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
