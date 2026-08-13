"""Main application window: menus, toolbars, and the glue between UI and document."""

from __future__ import annotations

import os

import fitz
from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import (QAction, QActionGroup, QColor, QImage, QKeySequence,
                           QPixmap)
from PySide6.QtWidgets import (QApplication, QColorDialog, QDialog,
                               QDoubleSpinBox, QFileDialog, QInputDialog,
                               QLabel, QMainWindow, QMessageBox, QScrollArea,
                               QSpinBox, QToolBar, QVBoxLayout, QWidget)

from . import APP_NAME, __version__
from .dialogs import (NewDocumentDialog, PageNumbersDialog, PasswordDialog,
                      PropertiesDialog, TextEntryDialog, WatermarkDialog)
from .document import PdfDocument, PdfError, WHITE, BLACK
from .find_bar import FindBar
from .icons import app_icon, color_swatch, tool_icon
from .page_view import TOOL_HINTS, PageView, Tool
from .thumbnails import ThumbnailPanel

PDF_FILTER = "PDF files (*.pdf)"
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff)"
ZOOM_LEVELS = (0.25, 0.33, 0.5, 0.67, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.doc = PdfDocument()
        self.doc.on_changed = self._on_doc_changed

        self.current_page = 0
        self.zoom = 1.0
        self.fit_mode = "width"           # "width" | "page" | None
        self.current_color = QColor(200, 40, 40)
        self.selected_annot: tuple[int, int] | None = None   # (page, xref)
        self._pan_origin = (0, 0)
        self._search_query = ""
        self._search_hit = -1             # index into current page's hits
        self.settings = QSettings()

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1280, 860)
        self.setAcceptDrops(True)

        self._build_central()
        self._build_actions()
        self._build_menus()
        self._build_toolbars()
        self._build_statusbar()

        self.thumbs = ThumbnailPanel(self)
        from PySide6.QtWidgets import QDockWidget
        dock = QDockWidget("Pages", self)
        dock.setObjectName("pagesDock")
        dock.setWidget(self.thumbs)
        dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.pages_dock = dock

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(120)
        self._resize_timer.timeout.connect(self._fit_rerender)

        self._sync_ui()

    # ----------------------------------------------------------------- UI build

    def _build_central(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.find_bar = FindBar()
        self.find_bar.find_requested.connect(self._find)
        self.find_bar.closed.connect(self._clear_search)
        layout.addWidget(self.find_bar)

        self.view = PageView(self)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.view)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setStyleSheet("QScrollArea { background: #52565c; border: none; }")
        layout.addWidget(self.scroll, 1)
        self.setCentralWidget(container)

    def _act(self, text, slot, shortcut=None, icon=None, checkable=False):
        action = QAction(text, self)
        if icon:
            action.setIcon(tool_icon(icon))
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.setCheckable(checkable)
        action.triggered.connect(slot)
        return action

    def _build_actions(self):
        self.act_new = self._act("&New…", self.action_new, "Ctrl+N", "new")
        self.act_open = self._act("&Open…", self.action_open, "Ctrl+O", "open")
        self.act_save = self._act("&Save", self.action_save, "Ctrl+S", "save")
        self.act_save_as = self._act("Save &As…", self.action_save_as, "Ctrl+Shift+S")
        self.act_save_pw = self._act("Save with Pass&word…", self.action_save_encrypted)
        self.act_save_opt = self._act("Save Optimi&zed As…", self.action_save_optimized)
        self.act_merge = self._act("&Insert / Merge PDF…", self.action_insert_pdf, "Ctrl+M")
        self.act_extract = self._act("&Extract Pages…", self.action_extract_pages)
        self.act_export_png = self._act("Export Page as &PNG…", self.action_export_png)
        self.act_props = self._act("P&roperties…", self.action_properties)
        self.act_print = self._act("&Print…", self.action_print, "Ctrl+P", "print")
        self.act_quit = self._act("E&xit", self.close, "Ctrl+Q")

        self.act_undo = self._act("&Undo", self.action_undo, "Ctrl+Z", "undo")
        self.act_redo = self._act("&Redo", self.action_redo, "Ctrl+Shift+Z", "redo")
        self.act_del_annot = self._act("&Delete Selected Annotation",
                                       self.delete_selected_annot, "Del")
        self.act_copy_text = self._act("&Copy Page Text", self.action_copy_text)
        self.act_find = self._act("&Find…", self.find_bar_show, "Ctrl+F", "find")

        self.act_rot_left = self._act("Rotate &Left", lambda: self.rotate_pages(-90))
        self.act_rot_right = self._act("Rotate &Right", lambda: self.rotate_pages(90))
        self.act_move_up = self._act("Move Page &Up", lambda: self.move_page_by(-1))
        self.act_move_down = self._act("Move Page &Down", lambda: self.move_page_by(1))
        self.act_insert_blank = self._act("&Insert Blank Page", self.action_insert_blank)
        self.act_delete_pages = self._act("De&lete Page(s)", self.action_delete_pages)
        self.act_page_numbers = self._act("Add Page &Numbers…", self.action_page_numbers)
        self.act_watermark = self._act("Add &Watermark…", self.action_watermark)

        self.act_zoom_in = self._act("Zoom &In", lambda: self.zoom_steps(1), "Ctrl++", "zoom-in")
        self.act_zoom_out = self._act("Zoom &Out", lambda: self.zoom_steps(-1), "Ctrl+-", "zoom-out")
        self.act_fit_width = self._act("Fit &Width", self.fit_width, "Ctrl+1", "fit-width")
        self.act_fit_page = self._act("Fit &Page", self.fit_page, "Ctrl+2", "fit-page")
        self.act_actual = self._act("&Actual Size", self.actual_size, "Ctrl+0")
        self.act_prev = self._act("&Previous Page", lambda: self.goto_page(self.current_page - 1), "PgUp")
        self.act_next = self._act("&Next Page", lambda: self.goto_page(self.current_page + 1), "PgDown")
        self.act_first = self._act("&First Page", lambda: self.goto_page(0), "Ctrl+Home")
        self.act_last = self._act("&Last Page", lambda: self.goto_page(self.doc.page_count - 1), "Ctrl+End")

        self.act_about = self._act("&About", self.action_about)
        self.act_shortcuts = self._act("&Keyboard Shortcuts", self.action_shortcuts)

        # tools
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_actions = {}
        for tool, label in [
            (Tool.SELECT, "Select / Pan"), (Tool.TEXT, "Add Text"),
            (Tool.EDIT_TEXT, "Edit Text"), (Tool.HIGHLIGHT, "Highlight"),
            (Tool.RECT, "Rectangle"), (Tool.ELLIPSE, "Ellipse"),
            (Tool.LINE, "Line"), (Tool.ARROW, "Arrow"), (Tool.INK, "Draw"),
            (Tool.WHITEOUT, "Whiteout"), (Tool.REDACT, "Redact"),
            (Tool.IMAGE, "Insert Image"), (Tool.NOTE, "Sticky Note"),
        ]:
            action = QAction(tool_icon(tool), label, self)
            action.setCheckable(True)
            action.setData(tool)
            action.setToolTip(f"{label} — {TOOL_HINTS.get(tool, '')}")
            action.triggered.connect(lambda _=False, t=tool: self.set_tool(t))
            self.tool_group.addAction(action)
            self.tool_actions[tool] = action
        self.tool_actions[Tool.SELECT].setChecked(True)

    def _build_menus(self):
        bar = self.menuBar()
        m_file = bar.addMenu("&File")
        for action in (self.act_new, self.act_open):
            m_file.addAction(action)
        self.recent_menu = m_file.addMenu("Open &Recent")
        self._rebuild_recent_menu()
        m_file.addSeparator()
        for action in (self.act_save, self.act_save_as, self.act_save_pw, self.act_save_opt):
            m_file.addAction(action)
        m_file.addSeparator()
        for action in (self.act_merge, self.act_extract, self.act_export_png):
            m_file.addAction(action)
        m_file.addSeparator()
        for action in (self.act_props, self.act_print):
            m_file.addAction(action)
        m_file.addSeparator()
        m_file.addAction(self.act_quit)

        m_edit = bar.addMenu("&Edit")
        for action in (self.act_undo, self.act_redo):
            m_edit.addAction(action)
        m_edit.addSeparator()
        m_edit.addAction(self.act_del_annot)
        m_edit.addSeparator()
        for action in (self.act_copy_text, self.act_find):
            m_edit.addAction(action)

        m_pages = bar.addMenu("&Pages")
        for action in (self.act_rot_left, self.act_rot_right):
            m_pages.addAction(action)
        m_pages.addSeparator()
        for action in (self.act_move_up, self.act_move_down):
            m_pages.addAction(action)
        m_pages.addSeparator()
        for action in (self.act_insert_blank, self.act_delete_pages):
            m_pages.addAction(action)
        m_pages.addSeparator()
        for action in (self.act_page_numbers, self.act_watermark):
            m_pages.addAction(action)

        m_view = bar.addMenu("&View")
        for action in (self.act_zoom_in, self.act_zoom_out, self.act_fit_width,
                       self.act_fit_page, self.act_actual):
            m_view.addAction(action)
        m_view.addSeparator()
        for action in (self.act_prev, self.act_next, self.act_first, self.act_last):
            m_view.addAction(action)

        m_help = bar.addMenu("&Help")
        m_help.addAction(self.act_shortcuts)
        m_help.addAction(self.act_about)

    def _build_toolbars(self):
        main_tb = QToolBar("Main")
        main_tb.setObjectName("mainToolbar")
        main_tb.setMovable(False)
        main_tb.setIconSize(QSize(22, 22))
        self.addToolBar(main_tb)
        for action in (self.act_open, self.act_save, self.act_print):
            main_tb.addAction(action)
        main_tb.addSeparator()
        for action in (self.act_undo, self.act_redo):
            main_tb.addAction(action)
        main_tb.addSeparator()

        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.setToolTip("Current page")
        self.page_spin.valueChanged.connect(self._page_spin_changed)
        self._page_spin_guard = False
        main_tb.addWidget(self.page_spin)
        self.page_total = QLabel(" / 0  ")
        main_tb.addWidget(self.page_total)
        main_tb.addSeparator()

        for action in (self.act_zoom_out, self.act_zoom_in, self.act_fit_width, self.act_fit_page):
            main_tb.addAction(action)
        self.zoom_label = QLabel(" 100% ")
        main_tb.addWidget(self.zoom_label)
        main_tb.addSeparator()
        main_tb.addAction(self.act_find)

        self.addToolBarBreak()
        tools_tb = QToolBar("Tools")
        tools_tb.setObjectName("toolsToolbar")
        tools_tb.setMovable(False)
        tools_tb.setIconSize(QSize(22, 22))
        self.addToolBar(tools_tb)
        for tool, action in self.tool_actions.items():
            tools_tb.addAction(action)
            if tool in (Tool.SELECT, Tool.EDIT_TEXT, Tool.INK, Tool.REDACT):
                tools_tb.addSeparator()

        self.color_action = QAction(color_swatch(self.current_color), "Color", self)
        self.color_action.setToolTip("Stroke / text color")
        self.color_action.triggered.connect(self.pick_color)
        tools_tb.addAction(self.color_action)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.5, 12.0)
        self.width_spin.setSingleStep(0.5)
        self.width_spin.setValue(2.0)
        self.width_spin.setPrefix("W ")
        self.width_spin.setToolTip("Stroke width")
        tools_tb.addWidget(self.width_spin)

        self.font_spin = QSpinBox()
        self.font_spin.setRange(6, 96)
        self.font_spin.setValue(14)
        self.font_spin.setPrefix("A ")
        self.font_spin.setToolTip("Font size for the Text tool")
        tools_tb.addWidget(self.font_spin)

    def _build_statusbar(self):
        self.status_hint = QLabel("")
        self.statusBar().addWidget(self.status_hint, 1)
        self.status_info = QLabel("")
        self.statusBar().addPermanentWidget(self.status_info)

    # -------------------------------------------------------------- rendering

    def _on_doc_changed(self, structural: bool):
        if self.doc.is_open():
            self.current_page = max(0, min(self.current_page, self.doc.page_count - 1))
        self.selected_annot = None
        self.render_page()
        if structural:
            self.thumbs.populate()
            self.thumbs.sync_current(self.current_page)
        else:
            self.thumbs.refresh_page(self.current_page)
        self._sync_ui()

    def render_page(self):
        if not self.doc.is_open():
            self.view.set_content(None)
            return
        if self.fit_mode:
            self._compute_fit_zoom()
        index = self.current_page
        dpr = self.devicePixelRatioF() or 1.0
        try:
            pix = self.doc.render(index, min(self.zoom * dpr, 8.0))
        except Exception as exc:
            self.statusBar().showMessage(f"Render failed: {exc}", 4000)
            return
        image = QImage(pix.samples, pix.width, pix.height, pix.stride,
                       QImage.Format_RGB888).copy()
        qpix = QPixmap.fromImage(image)
        qpix.setDevicePixelRatio(dpr)
        fwd = self.doc.display_matrix(index, self.zoom)
        inv = self.doc.inverse_matrix(index, self.zoom)
        self.view.set_content(qpix, fwd, inv)
        self._apply_search_overlay()
        self.zoom_label.setText(f" {int(self.zoom * 100)}% ")

    def _compute_fit_zoom(self):
        if not self.doc.is_open():
            return
        page = self.doc.page(self.current_page)
        avail_w = max(100, self.scroll.viewport().width() - 24)
        avail_h = max(100, self.scroll.viewport().height() - 24)
        zw = avail_w / max(1.0, page.rect.width)
        zh = avail_h / max(1.0, page.rect.height)
        self.zoom = min(zw, zh) if self.fit_mode == "page" else zw
        self.zoom = max(0.1, min(self.zoom, 8.0))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fit_mode and self.doc.is_open():
            self._resize_timer.start()

    def _fit_rerender(self):
        if self.fit_mode:
            self.render_page()

    def _sync_ui(self):
        open_ = self.doc.is_open()
        for action in (self.act_save, self.act_save_as, self.act_save_pw,
                       self.act_save_opt, self.act_merge, self.act_extract,
                       self.act_export_png, self.act_props, self.act_print,
                       self.act_copy_text, self.act_find, self.act_rot_left,
                       self.act_rot_right, self.act_move_up, self.act_move_down,
                       self.act_insert_blank, self.act_delete_pages,
                       self.act_page_numbers, self.act_watermark,
                       self.act_zoom_in, self.act_zoom_out, self.act_fit_width,
                       self.act_fit_page, self.act_actual, self.act_prev,
                       self.act_next, self.act_first, self.act_last):
            action.setEnabled(open_)
        for action in self.tool_actions.values():
            action.setEnabled(open_)
        self.act_undo.setEnabled(open_ and self.doc.can_undo)
        self.act_redo.setEnabled(open_ and self.doc.can_redo)
        self.act_del_annot.setEnabled(self.selected_annot is not None)

        count = self.doc.page_count
        self._page_spin_guard = True
        self.page_spin.setRange(1, max(1, count))
        self.page_spin.setValue(self.current_page + 1)
        self._page_spin_guard = False
        self.page_total.setText(f" / {count}  ")
        self.page_spin.setEnabled(open_)

        name = os.path.basename(self.doc.path) if self.doc.path else (
            "Untitled" if open_ else "")
        self.setWindowTitle(f"{name}[*] — {APP_NAME}" if name else APP_NAME)
        self.setWindowModified(self.doc.dirty)
        if open_:
            page = self.doc.page(self.current_page)
            self.status_info.setText(
                f"{page.rect.width:.0f} × {page.rect.height:.0f} pt   ")

    # ------------------------------------------------------------- navigation

    def goto_page(self, index: int):
        if not self.doc.is_open():
            return
        index = max(0, min(index, self.doc.page_count - 1))
        if index == self.current_page:
            return
        self.current_page = index
        self.selected_annot = None
        self._search_hit = -1
        self.render_page()
        self.thumbs.sync_current(index)
        self._sync_ui()

    def _page_spin_changed(self, value: int):
        if not self._page_spin_guard:
            self.goto_page(value - 1)

    # ------------------------------------------------------------------- zoom

    def set_zoom(self, zoom: float, fit_mode=None):
        self.fit_mode = fit_mode
        self.zoom = max(0.1, min(zoom, 8.0))
        self.render_page()

    def zoom_steps(self, steps: float):
        if not self.doc.is_open():
            return
        levels = list(ZOOM_LEVELS)
        current = self.zoom
        if steps > 0:
            nxt = next((z for z in levels if z > current * 1.01), levels[-1])
        else:
            nxt = next((z for z in reversed(levels) if z < current * 0.99), levels[0])
        self.set_zoom(nxt, fit_mode=None)

    def fit_width(self):
        self.set_zoom(self.zoom, fit_mode="width")

    def fit_page(self):
        self.set_zoom(self.zoom, fit_mode="page")

    def actual_size(self):
        self.set_zoom(1.0, fit_mode=None)

    # ---------------------------------------------------------------- panning

    def begin_pan(self):
        self._pan_origin = (self.scroll.horizontalScrollBar().value(),
                            self.scroll.verticalScrollBar().value())

    def pan_move(self, dx: int, dy: int):
        self.scroll.horizontalScrollBar().setValue(self._pan_origin[0] - dx)
        self.scroll.verticalScrollBar().setValue(self._pan_origin[1] - dy)

    # ------------------------------------------------------------- file actions

    def action_new(self):
        if not self._confirm_discard():
            return
        dialog = NewDocumentDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        size, pages = dialog.values()
        self.current_page = 0
        self.doc.new(pages=pages, size=size)
        self.set_tool(Tool.SELECT)

    def action_open(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", self._last_dir(), PDF_FILTER)
        if path:
            self.open_path(path)

    def open_path(self, path: str):
        password = None
        while True:
            try:
                result = self.doc.open(path, password)
            except PdfError as exc:
                QMessageBox.critical(self, APP_NAME, str(exc))
                return
            if result == "ok":
                break
            from PySide6.QtWidgets import QLineEdit
            title = "Password required" if result == "needs_password" else "Wrong password — try again"
            password, ok = QInputDialog.getText(
                self, title, f"Password for {os.path.basename(path)}:",
                QLineEdit.Password)
            if not ok:
                return
        self.current_page = 0
        self._remember_recent(path)
        self.set_tool(Tool.SELECT)
        self.fit_width()

    def action_save(self):
        if not self.doc.is_open():
            return
        if not self.doc.path:
            self.action_save_as()
            return
        try:
            self.doc.save()
            self.statusBar().showMessage("Saved", 2500)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Save failed: {exc}")

    def _save_as_path(self, title="Save PDF As"):
        suggestion = self.doc.path or os.path.join(self._last_dir(), "document.pdf")
        path, _ = QFileDialog.getSaveFileName(self, title, suggestion, PDF_FILTER)
        if path and not path.lower().endswith(".pdf"):
            path += ".pdf"
        return path

    def action_save_as(self):
        path = self._save_as_path()
        if not path:
            return
        try:
            self.doc.save(path)
            self._remember_recent(path)
            self.statusBar().showMessage("Saved", 2500)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Save failed: {exc}")

    def action_save_encrypted(self):
        dialog = PasswordDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        path = self._save_as_path("Save Encrypted PDF As")
        if not path:
            return
        try:
            self.doc.save(path, user_pw=dialog.password())
            self.statusBar().showMessage("Saved with password", 3000)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Save failed: {exc}")

    def action_save_optimized(self):
        path = self._save_as_path("Save Optimized PDF As")
        if not path:
            return
        try:
            self.doc.save(path, optimize=True)
            self.statusBar().showMessage("Saved (optimized)", 3000)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Save failed: {exc}")

    def action_insert_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Insert / Merge PDF",
                                              self._last_dir(), PDF_FILTER)
        if not path:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Insert PDF")
        box.setText(f"Where should the pages of\n{os.path.basename(path)}\nbe inserted?")
        after_btn = box.addButton("After current page", QMessageBox.AcceptRole)
        end_btn = box.addButton("At the end", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        clicked = box.clickedButton()
        try:
            if clicked is after_btn:
                count = self.doc.insert_pdf_file(path, at=self.current_page + 1)
            elif clicked is end_btn:
                count = self.doc.insert_pdf_file(path)
            else:
                return
            self.statusBar().showMessage(f"Inserted {count} page(s)", 3000)
        except (PdfError, Exception) as exc:
            QMessageBox.critical(self, APP_NAME, f"Insert failed: {exc}")

    def action_extract_pages(self):
        pages = self.thumbs.selected_pages() or [self.current_page]
        path, _ = QFileDialog.getSaveFileName(
            self, f"Extract {len(pages)} page(s) to…",
            os.path.join(self._last_dir(), "extracted.pdf"), PDF_FILTER)
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            self.doc.extract_pages(pages, path)
            self.statusBar().showMessage(f"Extracted {len(pages)} page(s)", 3000)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Extract failed: {exc}")

    def action_export_png(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export page as PNG",
            os.path.join(self._last_dir(), f"page-{self.current_page + 1}.png"),
            "PNG image (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        try:
            self.doc.export_page_image(self.current_page, path)
            self.statusBar().showMessage("Page exported", 3000)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Export failed: {exc}")

    def action_properties(self):
        meta = self.doc.get_metadata()
        page = self.doc.page(self.current_page)
        info = (f"{self.doc.page_count} page(s) · current page "
                f"{page.rect.width:.0f}×{page.rect.height:.0f} pt")
        dialog = PropertiesDialog(self, meta, info)
        if dialog.exec() == QDialog.Accepted:
            self.doc.set_metadata(dialog.values())
            self.statusBar().showMessage("Properties updated", 2500)

    def action_copy_text(self):
        text = self.doc.page_text(self.current_page)
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage(f"Copied text of page {self.current_page + 1}", 2500)

    def action_print(self):
        try:
            from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        except ImportError:
            QMessageBox.warning(self, APP_NAME, "Printing is not available in this build.")
            return
        from PySide6.QtGui import QPainter
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QDialog.Accepted:
            return
        painter = QPainter(printer)
        try:
            for i in range(self.doc.page_count):
                if i > 0:
                    printer.newPage()
                pix = self.doc.render(i, 2.0)
                image = QImage(pix.samples, pix.width, pix.height, pix.stride,
                               QImage.Format_RGB888).copy()
                target = painter.viewport()
                scaled = image.size()
                scaled.scale(target.size(), Qt.KeepAspectRatio)
                painter.drawImage(
                    target.x(), target.y(),
                    image.scaled(scaled, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        finally:
            painter.end()
        self.statusBar().showMessage("Sent to printer", 3000)

    # ------------------------------------------------------------ page actions

    def _target_pages(self) -> list[int]:
        pages = self.thumbs.selected_pages()
        return pages if pages else [self.current_page]

    def rotate_pages(self, delta: int):
        if self.doc.is_open():
            self.doc.rotate_pages(self._target_pages(), delta)

    def action_delete_pages(self):
        if not self.doc.is_open():
            return
        pages = self._target_pages()
        try:
            self.doc.delete_pages(pages)
        except PdfError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))

    def move_page(self, src: int, dest: int):
        if self.doc.is_open():
            self.current_page = max(0, min(dest, self.doc.page_count - 1))
            self.doc.move_page(src, dest)

    def move_page_by(self, delta: int):
        src = self.current_page
        dest = src + delta
        if 0 <= dest < self.doc.page_count:
            self.move_page(src, dest)

    def action_insert_blank(self):
        if self.doc.is_open():
            self.doc.insert_blank_page(self.current_page + 1, like=self.current_page)

    def action_page_numbers(self):
        dialog = PageNumbersDialog(self)
        if dialog.exec() == QDialog.Accepted:
            fmt, pos, start = dialog.values()
            try:
                self.doc.add_page_numbers(fmt=fmt, position=pos, start=start)
            except (KeyError, IndexError, ValueError) as exc:
                QMessageBox.warning(self, APP_NAME, f"Bad format string: {exc}")

    def action_watermark(self):
        dialog = WatermarkDialog(self)
        if dialog.exec() == QDialog.Accepted:
            text, size, opacity = dialog.values()
            if text.strip():
                self.doc.add_watermark(text, fontsize=size, opacity=opacity)

    def page_context_actions(self):
        return [self.act_rot_left, self.act_rot_right, None,
                self.act_move_up, self.act_move_down, None,
                self.act_insert_blank, self.act_delete_pages, None,
                self.act_extract]

    # ------------------------------------------------------------ tool commits

    def set_tool(self, tool: str):
        self.tool_actions[tool].setChecked(True)
        self.view.set_tool(tool)
        self.status_hint.setText(TOOL_HINTS.get(tool, ""))

    def pick_color(self):
        color = QColorDialog.getColor(self.current_color, self, "Choose color")
        if color.isValid():
            self.current_color = color
            self.view.color = color
            self.color_action.setIcon(color_swatch(color))

    def _rgb(self):
        c = self.current_color
        return (c.redF(), c.greenF(), c.blueF())

    def commit_rubber(self, tool: str, rect: fitz.Rect):
        index = self.current_page
        try:
            if tool == Tool.HIGHLIGHT:
                self.doc.add_highlight(index, rect)
            elif tool == Tool.RECT:
                self.doc.add_shape(index, "rect", rect, color=self._rgb(),
                                   width=self.width_spin.value())
            elif tool == Tool.ELLIPSE:
                self.doc.add_shape(index, "ellipse", rect, color=self._rgb(),
                                   width=self.width_spin.value())
            elif tool == Tool.WHITEOUT:
                self.doc.redact_area(index, rect, fill=WHITE)
            elif tool == Tool.REDACT:
                self.doc.redact_area(index, rect, fill=BLACK)
            elif tool == Tool.IMAGE:
                self._place_image(index, rect)
            elif tool == Tool.TEXT:
                self._place_text(index, rect)
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, f"Could not apply {tool}: {exc}")

    def _place_text(self, index: int, rect: fitz.Rect):
        dialog = TextEntryDialog(self, "Add text")
        if dialog.exec() != QDialog.Accepted or not dialog.text().strip():
            return
        fontsize = float(self.font_spin.value())
        if rect.width < 8 or rect.height < 8:
            lines = dialog.text().count("\n") + 1
            rect = fitz.Rect(rect.x0, rect.y0, rect.x0 + 260,
                             rect.y0 + (lines + 0.6) * fontsize * 1.25)
        self.doc.add_textbox(index, rect, dialog.text(), fontsize=fontsize,
                             color=self._rgb())

    def _place_image(self, index: int, rect: fitz.Rect):
        path, _ = QFileDialog.getOpenFileName(self, "Choose image",
                                              self._last_dir(), IMAGE_FILTER)
        if not path:
            return
        if rect.width < 8 or rect.height < 8:
            width, height = self.doc.image_size(path)
            scale = 260.0 / max(width, 1)
            rect = fitz.Rect(rect.x0, rect.y0, rect.x0 + width * scale,
                             rect.y0 + height * scale)
        self.doc.add_image(index, rect, path)

    def commit_line(self, tool: str, p1: fitz.Point, p2: fitz.Point):
        try:
            self.doc.add_line(self.current_page, p1, p2, color=self._rgb(),
                              width=self.width_spin.value(),
                              arrow=(tool == Tool.ARROW))
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, f"Could not draw line: {exc}")

    def commit_ink(self, points):
        if len(points) > 1:
            try:
                self.doc.add_ink(self.current_page, points, color=self._rgb(),
                                 width=self.width_spin.value())
            except Exception as exc:
                QMessageBox.warning(self, APP_NAME, f"Could not draw: {exc}")

    def commit_click(self, tool: str, point: fitz.Point):
        index = self.current_page
        if tool == Tool.NOTE:
            dialog = TextEntryDialog(self, "Sticky note")
            if dialog.exec() == QDialog.Accepted and dialog.text().strip():
                self.doc.add_note(index, point, dialog.text())
        elif tool == Tool.EDIT_TEXT:
            block = self.doc.block_at(index, point)
            if block is None:
                self.statusBar().showMessage("No editable text there", 3000)
                return
            dialog = TextEntryDialog(
                self, "Edit text", self.doc.block_text(block),
                label="Edits are re-set in Helvetica at the detected size — "
                      "complex layouts may shift slightly.")
            if dialog.exec() == QDialog.Accepted:
                self.doc.replace_block_text(index, block, dialog.text())

    # --------------------------------------------------------- annot selection

    def select_annot_at(self, point: fitz.Point) -> bool:
        hit = self.doc.annot_at(self.current_page, point)
        if hit is None:
            return False
        xref, rect = hit
        self.selected_annot = (self.current_page, xref)
        self.view.set_selection(self.view.from_page_rect(rect))
        self.act_del_annot.setEnabled(True)
        self.statusBar().showMessage("Annotation selected — press Del to delete", 4000)
        return True

    def clear_selection(self):
        self.selected_annot = None
        self.view.set_selection(None)
        self.act_del_annot.setEnabled(False)

    def delete_selected_annot(self):
        if self.selected_annot is None:
            return
        index, xref = self.selected_annot
        self.selected_annot = None
        self.doc.delete_annot(index, xref)

    # -------------------------------------------------------------------- find

    def find_bar_show(self):
        if self.doc.is_open():
            self.find_bar.show_bar()

    def _find(self, query: str, backward: bool):
        if not self.doc.is_open():
            return
        if query != self._search_query:
            self._search_query = query
            self._search_hit = -1
        count = self.doc.page_count
        page = self.current_page
        hits = self.doc.search_page(page, query)
        step = -1 if backward else 1
        nxt = self._search_hit + step
        if hits and 0 <= nxt < len(hits):
            self._search_hit = nxt
        else:
            found = False
            for offset in range(1, count + 1):
                candidate = (page + step * offset) % count
                candidate_hits = self.doc.search_page(candidate, query)
                if candidate_hits:
                    self.goto_page(candidate)
                    hits = candidate_hits
                    self._search_hit = len(hits) - 1 if backward else 0
                    found = True
                    break
            if not found:
                if hits:  # only hits are on this page — wrap within it
                    self._search_hit = len(hits) - 1 if backward else 0
                else:
                    self.find_bar.set_status("No matches")
                    self.view.set_search_rects([])
                    return
        self._apply_search_overlay(scroll_to_hit=True)

    def _apply_search_overlay(self, scroll_to_hit: bool = False):
        if not self._search_query or not self.doc.is_open():
            return
        hits = self.doc.search_page(self.current_page, self._search_query)
        rects = [self.view.from_page_rect(r) for r in hits]
        self.view.set_search_rects(rects)
        if hits:
            hit_index = max(0, min(self._search_hit, len(hits) - 1))
            self.find_bar.set_status(f"{hit_index + 1} of {len(hits)} on page")
            if scroll_to_hit and rects:
                rect = rects[hit_index]
                self.scroll.ensureVisible(rect.center().x(), rect.center().y(), 120, 120)

    def _clear_search(self):
        self._search_query = ""
        self._search_hit = -1
        self.view.set_search_rects([])

    # ----------------------------------------------------------- recent files

    def _last_dir(self) -> str:
        if self.doc.path:
            return os.path.dirname(self.doc.path)
        return self.settings.value("lastDir", os.path.expanduser("~"))

    def _remember_recent(self, path: str):
        self.settings.setValue("lastDir", os.path.dirname(path))
        recent = self.settings.value("recentFiles", []) or []
        if isinstance(recent, str):
            recent = [recent]
        recent = [p for p in recent if p != path]
        recent.insert(0, path)
        self.settings.setValue("recentFiles", recent[:10])
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        self.recent_menu.clear()
        recent = self.settings.value("recentFiles", []) or []
        if isinstance(recent, str):
            recent = [recent]
        for path in recent:
            action = QAction(os.path.basename(path), self)
            action.setToolTip(path)
            action.triggered.connect(lambda _=False, p=path: self._open_recent(p))
            self.recent_menu.addAction(action)
        self.recent_menu.setEnabled(bool(recent))

    def _open_recent(self, path: str):
        if not os.path.exists(path):
            QMessageBox.warning(self, APP_NAME, f"File not found:\n{path}")
            return
        if self._confirm_discard():
            self.open_path(path)

    # ------------------------------------------------------------------- misc

    def action_undo(self):
        self.doc.undo()

    def action_redo(self):
        self.doc.redo()

    def action_about(self):
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> v{__version__}<br><br>"
            "A free PDF viewer and editor.<br>"
            "Built with PySide6 (Qt) and PyMuPDF.<br><br>"
            "PyMuPDF is licensed under the AGPL — this application and its "
            "source code are free and open.")

    def action_shortcuts(self):
        QMessageBox.information(
            self, "Keyboard shortcuts",
            "<table cellpadding=4>"
            "<tr><td><b>Ctrl+O / Ctrl+S</b></td><td>Open / Save</td></tr>"
            "<tr><td><b>Ctrl+Z / Ctrl+Shift+Z</b></td><td>Undo / Redo</td></tr>"
            "<tr><td><b>Ctrl+F</b></td><td>Find text</td></tr>"
            "<tr><td><b>PgUp / PgDown</b></td><td>Previous / next page</td></tr>"
            "<tr><td><b>Ctrl++ / Ctrl+- / Ctrl+0</b></td><td>Zoom in / out / 100%</td></tr>"
            "<tr><td><b>Ctrl+1 / Ctrl+2</b></td><td>Fit width / fit page</td></tr>"
            "<tr><td><b>Ctrl+scroll</b></td><td>Zoom</td></tr>"
            "<tr><td><b>Del</b></td><td>Delete selected annotation</td></tr>"
            "<tr><td><b>Ctrl+M</b></td><td>Insert / merge PDF</td></tr>"
            "</table>")

    def _confirm_discard(self) -> bool:
        if not (self.doc.is_open() and self.doc.dirty):
            return True
        answer = QMessageBox.question(
            self, APP_NAME, "The document has unsaved changes. Save them first?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if answer == QMessageBox.Save:
            self.action_save()
            return not self.doc.dirty
        return answer == QMessageBox.Discard

    def closeEvent(self, event):
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()

    # ------------------------------------------------------------ drag & drop

    def dragEnterEvent(self, event):
        if any(url.toLocalFile().lower().endswith(".pdf")
               for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                if self._confirm_discard():
                    self.open_path(path)
                break
