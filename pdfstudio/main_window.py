"""Main window: menus, toolbars, docks, and the glue between UI and document."""

from __future__ import annotations

import os

import fitz
from PySide6.QtCore import QEvent, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QImage, QKeySequence
from PySide6.QtWidgets import (QApplication, QColorDialog, QComboBox, QDialog,
                               QDockWidget, QFileDialog, QInputDialog, QLabel,
                               QLineEdit, QMainWindow, QMenuBar, QMessageBox,
                               QScrollArea, QSpinBox, QTabWidget, QToolBar,
                               QWidget)

from . import APP_NAME, __version__, icons, theme
from .canvas import HINTS, PageCanvas, Tool, ViewMode
from .dialogs import (CompressDialog, NewDocumentDialog, PageLabelDialog,
                      PageNumbersDialog, PasswordDialog, PropertiesDialog,
                      SplitDialog, TextEntryDialog, WatermarkDialog,
                      human_size)
from .document import BLACK, WHITE, PdfDocument, PdfError
from .doc_features import STAMP_PRESETS
from .panels import InspectorPanel, SearchPanel, ThumbnailPanel
from .panels2 import (AttachmentsPanel, BookmarksPanel, CommentsPanel,
                      FormPanel)
from .titlebar import TitleBar, install_grips, position_grips, use_custom_frame

PDF_FILTER = "PDF files (*.pdf)"
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp)"
ZOOM_PRESETS = [("Fit width", "width"), ("Fit page", "page"), ("50%", 0.5),
                ("75%", 0.75), ("100%", 1.0), ("125%", 1.25), ("150%", 1.5),
                ("200%", 2.0), ("400%", 4.0)]

