"""Dark application theme — palette, stylesheet and shared metrics."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

# Core palette
BG_DEEP = "#1c1f24"          # window background
BG_PANEL = "#23272e"         # side panels
BG_BAR = "#2a2f37"           # toolbars
BG_HOVER = "#333944"
BG_ACTIVE = "#3d4552"
BORDER = "#383e47"
CANVAS = "#15171b"           # area behind the pages
TITLEBAR = "#14161a"         # custom window chrome
TEXT = "#e4e7ec"
TEXT_DIM = "#9aa3b0"
ACCENT = "#4c8dff"
ACCENT_DIM = "#2f5da8"
DANGER = "#e05563"
SELECT_FILL = "#4c8dff40"

PAGE_SHADOW = QColor(0, 0, 0, 110)
CARET_COLOR = QColor(30, 120, 255)
TEXT_SEL = QColor(76, 141, 255, 90)
BLOCK_OUTLINE = QColor(76, 141, 255, 190)
BLOCK_HOVER = QColor(140, 170, 220, 110)
SEARCH_HIT = QColor(255, 196, 0, 110)
SEARCH_CURRENT = QColor(255, 140, 0, 190)
HANDLE_FILL = QColor(255, 255, 255)
HANDLE_EDGE = QColor(60, 130, 240)


def apply(app):
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG_DEEP))
    palette.setColor(QPalette.WindowText, QColor(TEXT))
    palette.setColor(QPalette.Base, QColor(BG_PANEL))
    palette.setColor(QPalette.AlternateBase, QColor(BG_BAR))
    palette.setColor(QPalette.Text, QColor(TEXT))
    palette.setColor(QPalette.Button, QColor(BG_BAR))
    palette.setColor(QPalette.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipBase, QColor(BG_BAR))
    palette.setColor(QPalette.ToolTipText, QColor(TEXT))
    palette.setColor(QPalette.PlaceholderText, QColor(TEXT_DIM))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#5f6774"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#5f6774"))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#5f6774"))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)


STYLESHEET = f"""
QMainWindow, QDialog {{ background: {BG_DEEP}; }}
QWidget {{ color: {TEXT}; font-size: 13px; }}

QMenuBar {{ background: {BG_BAR}; padding: 2px 4px; border-bottom: 1px solid {BORDER}; }}
QMenuBar::item {{ padding: 5px 11px; border-radius: 5px; background: transparent; }}
QMenuBar::item:selected {{ background: {BG_ACTIVE}; }}
QMenu {{ background: {BG_PANEL}; border: 1px solid {BORDER};
         padding: 6px; border-radius: 8px; }}
