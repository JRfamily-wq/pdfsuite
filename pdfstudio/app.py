"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication

from . import APP_NAME, theme
from .icons import app_icon
from .main_window import MainWindow


def main():
    QCoreApplication.setOrganizationName("PDFStudio")
    QCoreApplication.setApplicationName(APP_NAME)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    theme.apply(app)
    app.setWindowIcon(app_icon())

    window = MainWindow()
    window.show()
    if len(sys.argv) > 1:
        window.open_path(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