TOOLBAR_TOOLS = [
    (Tool.SELECT, "Select", "select"),
    (Tool.EDIT_TEXT, "Edit text", "edittext"),
    (Tool.TEXT, "Add text", "text"),
    (Tool.TEXT_SELECT, "Select text", "textselect"),
    None,
    (Tool.HIGHLIGHT, "Highlight", "highlight"),
    (Tool.UNDERLINE, "Underline", "underline"),
    (Tool.STRIKEOUT, "Strike out", "strikeout"),
    None,
    (Tool.RECT, "Rectangle", "rect"),
    (Tool.ELLIPSE, "Ellipse", "ellipse"),
    (Tool.LINE, "Line", "line"),
    (Tool.ARROW, "Arrow", "arrow"),
    (Tool.INK, "Draw", "ink"),
    None,
    (Tool.IMAGE, "Image", "image"),
    (Tool.NOTE, "Sticky note", "note"),
    None,
    (Tool.STAMP, "Stamp", "stamp"),
    None,
    (Tool.WHITEOUT, "Whiteout", "whiteout"),
    (Tool.REDACT, "Redact", "redact"),
    None,
    (Tool.SNAPSHOT, "Snapshot", "snapshot"),
    (Tool.LINK, "Link", "link"),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.doc = PdfDocument()
        self.doc.on_changed = self._on_doc_changed
        self.settings = QSettings()
        self.fill_shapes = False

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.resize(1440, 920)
        self.setAcceptDrops(True)
        self.setDockOptions(QMainWindow.AnimatedDocks | QMainWindow.AllowTabbedDocks)

        self._build_canvas()
        self._build_actions()
        self._build_menus()
        self._build_frame()
        self._build_toolbars()
        self._build_docks()
        self._build_statusbar()

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(110)
        self._resize_timer.timeout.connect(self._refit)
        self._sync_ui()

    # -------------------------------------------------------------- building

    def _build_canvas(self):
        self.canvas = PageCanvas(self)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setStyleSheet(f"QScrollArea {{ background: {theme.CANVAS}; border: none; }}")
        self.scroll.verticalScrollBar().valueChanged.connect(
            lambda _: self.canvas.update_current_page())
        self.setCentralWidget(self.scroll)

        self.canvas.page_changed.connect(self._page_changed)
        self.canvas.selection_changed.connect(self._refresh_inspector)
        self.canvas.edit_state_changed.connect(self._refresh_inspector)
        self.canvas.status_message.connect(lambda m: self.statusBar().showMessage(m, 6000))

    def _act(self, text, slot, shortcut=None, icon=None, checkable=False, tip=None):
        action = QAction(text, self)
        if icon:
            action.setIcon(icons.icon(icon))
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.setCheckable(checkable)
        action.setToolTip(tip or text.replace("&", "") +
                          (f"  ({QKeySequence(shortcut).toString()})" if shortcut else ""))
        action.triggered.connect(slot)
        return action

    def _build_actions(self):
        A = self._act
        self.act_new = A("&New…", self.action_new, "Ctrl+N", "new")
        self.act_open = A("&Open…", self.action_open, "Ctrl+O", "open")
        self.act_save = A("&Save", self.action_save, "Ctrl+S", "save")
        self.act_save_as = A("Save &As…", self.action_save_as, "Ctrl+Shift+S")
        self.act_save_pw = A("Save with Pass&word…", self.action_save_encrypted, None, "lock")
        self.act_save_opt = A("Save Optimi&sed As…", self.action_save_optimized)
        self.act_merge = A("&Insert / Merge PDF…", self.action_insert_pdf, "Ctrl+M", "merge")
        self.act_extract = A("&Extract Pages…", self.action_extract_pages, None, "extract")
        self.act_export_png = A("Export Page as &Image…", self.action_export_png)
        self.act_export_text = A("Export &Text…", self.action_export_text)
        self.act_props = A("Document P&roperties…", self.action_properties, None, "props")
        self.act_print = A("&Print…", self.action_print, "Ctrl+P", "print")
        self.act_quit = A("E&xit", self.close, "Ctrl+Q")

        self.act_undo = A("&Undo", self.action_undo, "Ctrl+Z", "undo")
        self.act_redo = A("&Redo", self.action_redo, "Ctrl+Shift+Z", "redo")
        self.act_copy = A("&Copy", self.action_copy, "Ctrl+C", "copy")
        self.act_delete_obj = A("&Delete Selection", self.action_delete_selection, "Del", "delete")
        self.act_select_all = A("Select &All Text on Page", self.action_select_all_text, "Ctrl+A")
        self.act_find = A("&Find…", self.action_find, "Ctrl+F", "find")
        self.act_find_next = A("Find &Next", lambda: self.search_panel.step(1), "F3")
        self.act_find_prev = A("Find &Previous", lambda: self.search_panel.step(-1), "Shift+F3")

        self.act_rot_left = A("Rotate &Left", lambda: self.rotate_pages(-90), "Ctrl+[", "rotate-left")
        self.act_rot_right = A("Rotate &Right", lambda: self.rotate_pages(90), "Ctrl+]", "rotate-right")
        self.act_move_up = A("Move Page &Up", lambda: self.move_page_by(-1))
        self.act_move_down = A("Move Page &Down", lambda: self.move_page_by(1))
        self.act_insert_blank = A("&Insert Blank Page", self.action_insert_blank)
        self.act_delete_pages = A("De&lete Page(s)", self.action_delete_pages)
        self.act_page_numbers = A("Add Page &Numbers…", self.action_page_numbers, None, "numbering")
        self.act_watermark = A("Add &Watermark…", self.action_watermark, None, "watermark")

        self.act_zoom_in = A("Zoom &In", lambda: self.zoom_step(1), "Ctrl++", "zoom-in")
        self.act_zoom_out = A("Zoom &Out", lambda: self.zoom_step(-1), "Ctrl+-", "zoom-out")
        self.act_fit_width = A("Fit &Width", lambda: self.set_zoom_mode("width"), "Ctrl+1", "fit-width")
        self.act_fit_page = A("Fit &Page", lambda: self.set_zoom_mode("page"), "Ctrl+2", "fit-page")
        self.act_actual = A("&Actual Size", lambda: self.set_zoom_mode(1.0), "Ctrl+0")
        self.act_prev = A("&Previous Page", lambda: self.goto_page(self.canvas.current_page - 1), "PgUp")
        self.act_next = A("&Next Page", lambda: self.goto_page(self.canvas.current_page + 1), "PgDown")
        self.act_first = A("&First Page", lambda: self.goto_page(0), "Ctrl+Home")
        self.act_last = A("&Last Page", lambda: self.goto_page(self.doc.page_count - 1), "Ctrl+End")
        self.act_fullscreen = A("F&ull Screen", self.action_fullscreen, "F11")
        self.act_toggle_side = A("Toggle &Sidebar", self.toggle_sidebar, "F9", "sidebar")
        self.act_toggle_inspect = A("Toggle &Inspector", self.toggle_inspector, "F10")

        # view modes
        self.act_view_continuous = A("&Continuous Scroll",
                                     lambda: self.set_view_mode(ViewMode.CONTINUOUS),
                                     "Ctrl+3", checkable=True)
        self.act_view_single = A("&Single Page",
                                 lambda: self.set_view_mode(ViewMode.SINGLE),
                                 "Ctrl+4", checkable=True)
        self.act_view_facing = A("&Two-Page Spread",
                                 lambda: self.set_view_mode(ViewMode.FACING),
                                 "Ctrl+5", checkable=True)
        self.act_night = A("&Night Mode", self.toggle_night, "Ctrl+D", checkable=True)
        self.view_group = QActionGroup(self)
        for act in (self.act_view_continuous, self.act_view_single, self.act_view_facing):
            self.view_group.addAction(act)
        self.act_view_continuous.setChecked(True)

        # document tools
        self.act_split = A("&Split Document…", self.action_split)
        self.act_crop = A("&Crop Pages…", self.action_crop)
        self.act_reset_crop = A("Reset Cro&p", self.action_reset_crop)
        self.act_images_pdf = A("Insert &Images as Pages…", self.action_images_to_pages)
        self.act_flatten_annots = A("&Flatten Annotations", self.action_flatten_annots)
        self.act_page_labels = A("Page &Labels…", self.action_page_labels)
        self.act_attach = A("&Attach File…", self.action_attach)
        self.act_bookmarks_auto = A("&Generate Bookmarks from Headings",
                                    self.action_auto_bookmarks)
        self.act_form_reset = A("&Reset Form", self.action_form_reset)
        self.act_form_flatten = A("Flatten &Form", self.action_form_flatten)
        self.act_snapshot_save = A("Save Snapshot to &File…", self.action_snapshot_file)
        self.act_compress = A("&Reduce File Size…", self.action_compress, "Ctrl+Shift+C",
                              "compress")

        self.act_about = A("&About", self.action_about)
        self.act_shortcuts = A("&Keyboard Shortcuts", self.action_shortcuts, "F1")

        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_actions: dict[str, QAction] = {}
        for entry in TOOLBAR_TOOLS:
            if entry is None:
                continue
            tool, label, icon_name = entry
            action = QAction(icons.icon(icon_name), label, self)
            action.setCheckable(True)
            action.setToolTip(f"{label} — {HINTS.get(tool, '')}")
            action.triggered.connect(lambda _=False, t=tool: self.set_tool(t))
            self.tool_group.addAction(action)
            self.tool_actions[tool] = action
        self.tool_actions[Tool.SELECT].setChecked(True)

    def _build_menus(self):
        # Built as a standalone widget so the custom title bar can adopt it;
        # with the native frame it is installed as the ordinary menu bar.
        self.menu_bar = QMenuBar()
        bar = self.menu_bar
        m = bar.addMenu("&File")
        m.addAction(self.act_new)
        m.addAction(self.act_open)
        self.recent_menu = m.addMenu("Open &Recent")
        self._rebuild_recent()
        m.addSeparator()
        for a in (self.act_save, self.act_save_as, self.act_save_pw, self.act_save_opt):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_compress)
        m.addSeparator()
        for a in (self.act_merge, self.act_extract, self.act_export_png, self.act_export_text):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_props)
        m.addAction(self.act_print)
        m.addSeparator()
        m.addAction(self.act_quit)

        m = bar.addMenu("&Edit")
        for a in (self.act_undo, self.act_redo):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_copy, self.act_delete_obj, self.act_select_all):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_find, self.act_find_next, self.act_find_prev):
            m.addAction(a)

        m = bar.addMenu("&Tools")
        for entry in TOOLBAR_TOOLS:
            if entry is None:
                m.addSeparator()
            else:
                m.addAction(self.tool_actions[entry[0]])

        m = bar.addMenu("&Pages")
        for a in (self.act_rot_left, self.act_rot_right):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_move_up, self.act_move_down):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_insert_blank, self.act_delete_pages, self.act_extract):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_crop, self.act_reset_crop, self.act_split,
                  self.act_images_pdf):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_page_numbers, self.act_page_labels, self.act_watermark):
            m.addAction(a)

        m = bar.addMenu("&Document")
        for a in (self.act_form_reset, self.act_form_flatten):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_bookmarks_auto, self.act_attach, self.act_flatten_annots):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_snapshot_save)

        m = bar.addMenu("&View")
        for a in (self.act_zoom_in, self.act_zoom_out, self.act_fit_width,
                  self.act_fit_page, self.act_actual):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_view_continuous, self.act_view_single, self.act_view_facing):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_night)
        m.addSeparator()
        for a in (self.act_prev, self.act_next, self.act_first, self.act_last):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_fullscreen)
        m.addAction(self.act_toggle_side)
        m.addAction(self.act_toggle_inspect)

        m = bar.addMenu("&Help")
        m.addAction(self.act_shortcuts)
        m.addAction(self.act_about)

    def _build_frame(self):
        """Install either the custom frameless chrome or the native frame."""
        self.use_custom_frame = use_custom_frame()
        if not self.use_custom_frame:
            self.title_bar = None
            self.grips = []
            self.setMenuBar(self.menu_bar)
            return
        self.setObjectName("appWindow")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint
                            | Qt.WindowSystemMenuHint | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        self.title_bar = TitleBar(self, self.menu_bar)
        self.setMenuWidget(self.title_bar)
        self.grips = install_grips(self)
        self.title_bar.refresh_title()

    def _build_toolbars(self):
        tb = QToolBar("Main")
        tb.setObjectName("mainbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(22, 22))
        self.addToolBar(tb)
        for a in (self.act_toggle_side, None, self.act_open, self.act_save,
                  self.act_print, None, self.act_undo, self.act_redo, None):
            tb.addSeparator() if a is None else tb.addAction(a)

        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.setFixedWidth(58)
        self.page_spin.setAlignment(Qt.AlignCenter)
        self.page_spin.setToolTip("Go to page")
        self._spin_guard = False
        self.page_spin.valueChanged.connect(self._spin_changed)
        tb.addWidget(self.page_spin)
        self.page_total = QLabel(" / 0 ")
        tb.addWidget(self.page_total)

        tb.addSeparator()
        tb.addAction(self.act_zoom_out)
        self.zoom_combo = QComboBox()
        self.zoom_combo.setEditable(True)
        self.zoom_combo.setFixedWidth(104)
        for label, value in ZOOM_PRESETS:
            self.zoom_combo.addItem(label, value)
        self.zoom_combo.setCurrentIndex(0)
        self.zoom_combo.activated.connect(self._zoom_combo_picked)
        self.zoom_combo.lineEdit().returnPressed.connect(self._zoom_typed)
        tb.addWidget(self.zoom_combo)
        tb.addAction(self.act_zoom_in)
        tb.addAction(self.act_fit_width)
        tb.addAction(self.act_fit_page)
        tb.addSeparator()
        tb.addAction(self.act_rot_left)
        tb.addAction(self.act_rot_right)

        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy().Expanding,
                             spacer.sizePolicy().verticalPolicy().Preferred)
        tb.addWidget(spacer)
        tb.addAction(self.act_find)

        self.addToolBarBreak()
        tools = QToolBar("Tools")
        tools.setObjectName("toolsbar")
        tools.setMovable(False)
        tools.setIconSize(QSize(22, 22))
        self.addToolBar(tools)
        for entry in TOOLBAR_TOOLS:
            if entry is None:
                tools.addSeparator()
            else:
                tools.addAction(self.tool_actions[entry[0]])
        tools.addSeparator()
        self.color_action = QAction(icons.color_swatch(self.canvas.color), "Colour", self)
        self.color_action.setToolTip("Colour for new text, shapes and drawings")
        self.color_action.triggered.connect(self.pick_color)
        tools.addAction(self.color_action)

    def _build_docks(self):
        self.side_tabs = QTabWidget()
        self.side_tabs.setDocumentMode(True)
        self.thumbs = ThumbnailPanel(self)
        self.outline = BookmarksPanel(self)
        self.search_panel = SearchPanel(self)
        self.comments = CommentsPanel(self)
        self.forms = FormPanel(self)
        self.attachments = AttachmentsPanel(self)
        for widget, icon_name, tip in [
                (self.thumbs, "pages", "Page thumbnails"),
                (self.outline, "outline", "Bookmarks"),
                (self.search_panel, "find", "Search"),
                (self.comments, "note", "Comments"),
                (self.forms, "form", "Form fields"),
                (self.attachments, "attach", "Attachments")]:
            self.side_tabs.addTab(widget, icons.icon(icon_name), "")
            self.side_tabs.setTabToolTip(self.side_tabs.count() - 1, tip)
        self.SIDE_TITLES = ["Pages", "Bookmarks", "Search", "Comments",
                            "Form fields", "Attachments"]
        # Six tabs only fit if they stay compact — otherwise the tab bar grows
        # scroll arrows and half of them become unreachable.
        bar = self.side_tabs.tabBar()
        bar.setExpanding(False)
        bar.setUsesScrollButtons(False)
        bar.setIconSize(QSize(18, 18))
        bar.setStyleSheet("QTabBar::tab { padding: 6px 6px; margin: 0; }")

        self.side_dock = QDockWidget("Pages", self)
        self.side_dock.setObjectName("sideDock")
        self.side_dock.setWidget(self.side_tabs)
        self.side_dock.setFeatures(QDockWidget.DockWidgetMovable |
                                   QDockWidget.DockWidgetClosable)
        self.side_dock.setMinimumWidth(248)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.side_dock)
        self.side_tabs.currentChanged.connect(self._side_tab_changed)

        self.inspector = InspectorPanel(self)
        self.inspector.changed.connect(self._inspector_changed)
        self.inspect_dock = QDockWidget("Properties", self)
        self.inspect_dock.setObjectName("inspectDock")
        self.inspect_dock.setWidget(self.inspector)
        self.inspect_dock.setFeatures(QDockWidget.DockWidgetMovable |
                                      QDockWidget.DockWidgetClosable)
        self.inspect_dock.setMinimumWidth(226)
        self.addDockWidget(Qt.RightDockWidgetArea, self.inspect_dock)

    def _build_statusbar(self):
        self.status_hint = QLabel(HINTS[Tool.SELECT])
        self.statusBar().addWidget(self.status_hint, 1)
        self.status_page = QLabel("")
        self.status_size = QLabel("")
        for widget in (self.status_page, self.status_size):
            self.statusBar().addPermanentWidget(widget)

    # ------------------------------------------------------------- document

    def _on_doc_changed(self, structural: bool):
        page = self.canvas.current_page
        if self.doc.is_open():
            page = max(0, min(page, self.doc.page_count - 1))
        self.canvas.invalidate_cache(None if structural else page)
        self.canvas.relayout()
        if structural:
            self.thumbs.populate()
            self.outline.populate()
            self.thumbs.sync_current(page)
        else:
            self.thumbs.refresh_page(page)
        self._refresh_side_panel()
        self._sync_ui()

    def _refresh_side_panel(self):
        """Repopulate only the panel on screen — the others catch up when shown."""
        current = self.side_tabs.currentWidget()
        for panel in (self.comments, self.forms, self.attachments, self.outline):
            if panel is current:
                panel.populate()
                return

    def _side_tab_changed(self, index: int):
        titles = getattr(self, "SIDE_TITLES", [])
        self.side_dock.setWindowTitle(titles[index] if index < len(titles) else "Pages")
        widget = self.side_tabs.widget(index)
        if hasattr(widget, "populate") and widget is not self.thumbs:
            widget.populate()

    def _sync_ui(self):
        open_ = self.doc.is_open()
        for action in (self.act_save, self.act_save_as, self.act_save_pw,
                       self.act_save_opt, self.act_merge, self.act_extract,
                       self.act_export_png, self.act_export_text, self.act_props,
                       self.act_compress,
                       self.act_print, self.act_copy, self.act_select_all,
                       self.act_find, self.act_rot_left, self.act_rot_right,
                       self.act_move_up, self.act_move_down, self.act_insert_blank,
                       self.act_delete_pages, self.act_page_numbers,
                       self.act_watermark, self.act_zoom_in, self.act_zoom_out,
                       self.act_fit_width, self.act_fit_page, self.act_actual,
                       self.act_prev, self.act_next, self.act_first, self.act_last):
            action.setEnabled(open_)
        for action in self.tool_actions.values():
            action.setEnabled(open_)
        self.act_undo.setEnabled(open_ and self.doc.can_undo)
        self.act_redo.setEnabled(open_ and self.doc.can_redo)
        self.act_delete_obj.setEnabled(self.canvas.sel_annot is not None)
        self.page_spin.setEnabled(open_)

        count = self.doc.page_count
        self._spin_guard = True
        self.page_spin.setRange(1, max(1, count))
        self.page_spin.setValue(self.canvas.current_page + 1)
        self._spin_guard = False
        self.page_total.setText(f" / {count} ")
        self.status_page.setText(f"Page {self.canvas.current_page + 1} of {count}" if open_ else "")
        if open_:
            rect = self.doc.page(self.canvas.current_page).rect
            self.status_size.setText(f"{rect.width:.0f} × {rect.height:.0f} pt")
        else:
            self.status_size.setText("")

        name = os.path.basename(self.doc.path) if self.doc.path else ("Untitled" if open_ else "")
        self.setWindowTitle(f"{name}[*] — {APP_NAME}" if name else APP_NAME)
        self.setWindowModified(self.doc.dirty)
        if self.title_bar is not None:
            self.title_bar.refresh_title()
        self._refresh_inspector()

    def _refresh_inspector(self):
        self.inspector.refresh()
        self.act_delete_obj.setEnabled(self.canvas.sel_annot is not None)
        self.act_undo.setEnabled(self.doc.is_open() and self.doc.can_undo)
        self.act_redo.setEnabled(self.doc.is_open() and self.doc.can_redo)

    def _page_changed(self, index: int):
        self.thumbs.sync_current(index)
        self._spin_guard = True
        self.page_spin.setValue(index + 1)
        self._spin_guard = False
        self.status_page.setText(f"Page {index + 1} of {self.doc.page_count}")

    # ----------------------------------------------------------- navigation

    def goto_page(self, index: int):
        if not self.doc.is_open():
            return
        index = max(0, min(index, self.doc.page_count - 1))
        self.canvas.scroll_to_page(index)
        self._sync_ui()

    def _spin_changed(self, value: int):
        if not self._spin_guard:
            self.goto_page(value - 1)

    # ----------------------------------------------------------------- zoom

    def set_zoom_mode(self, mode):
        if isinstance(mode, str):
            self.canvas.set_zoom(self.canvas.zoom, fit_mode=mode)
        else:
            self.canvas.set_zoom(float(mode), fit_mode=None)
        self._update_zoom_label()

    def zoom_step(self, direction: int):
        levels = [0.25, 0.33, 0.5, 0.67, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 6.0]
        current = self.canvas.zoom
        if direction > 0:
            target = next((z for z in levels if z > current * 1.02), levels[-1])
        else:
            target = next((z for z in reversed(levels) if z < current * 0.98), levels[0])
        self.canvas.set_zoom(target, fit_mode=None)
        self._update_zoom_label()

    def _zoom_combo_picked(self, index: int):
        value = self.zoom_combo.itemData(index)
        self.set_zoom_mode(value)

    def _zoom_typed(self):
        text = self.zoom_combo.currentText().strip().rstrip("%")
        try:
            self.set_zoom_mode(max(8.0, min(float(text), 800.0)) / 100.0)
        except ValueError:
            self._update_zoom_label()

    def _update_zoom_label(self):
        mode = self.canvas.fit_mode
        label = ("Fit width" if mode == "width" else "Fit page" if mode == "page"
                 else f"{int(round(self.canvas.zoom * 100))}%")
        self.zoom_combo.setCurrentText(label)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.grips:
            position_grips(self, self.grips)
        if self.doc.is_open() and self.canvas.fit_mode:
            self._resize_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        if self.grips:
            position_grips(self, self.grips)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() != QEvent.WindowStateChange:
            return
        maxed = self.isMaximized() or self.isFullScreen()
        if self.title_bar is not None:
            self.title_bar.sync_max()
        for grip in self.grips:
            grip.setVisible(not maxed)
        if getattr(self, "use_custom_frame", False):
            # the 1px window border disappears while maximised, like a native frame
            self.setProperty("maxed", "true" if maxed else "false")
            self.style().unpolish(self)
            self.style().polish(self)

    def _refit(self):
        if self.canvas.fit_mode:
            self.canvas.set_zoom(self.canvas.zoom, fit_mode=self.canvas.fit_mode)

    def action_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized() if getattr(self, "_was_maximized", False) else self.showNormal()
        else:
            self._was_maximized = self.isMaximized()
            self.showFullScreen()

    def toggle_sidebar(self):
        self.side_dock.setVisible(not self.side_dock.isVisible())

    def toggle_inspector(self):
        self.inspect_dock.setVisible(not self.inspect_dock.isVisible())

    # ---------------------------------------------------------------- tools

    def set_tool(self, tool: str):
        action = self.tool_actions.get(tool)
        if action:
            action.setChecked(True)
        self.canvas.set_tool(tool)
        self.status_hint.setText(HINTS.get(tool, ""))
        self._refresh_inspector()

    def pick_color(self):
        color = QColorDialog.getColor(self.canvas.color, self, "Choose colour")
        if color.isValid():
            self.canvas.color = color
            self.color_action.setIcon(icons.color_swatch(color))
            if self.canvas.edit is not None:
                self.canvas.apply_edit_style(
                    color=(color.redF(), color.greenF(), color.blueF()))

    def _rgb(self):
        c = self.canvas.color
        return (c.redF(), c.greenF(), c.blueF())

    def _inspector_changed(self, key: str, value):
        canvas = self.canvas
        if key == "size":
            canvas.font_size = value
            if canvas.edit is not None:
                canvas.apply_edit_style(size=float(value))
        elif key in ("bold", "italic"):
            if canvas.edit is not None:
                canvas.apply_edit_style(**{key: bool(value)})
        elif key == "family":
            if canvas.edit is not None:
                canvas.apply_edit_style(family=value)
        elif key == "width":
            canvas.stroke_width = float(value)
        elif key == "fill":
            self.fill_shapes = bool(value)
        elif key == "stamp":
            canvas.stamp_text = str(value).strip() or "APPROVED"
        elif key in ("pick_color", "pick_text_color"):
            self.pick_color()
        elif key == "delete_annot":
            self.action_delete_selection()

    # --------------------------------------------------------- tool commits

    def commit_marquee(self, tool: str, index: int, rect: fitz.Rect):
        if tool == Tool.CROP:
            pages = self._target_pages()
            self.doc.crop_pages(pages, rect)
            self.set_tool(Tool.SELECT)
            self.statusBar().showMessage(f"Cropped {len(pages)} page(s)", 4000)
            return
        if tool == Tool.LINK:
            self._make_link(index, rect)
            return
        try:
            if tool == Tool.RECT:
                self.doc.add_shape(index, "rect", rect, color=self._rgb(),
                                   width=self.canvas.stroke_width,
                                   fill=self._rgb() if self.fill_shapes else None)
            elif tool == Tool.ELLIPSE:
                self.doc.add_shape(index, "ellipse", rect, color=self._rgb(),
                                   width=self.canvas.stroke_width,
                                   fill=self._rgb() if self.fill_shapes else None)
            elif tool == Tool.WHITEOUT:
                self.doc.redact_area(index, rect, fill=WHITE)
            elif tool == Tool.REDACT:
                self.doc.redact_area(index, rect, fill=BLACK)
            elif tool == Tool.IMAGE:
                self._place_image(index, rect)
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, f"Could not apply that: {exc}")

    def _make_link(self, index: int, rect: fitz.Rect):
        target, ok = QInputDialog.getText(
            self, "Create link",
            "Web address, or a page number to jump to:", text="https://")
        if not ok or not target.strip():
            return
        target = target.strip()
        if target.isdigit():
            page = max(1, min(int(target), self.doc.page_count)) - 1
            self.doc.add_goto_link(index, rect, page)
            self.statusBar().showMessage(f"Link to page {page + 1} created", 3000)
        else:
            if "://" not in target:
                target = "https://" + target
            self.doc.add_uri_link(index, rect, target)
            self.statusBar().showMessage("Link created", 3000)
        self.set_tool(Tool.SELECT)

    def commit_markup(self, tool: str, index: int, rects):
        kind = {Tool.HIGHLIGHT: "highlight", Tool.UNDERLINE: "underline",
                Tool.STRIKEOUT: "strikeout"}[tool]
        color = ((1.0, 0.85, 0.0) if kind == "highlight" else self._rgb())
        try:
            self.doc.add_text_markup(index, kind, rects, color=color)
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, f"Could not mark up the text: {exc}")

    def commit_line(self, tool: str, index: int, p1, p2):
        try:
            self.doc.add_line(index, p1, p2, color=self._rgb(),
                              width=self.canvas.stroke_width,
                              arrow=(tool == Tool.ARROW))
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, f"Could not draw that: {exc}")

    def commit_ink(self, index: int, points):
        try:
            self.doc.add_ink(index, points, color=self._rgb(),
                             width=self.canvas.stroke_width)
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, f"Could not draw that: {exc}")

    def commit_click(self, tool: str, index: int, point):
        if tool == Tool.NOTE:
            dialog = TextEntryDialog(self, "Sticky note", label="Note text:")
            if dialog.exec() == QDialog.Accepted and dialog.text().strip():
                self.doc.add_note(index, point, dialog.text())

    def _place_image(self, index: int, rect: fitz.Rect):
        path, _ = QFileDialog.getOpenFileName(self, "Choose image", self._last_dir(),
                                              IMAGE_FILTER)
        if not path:
            return
        if rect.width < 12 or rect.height < 12:
            w, h = self.doc.image_size(path)
            scale = 240.0 / max(w, 1)
            rect = fitz.Rect(rect.x0, rect.y0, rect.x0 + w * scale, rect.y0 + h * scale)
        self.doc.add_image(index, rect, path)

    # ---------------------------------------------------------- file actions

    def action_new(self):
        if not self._confirm_discard():
            return
        dialog = NewDocumentDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        size, pages = dialog.values()
        self.doc.new(pages=pages, size=size)
        self.set_tool(Tool.SELECT)
        self.set_zoom_mode("width")

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
            title = ("Password required" if result == "needs_password"
                     else "Wrong password — try again")
            password, ok = QInputDialog.getText(
                self, title, f"Password for {os.path.basename(path)}:", QLineEdit.Password)
            if not ok:
                return
        self._remember_recent(path)
        self.search_panel.clear()
        self.set_tool(Tool.SELECT)
        self.canvas.scroll_to_page(0)
        self.set_zoom_mode("width")
        self.statusBar().showMessage(f"Opened {os.path.basename(path)}", 4000)

    def action_save(self):
        if not self.doc.is_open():
            return
        self.canvas.commit_edit()
        if not self.doc.path:
            self.action_save_as()
            return
        try:
            self.doc.save()
            self.statusBar().showMessage("Saved", 3000)
            self._sync_ui()
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Save failed: {exc}")

    def _ask_save_path(self, title="Save PDF As"):
        suggestion = self.doc.path or os.path.join(self._last_dir(), "document.pdf")
        path, _ = QFileDialog.getSaveFileName(self, title, suggestion, PDF_FILTER)
        if path and not path.lower().endswith(".pdf"):
            path += ".pdf"
        return path

    def action_save_as(self):
        self.canvas.commit_edit()
        path = self._ask_save_path()
        if not path:
            return
        try:
            self.doc.save(path)
            self._remember_recent(path)
            self.statusBar().showMessage("Saved", 3000)
            self._sync_ui()
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Save failed: {exc}")

    def action_save_encrypted(self):
        self.canvas.commit_edit()
        dialog = PasswordDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        path = self._ask_save_path("Save Encrypted PDF As")
        if not path:
            return
        try:
            self.doc.save(path, user_pw=dialog.password())
            self.statusBar().showMessage("Saved with password protection", 4000)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Save failed: {exc}")

    def action_save_optimized(self):
        self.canvas.commit_edit()
        path = self._ask_save_path("Save Optimised PDF As")
        if not path:
            return
        try:
            before = os.path.getsize(self.doc.path) if self.doc.path and os.path.exists(self.doc.path) else 0
            self.doc.save(path, optimize=True)
            after = os.path.getsize(path)
            msg = "Saved (optimised)"
            if before:
                msg += f" — {before // 1024} KB → {after // 1024} KB"
            self.statusBar().showMessage(msg, 5000)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Save failed: {exc}")

    def action_insert_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Insert / Merge PDF",
                                              self._last_dir(), PDF_FILTER)
        if not path:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Insert PDF")
        box.setText(f"Where should the pages of\n{os.path.basename(path)}\ngo?")
        after = box.addButton("After current page", QMessageBox.AcceptRole)
        end = box.addButton("At the end", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        clicked = box.clickedButton()
        try:
            if clicked is after:
                count = self.doc.insert_pdf_file(path, at=self.canvas.current_page + 1)
            elif clicked is end:
                count = self.doc.insert_pdf_file(path)
            else:
                return
            self.statusBar().showMessage(f"Inserted {count} page(s)", 4000)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Insert failed: {exc}")

    def action_extract_pages(self):
        pages = self.thumbs.selected_pages() or [self.canvas.current_page]
        path, _ = QFileDialog.getSaveFileName(
            self, f"Extract {len(pages)} page(s) to…",
            os.path.join(self._last_dir(), "extracted.pdf"), PDF_FILTER)
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            self.doc.extract_pages(pages, path)
            self.statusBar().showMessage(f"Extracted {len(pages)} page(s)", 4000)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Extract failed: {exc}")

    def action_export_png(self):
        page = self.canvas.current_page
        path, _ = QFileDialog.getSaveFileName(
            self, "Export page as image",
            os.path.join(self._last_dir(), f"page-{page + 1}.png"),
            "PNG image (*.png);;JPEG image (*.jpg)")
        if not path:
            return
        try:
            self.doc.export_page_image(page, path, zoom=2.5)
            self.statusBar().showMessage("Page exported", 3000)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Export failed: {exc}")

    def action_export_text(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export document text",
            os.path.join(self._last_dir(), "document.txt"), "Text file (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                for i in range(self.doc.page_count):
                    fh.write(f"--- Page {i + 1} ---\n{self.doc.page_text(i)}\n")
            self.statusBar().showMessage("Text exported", 3000)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Export failed: {exc}")

    def action_properties(self):
        page = self.doc.page(self.canvas.current_page)
        info = (f"{self.doc.page_count} page(s) · current page "
                f"{page.rect.width:.0f} × {page.rect.height:.0f} pt")
        dialog = PropertiesDialog(self, self.doc.get_metadata(), info)
        if dialog.exec() == QDialog.Accepted:
            self.doc.set_metadata(dialog.values())
            self.statusBar().showMessage("Properties updated", 3000)

    def action_print(self):
        try:
            from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        except ImportError:
            QMessageBox.warning(self, APP_NAME, "Printing is unavailable in this build.")
            return
        from PySide6.QtGui import QPainter
        self.canvas.commit_edit()
        printer = QPrinter(QPrinter.HighResolution)
        if QPrintDialog(printer, self).exec() != QDialog.Accepted:
            return
        painter = QPainter(printer)
        try:
            for i in range(self.doc.page_count):
                if i:
                    printer.newPage()
                raw = self.doc.render(i, 2.0)
                image = QImage(raw.samples, raw.width, raw.height, raw.stride,
                               QImage.Format_RGB888).copy()
                target = painter.viewport()
                size = image.size()
                size.scale(target.size(), Qt.KeepAspectRatio)
                painter.drawImage(target.x(), target.y(),
                                  image.scaled(size, Qt.KeepAspectRatio,
                                               Qt.SmoothTransformation))
        finally:
            painter.end()
        self.statusBar().showMessage("Sent to printer", 4000)

    # ---------------------------------------------------------- page actions

    def _target_pages(self):
        return self.thumbs.selected_pages() or [self.canvas.current_page]

    def rotate_pages(self, delta: int):
        if self.doc.is_open():
            self.canvas.commit_edit()
            self.doc.rotate_pages(self._target_pages(), delta)

    def action_delete_pages(self):
        if not self.doc.is_open():
            return
        pages = self._target_pages()
        if len(pages) > 1:
            answer = QMessageBox.question(
                self, APP_NAME, f"Delete {len(pages)} pages?",
                QMessageBox.Yes | QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        try:
            self.doc.delete_pages(pages)
        except PdfError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))

    def move_page(self, src: int, dest: int):
        if self.doc.is_open():
            self.doc.move_page(src, dest)
            self.goto_page(dest)

    def move_page_by(self, delta: int):
        src = self.canvas.current_page
        dest = src + delta
        if 0 <= dest < self.doc.page_count:
            self.move_page(src, dest)

    def action_insert_blank(self):
        if self.doc.is_open():
            self.doc.insert_blank_page(self.canvas.current_page + 1,
                                       like=self.canvas.current_page)

    def action_page_numbers(self):
        dialog = PageNumbersDialog(self)
        if dialog.exec() == QDialog.Accepted:
            fmt, pos, start = dialog.values()
            try:
                self.doc.add_page_numbers(fmt=fmt, position=pos, start=start)
            except (KeyError, IndexError, ValueError) as exc:
                QMessageBox.warning(self, APP_NAME, f"That format string is not valid: {exc}")

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

    # ---------------------------------------------------------- edit actions

    def action_undo(self):
        self.canvas.cancel_edit()
        self.doc.undo()

    def action_redo(self):
        self.canvas.cancel_edit()
        self.doc.redo()

    def action_copy(self):
        text = self.canvas.selected_document_text()
        if not text and self.canvas.edit is not None:
            text = self.canvas.edit.selected_text()
        if not text:
            text = self.doc.page_text(self.canvas.current_page)
            self.statusBar().showMessage("Copied the whole page's text", 3000)
        QApplication.clipboard().setText(text)

    def action_select_all_text(self):
        if self.canvas.edit is not None:
            self.canvas.edit.select_all()
            self.canvas.update()
            return
        page = self.canvas.current_page
        try:
            words = self.doc.page(page).get_text("words")
        except Exception:
            return
        self.canvas.text_sel = [(page, fitz.Rect(w[:4])) for w in words]
        self.canvas.update()

    def action_delete_selection(self):
        if self.canvas.sel_annot is not None:
            index, xref = self.canvas.sel_annot
            self.canvas.clear_annot_selection()
            self.doc.delete_annot(index, xref)

    def action_find(self):
        self.side_dock.setVisible(True)
        self.side_tabs.setCurrentWidget(self.search_panel)
        self.search_panel.focus_entry()

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
        self.settings.setValue("recentFiles", recent[:12])
        self._rebuild_recent()

    def _rebuild_recent(self):
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
            QMessageBox.warning(self, APP_NAME, f"That file has moved or been deleted:\n{path}")
            return
        if self._confirm_discard():
            self.open_path(path)

    # ------------------------------------------------------------------ misc

    # ------------------------------------------------------ view and tools

    def set_view_mode(self, mode: str):
        self.canvas.commit_edit()
        self.canvas.set_view_mode(mode)
        action = {ViewMode.CONTINUOUS: self.act_view_continuous,
                  ViewMode.SINGLE: self.act_view_single,
                  ViewMode.FACING: self.act_view_facing}.get(mode)
        if action:
            action.setChecked(True)
        self.statusBar().showMessage(
            {ViewMode.CONTINUOUS: "Continuous scrolling",
             ViewMode.SINGLE: "One page at a time",
             ViewMode.FACING: "Two-page spread"}[mode], 3000)

    def toggle_night(self):
        on = self.act_night.isChecked()
        self.canvas.set_night_mode(on)
        self.statusBar().showMessage(
            "Night mode on — colours inverted for reading in the dark" if on
            else "Night mode off", 3000)

    def commit_stamp(self, index: int, point):
        try:
            self.doc.add_stamp(index, self.canvas.stamp_text, point,
                               fontsize=float(self.canvas.font_size) * 1.6,
                               rotate=0)
            self.statusBar().showMessage(f"Placed a {self.canvas.stamp_text} stamp", 3000)
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, f"Could not place the stamp: {exc}")

    def follow_link(self, index: int, link: dict) -> bool:
        """Act on a link the user clicked. Returns True if it was handled."""
        kind = link.get("kind")
        if kind == fitz.LINK_GOTO:
            target = link.get("page", 0)
            self.goto_page(int(target))
            return True
        uri = link.get("uri")
        if kind == fitz.LINK_URI and uri:
            answer = QMessageBox.question(
                self, "Open link",
                f"Open this address in your browser?\n\n{uri}",
                QMessageBox.Open | QMessageBox.Cancel)
            if answer == QMessageBox.Open:
                from PySide6.QtGui import QDesktopServices
                from PySide6.QtCore import QUrl
                QDesktopServices.openUrl(QUrl(uri))
            return True
        return False

    def choose_field_option(self, index: int, field):
        choice, ok = QInputDialog.getItem(
            self, field.label or "Choose", "Value:",
            [str(c) for c in field.choices],
            max(0, [str(c) for c in field.choices].index(str(field.value))
                if str(field.value) in [str(c) for c in field.choices] else 0),
            False)
        if ok:
            self.doc.set_field_value(index, field.name, choice)
            self.canvas.invalidate_cache(index)

    # -------------------------------------------------- document commands

    def action_split(self):
        if not self.doc.is_open():
            return
        dialog = SplitDialog(self, self.doc.page_count, bool(self.doc.get_toc()))
        if dialog.exec() != QDialog.Accepted:
            return
        mode, size, ranges = dialog.values()
        out_dir = QFileDialog.getExistingDirectory(
            self, "Where should the pieces go?", self._last_dir())
        if not out_dir:
            return
        stem = os.path.splitext(os.path.basename(self.doc.path or "document"))[0]
        try:
            written = self.doc.split_to_files(out_dir, mode=mode, size=size,
                                              ranges=ranges, stem=stem)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Split failed: {exc}")
            return
        QMessageBox.information(
            self, "Split complete",
            f"Wrote {len(written)} file(s) to:\n{out_dir}")

    def action_crop(self):
        if not self.doc.is_open():
            return
        self.set_tool(Tool.CROP)
        self.statusBar().showMessage(
            "Drag the area to keep — it is applied to the pages selected in the "
            "thumbnails, or the current page", 8000)

    def action_reset_crop(self):
        if self.doc.is_open():
            self.doc.reset_crop(self._target_pages())
            self.statusBar().showMessage("Crop reset", 3000)

    def action_images_to_pages(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choose images to add as pages", self._last_dir(), IMAGE_FILTER)
        if not paths:
            return
        added = self.doc.images_to_pages(paths, at=self.canvas.current_page + 1)
        self.statusBar().showMessage(f"Added {added} page(s) from images", 4000)

    def action_flatten_annots(self):
        if not self.doc.is_open():
            return
        if QMessageBox.question(
                self, "Flatten annotations",
                "This bakes every annotation into the page so it can no longer "
                "be selected or edited.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        count = self.doc.flatten_annotations()
        self.canvas.clear_annot_selection()
        self.statusBar().showMessage(f"Flattened {count} annotation(s)", 4000)

    def action_page_labels(self):
        dialog = PageLabelDialog(self)
        if dialog.exec() == QDialog.Accepted:
            style, prefix, start = dialog.values()
            if self.doc.set_page_numbering(style=style, prefix=prefix, start=start):
                self.statusBar().showMessage("Page labels updated", 3000)

    def action_attach(self):
        path, _ = QFileDialog.getOpenFileName(self, "Attach a file to this PDF",
                                              self._last_dir())
        if path and self.doc.attach_file(path):
            self.side_tabs.setCurrentWidget(self.attachments)
            self.attachments.populate()
            self.statusBar().showMessage(f"Attached {os.path.basename(path)}", 3000)

    def action_auto_bookmarks(self):
        self.side_tabs.setCurrentWidget(self.outline)
        self.outline._auto()

    def action_form_reset(self):
        if self.doc.is_open() and self.doc.has_form:
            self.side_tabs.setCurrentWidget(self.forms)
            self.forms._reset()
        else:
            self.statusBar().showMessage("This document has no form fields", 3000)

    def action_form_flatten(self):
        if self.doc.is_open() and self.doc.has_form:
            self.side_tabs.setCurrentWidget(self.forms)
            self.forms._flatten()
        else:
            self.statusBar().showMessage("This document has no form fields", 3000)

    def action_compress(self):
        """Reduce the file size, then show what it actually achieved."""
        if not self.doc.is_open():
            return
        self.canvas.commit_edit()
        self.canvas.commit_field()
        report = self.doc.image_report()
        dialog = CompressDialog(self, report)
        if dialog.exec() != QDialog.Accepted:
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.statusBar().showMessage("Compressing…")
        try:
            result = self.doc.compress(**dialog.values())
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, APP_NAME, f"Compression failed: {exc}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.canvas.invalidate_cache()
        self.thumbs.populate()

        if result.get("no_gain"):
            QMessageBox.information(
                self, "Nothing to reclaim",
                f"This file is already about as small as it gets "
                f"({human_size(result['before'])}), so it has been left alone.\n\n"
                + ("It contains no images, and text and vector graphics are already "
                   "compressed." if not result["did"].get("image_count")
                   else "Its images are already at or below the resolution you chose."))
            self.statusBar().showMessage("No saving available — document unchanged", 6000)
            return

        before, after = result["before"], result["after"]
        detail = []
        if result["did"].get("images"):
            detail.append(f"resampled {result['did'].get('image_count', 0)} image(s)")
        if result["did"].get("fonts"):
            detail.append(f"subset {result['did']['fonts']} font(s)")
        if result["did"].get("scrubbed"):
            detail.append("removed metadata and thumbnails")
        if result["did"].get("baked"):
            detail.append("flattened annotations")

        box = QMessageBox(self)
        box.setWindowTitle("File size reduced")
        box.setIcon(QMessageBox.Information)
        box.setText(f"<b>{human_size(before)} → {human_size(after)}</b><br>"
                    f"{result['ratio']:.0%} smaller "
                    f"({human_size(result['saved'])} saved)")
        box.setInformativeText(
            ("This " + ", ".join(detail) + ".\n\n" if detail else "")
            + "Look over the pages — if the quality is not good enough, choose "
              "Undo. Save the document to write the smaller file to disk.")
        keep = box.addButton("Keep", QMessageBox.AcceptRole)
        box.addButton("Undo", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not keep:
            self.doc.undo()
            self.canvas.invalidate_cache()
            self.statusBar().showMessage("Compression undone", 4000)
        else:
            self.statusBar().showMessage(
                f"{result['ratio']:.0%} smaller — save the document to keep it", 8000)

    def action_snapshot_file(self):
        image = QApplication.clipboard().image()
        if image.isNull():
            self.statusBar().showMessage(
                "Take a snapshot first with the Snapshot tool", 4000)
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save snapshot", os.path.join(self._last_dir(), "snapshot.png"),
            "PNG image (*.png)")
        if path:
            image.save(path)
            self.statusBar().showMessage("Snapshot saved", 3000)

    def action_about(self):
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>A free PDF editor — view, edit text in place, annotate, "
            "reorganise pages, redact and protect.</p>"
            "<p style='color:#888'>Built with Qt (PySide6) and MuPDF. "
            "The text layout and editing engine is written from scratch for "
            "this application.</p>")

    def action_shortcuts(self):
        QMessageBox.information(
            self, "Keyboard shortcuts",
            "<table cellpadding=5>"
            "<tr><td><b>Ctrl+O / Ctrl+S</b></td><td>Open / Save</td></tr>"
            "<tr><td><b>Ctrl+Z / Ctrl+Shift+Z</b></td><td>Undo / Redo</td></tr>"
            "<tr><td><b>Ctrl+F / F3</b></td><td>Find / find next</td></tr>"
            "<tr><td><b>Ctrl+B / Ctrl+I</b></td><td>Bold / italic while editing text</td></tr>"
            "<tr><td><b>Esc</b></td><td>Finish editing a text block</td></tr>"
            "<tr><td><b>PgUp / PgDown</b></td><td>Previous / next page</td></tr>"
            "<tr><td><b>Ctrl++ / Ctrl+- / Ctrl+0</b></td><td>Zoom in / out / 100%</td></tr>"
            "<tr><td><b>Ctrl+1 / Ctrl+2</b></td><td>Fit width / fit page</td></tr>"
            "<tr><td><b>Ctrl+scroll</b></td><td>Zoom around the pointer</td></tr>"
            "<tr><td><b>Space+drag</b> or middle-drag</td><td>Pan</td></tr>"
            "<tr><td><b>Del</b></td><td>Delete the selected object</td></tr>"
            "<tr><td><b>F9 / F10</b></td><td>Toggle sidebar / properties</td></tr>"
            "</table>")

    def _confirm_discard(self) -> bool:
        self.canvas.commit_edit()
        if not (self.doc.is_open() and self.doc.dirty):
            return True
        answer = QMessageBox.question(
            self, APP_NAME, "This document has unsaved changes. Save them first?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if answer == QMessageBox.Save:
            self.action_save()
            return not self.doc.dirty
        return answer == QMessageBox.Discard

    def closeEvent(self, event):
        event.accept() if self._confirm_discard() else event.ignore()

    def dragEnterEvent(self, event):
        if any(u.toLocalFile().lower().endswith(".pdf") for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                if self._confirm_discard():
                    self.open_path(path)
                break