QMenu::item {{ padding: 6px 26px 6px 24px; border-radius: 5px; }}
QMenu::item:selected {{ background: {ACCENT_DIM}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}
QMenu::icon {{ padding-left: 8px; }}

QToolBar {{ background: {BG_BAR}; border: none; padding: 4px 6px; spacing: 2px; }}
QToolBar::separator {{ background: {BORDER}; width: 1px; margin: 5px 7px; }}
QToolButton {{ background: transparent; border: 1px solid transparent;
               border-radius: 6px; padding: 5px; margin: 0px; }}
QToolButton:hover {{ background: {BG_HOVER}; border-color: {BORDER}; }}
QToolButton:pressed {{ background: {BG_ACTIVE}; }}
QToolButton:checked {{ background: {ACCENT_DIM}; border-color: {ACCENT}; }}
QToolButton::menu-indicator {{ image: none; }}

QStatusBar {{ background: {BG_BAR}; border-top: 1px solid {BORDER}; }}
QStatusBar QLabel {{ color: {TEXT_DIM}; padding: 0 6px; }}
QStatusBar::item {{ border: none; }}

QDockWidget {{ titlebar-close-icon: none; titlebar-normal-icon: none; }}
QDockWidget::title {{ background: {BG_BAR}; padding: 7px 10px;
                      border-bottom: 1px solid {BORDER};
                      font-weight: 600; font-size: 12px; }}

QScrollBar:vertical {{ background: transparent; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #495160; border-radius: 6px; min-height: 30px;
                               margin: 2px; }}
QScrollBar::handle:vertical:hover {{ background: #5a6373; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #495160; border-radius: 6px; min-width: 30px;
                                 margin: 2px; }}
QScrollBar::handle:horizontal:hover {{ background: #5a6373; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {BG_DEEP}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 4px 7px; selection-background-color: {ACCENT}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
QPlainTextEdit:focus {{ border-color: {ACCENT}; }}
/* Sub-control arrows are deliberately left unstyled — Qt cannot render the
   CSS transparent-border triangle and paints a solid block instead, so the
   Fusion style draws them. */
QComboBox QAbstractItemView {{ background: {BG_PANEL}; border: 1px solid {BORDER};
    selection-background-color: {ACCENT_DIM}; outline: none; padding: 4px; }}

QPushButton {{ background: {BG_BAR}; border: 1px solid {BORDER};
               border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ background: {BG_HOVER}; }}
QPushButton:pressed {{ background: {BG_ACTIVE}; }}
QPushButton:default {{ background: {ACCENT_DIM}; border-color: {ACCENT}; }}

QListWidget, QTreeWidget {{ background: {BG_PANEL}; border: none; outline: none; }}
QListWidget::item {{ border-radius: 6px; padding: 3px; color: {TEXT_DIM}; }}
QListWidget::item:selected {{ background: {ACCENT_DIM}; color: {TEXT}; }}
QListWidget::item:hover {{ background: {BG_HOVER}; }}
QTreeWidget::item {{ padding: 4px; border-radius: 5px; }}
QTreeWidget::item:selected {{ background: {ACCENT_DIM}; }}
QTreeWidget::item:hover {{ background: {BG_HOVER}; }}

QTabWidget::pane {{ border: none; background: {BG_PANEL}; }}
QTabBar::tab {{ background: transparent; color: {TEXT_DIM}; padding: 7px 13px;
                border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom-color: {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

QGroupBox {{ border: 1px solid {BORDER}; border-radius: 8px; margin-top: 16px;
             padding-top: 10px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px;
                    color: {TEXT_DIM}; font-size: 11px; }}

QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {ACCENT}; width: 14px; height: 14px;
    margin: -5px 0; border-radius: 7px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT_DIM}; border-radius: 2px; }}

QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {BORDER};
    border-radius: 4px; background: {BG_DEEP}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QToolTip {{ background: {BG_PANEL}; color: {TEXT}; border: 1px solid {BORDER};
            padding: 5px 7px; border-radius: 5px; }}
QSplitter::handle {{ background: {BORDER}; }}
QLabel[dim="true"] {{ color: {TEXT_DIM}; font-size: 11px; }}
QLabel[heading="true"] {{ color: {TEXT_DIM}; font-size: 10px; font-weight: 700;
                          letter-spacing: 1px; }}
"""

STYLESHEET += f"""
/* ---- custom window frame ---- */
QMainWindow#appWindow {{ border: 1px solid #30363f; }}
QMainWindow#appWindow[maxed="true"] {{ border: none; }}
QWidget#titleBar {{ background: {TITLEBAR}; border-bottom: 1px solid {BORDER}; }}
QLabel#titleTitle {{ color: {TEXT_DIM}; font-size: 12px; background: transparent; }}
QMenuBar#titleMenuBar {{ background: transparent; border: none; padding: 0; }}
QMenuBar#titleMenuBar::item {{ padding: 5px 10px; border-radius: 5px;
                               background: transparent; color: {TEXT}; }}
QMenuBar#titleMenuBar::item:selected {{ background: {BG_ACTIVE}; }}
QMenuBar#titleMenuBar::item:pressed {{ background: {ACCENT_DIM}; }}
"""
