#!/usr/bin/env python3
"""Offscreen GUI test — drives the real window with synthesized input.

Run: QT_QPA_PLATFORM=offscreen python tests/test_gui.py [screenshot.png]
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# The custom window frame defaults off on macOS (deliberate policy). Force it
# on for the test run so the frame is exercised identically on every CI OS.
os.environ["PDFSTUDIO_NATIVE_FRAME"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fitz
from PySide6.QtCore import QEvent, QPoint, QPointF, QEventLoop, Qt, QTimer
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from pdfstudio import theme
from pdfstudio.canvas import Tool
from pdfstudio.main_window import MainWindow
from test_compress import build_heavy, make_photo
from test_features import build_form
from test_textengine import TMP, build


def pump(ms=120):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def click(widget, pos, kind=QEvent.MouseButtonPress, buttons=Qt.LeftButton):
    event = QMouseEvent(kind, QPointF(pos), QPointF(widget.mapToGlobal(pos)),
                        Qt.LeftButton, buttons, Qt.NoModifier)
    QApplication.sendEvent(widget, event)


def drag(widget, start, end, steps=3):
    click(widget, start, QEvent.MouseButtonPress)
    for i in range(1, steps + 1):
        mid = QPoint(int(start.x() + (end.x() - start.x()) * i / steps),
                     int(start.y() + (end.y() - start.y()) * i / steps))
        click(widget, mid, QEvent.MouseMove, Qt.LeftButton)
    click(widget, end, QEvent.MouseButtonRelease, Qt.NoButton)


def key(widget, code, text="", mods=Qt.NoModifier):
    QApplication.sendEvent(widget, QKeyEvent(QEvent.KeyPress, code, mods, text))


def type_text(widget, text):
    for ch in text:
        key(widget, Qt.Key_A if ch.isalpha() else Qt.Key_Space, ch)


def canvas_point(canvas, page, x, y):
    pt = canvas.to_canvas(page, fitz.Point(x, y))
    return QPoint(int(pt.x()), int(pt.y()))


def main():
    shot = sys.argv[1] if len(sys.argv) > 1 else None
    app = QApplication.instance() or QApplication([])
    theme.apply(app)
    win = MainWindow()
    win.resize(1440, 920)
    win.show()
    canvas = win.canvas

    src = build(os.path.join(TMP, "gui.pdf"))
    win.open_path(src)
    pump(250)
    assert win.doc.is_open() and win.doc.page_count == 1
    assert canvas.slots, "canvas produced no page layout"
    print("open + continuous layout: ok")

    # ---------------------------------------------------- inline text editing
    win.set_tool(Tool.EDIT_TEXT)
    target = canvas_point(canvas, 0, 120, 86)          # inside "Quarterly Report"
    click(canvas, target, QEvent.MouseButtonPress)
    click(canvas, target, QEvent.MouseButtonRelease, Qt.NoButton)
    pump()
    assert canvas.edit is not None, "clicking text did not start an edit session"
    assert canvas.edit.text == "Quarterly Report", repr(canvas.edit.text)
    caret_before = canvas.edit.caret
    print(f"click into text -> caret at {caret_before}: ok")

    # type at the caret
    canvas.edit.set_caret(9)
    for ch in " Q3":
        key(canvas, Qt.Key_unknown, ch)
    pump()
    assert canvas.edit.text == "Quarterly Q3 Report", repr(canvas.edit.text)
    print("typing inserts at the caret: ok")

    # backspace + arrow keys + shift-selection
    key(canvas, Qt.Key_Backspace)
    assert canvas.edit.text == "Quarterly Q Report"
    key(canvas, Qt.Key_Left)
    key(canvas, Qt.Key_Right, mods=Qt.ShiftModifier)
    assert canvas.edit.selection_range() is not None, "shift+arrow made no selection"
    key(canvas, Qt.Key_Home)
    assert canvas.edit.caret == 0
    print("keyboard editing (backspace/arrows/shift/home): ok")

    # bold toggle through the shortcut path
    canvas.edit.select_all()
    was_bold = canvas.edit.style_at(0).font.bold
    key(canvas, Qt.Key_I, mods=Qt.ControlModifier)
    pump()
    assert canvas.edit.style_at(0).font.italic != (not True), "ctrl+I did nothing"
    print("ctrl+I styling: ok")

    # Esc commits into the document
    canvas.edit.set_caret(0)
    key(canvas, Qt.Key_Escape)
    pump(200)
    assert canvas.edit is None, "Esc did not close the editor"
    page_text = win.doc.page_text(0)
    assert "Quarterly Q Report" in page_text, page_text[:160]
    print("Esc commits the edit into the PDF: ok")

    # ------------------------------------------------------ drag a text block
    click(canvas, canvas_point(canvas, 0, 120, 86), QEvent.MouseButtonPress)
    click(canvas, canvas_point(canvas, 0, 120, 86), QEvent.MouseButtonRelease, Qt.NoButton)
    pump()
    assert canvas.edit is not None
    handles = canvas.edit_handles()
    bar = handles["move"].center().toPoint()
    origin_x, origin_y = canvas.edit.x, canvas.edit.y
    drag(canvas, bar, QPoint(bar.x() + 90, bar.y() + 140))
    pump()
    assert canvas.edit.x > origin_x + 20, "block did not move horizontally"
    assert canvas.edit.y > origin_y + 40, "block did not move vertically"
    moved_to = (canvas.edit.x, canvas.edit.y)
    key(canvas, Qt.Key_Escape)
    pump(200)
    found = win.doc.editable_at(0, fitz.Point(moved_to[0] + 30, moved_to[1] + 12))
    assert found is not None and "Report" in found.text, "moved text not at its new home"
    print("drag text block to a new position: ok")

    # -------------------------------------------------------- drawing + select
    win.set_tool(Tool.RECT)
    drag(canvas, canvas_point(canvas, 0, 90, 420), canvas_point(canvas, 0, 300, 500))
    pump(150)
    page0 = win.doc.page(0)
    assert len(list(page0.annots())) == 1, "rectangle was not created"
    print("draw rectangle: ok")

    win.set_tool(Tool.SELECT)
    click(canvas, canvas_point(canvas, 0, 200, 460), QEvent.MouseButtonPress)
    click(canvas, canvas_point(canvas, 0, 200, 460), QEvent.MouseButtonRelease, Qt.NoButton)
    pump()
    assert canvas.sel_annot is not None, "clicking the shape did not select it"
    before = fitz.Rect(canvas.sel_rect)
    drag(canvas, canvas_point(canvas, 0, 200, 460), canvas_point(canvas, 0, 260, 520))
    pump(150)
    after = win.doc.annot_rect(0, canvas.sel_annot[1])
    assert after.x0 > before.x0 + 20, f"annotation did not move: {before} -> {after}"
    print("select + drag annotation: ok")

    handles = canvas.annot_handles()
    grip = handles["se"].center().toPoint()
    drag(canvas, grip, QPoint(grip.x() + 60, grip.y() + 40))
    pump(150)
    resized = win.doc.annot_rect(0, canvas.sel_annot[1])
    assert resized.width > after.width + 15, "resize handle did not enlarge the shape"
    print("resize annotation by its handle: ok")

    win.action_delete_selection()
    pump(150)
    assert len(list(win.doc.page(0).annots())) == 0, "annotation was not deleted"
    print("delete annotation: ok")

    # ------------------------------------------------------------- highlight
    win.set_tool(Tool.HIGHLIGHT)
    drag(canvas, canvas_point(canvas, 0, 74, 176), canvas_point(canvas, 0, 300, 186))
    pump(150)
    kinds = [a.type[1] for a in win.doc.page(0).annots()]
    assert any("Highlight" in k for k in kinds), f"no highlight created: {kinds}"
    print("highlight over text: ok")

    # ---------------------------------------------------------------- search
    win.action_find()
    win.search_panel.entry.setText("Revenue")
    win.search_panel.run()
    pump(150)
    assert win.search_panel.results, "search found nothing"
    assert canvas.search_hits, "search hits not passed to the canvas"
    print(f"search: {len(win.search_panel.results)} hit(s): ok")
    win.search_panel.clear()

    # ------------------------------------------------------------ zoom & nav
    win.set_zoom_mode(1.0)
    assert abs(canvas.zoom - 1.0) < 0.01
    win.zoom_step(1)
    assert canvas.zoom > 1.0
    win.set_zoom_mode("width")
    assert canvas.fit_mode == "width"
    pump(150)
    print("zoom modes: ok")

    win.doc.insert_blank_page(1, like=0)
    pump(200)
    assert win.doc.page_count == 2 and len(canvas.slots) == 2
    win.goto_page(1)
    pump(150)
    assert canvas.current_page == 1
    win.action_undo()
    pump(200)
    print("multi-page layout + navigation: ok")

    # --------------------------------------------------------- new text box
    win.set_tool(Tool.TEXT)
    drag(canvas, canvas_point(canvas, 0, 90, 600), canvas_point(canvas, 0, 380, 640))
    pump()
    assert canvas.edit is not None, "text tool did not open an editor"
    for ch in "Hello":
        key(canvas, Qt.Key_unknown, ch)
    key(canvas, Qt.Key_Escape)
    pump(200)
    assert "Hello" in win.doc.page_text(0), "new text box was not written"
    print("new text box via drag: ok")

    # ----------------------------------------------------------- view modes
    from pdfstudio.canvas import ViewMode
    win.doc.insert_blank_page(1, like=0)
    win.doc.insert_blank_page(2, like=0)
    pump(200)
    win.set_view_mode(ViewMode.SINGLE)
    pump(150)
    assert len(canvas.slots) == 1, f"single mode laid out {len(canvas.slots)} pages"
    win.goto_page(1)
    pump(150)
    assert canvas.slots[0].index == 1, "single mode did not follow the page change"

    win.set_view_mode(ViewMode.FACING)
    pump(150)
    assert len(canvas.slots) == 2, f"facing mode laid out {len(canvas.slots)} pages"
    left, right = canvas.slots[0], canvas.slots[1]
    assert right.left > left.left, "facing pages are not side by side"
    assert abs(left.top - right.top) < 1, "facing pages are not level"

    win.set_view_mode(ViewMode.CONTINUOUS)
    pump(150)
    assert len(canvas.slots) == win.doc.page_count
    print("view modes single / facing / continuous: ok")

    canvas.set_night_mode(True)
    pump(150)
    dark = canvas.pixmap_for(0).toImage().pixelColor(4, 4)
    canvas.set_night_mode(False)
    pump(150)
    light = canvas.pixmap_for(0).toImage().pixelColor(4, 4)
    assert dark != light, "night mode did not change the rendering"
    assert dark.lightness() < light.lightness(), "night mode did not darken the page"
    print("night mode inverts the page: ok")

    win.doc.undo(); win.doc.undo()
    pump(200)

    # ------------------------------------------------------------- snapshot
    image = canvas.take_snapshot(0, fitz.Rect(60, 70, 320, 130))
    assert not image.isNull() and image.width() > 100, "snapshot produced nothing"
    assert not QApplication.clipboard().image().isNull(), "snapshot not on the clipboard"
    print(f"snapshot to clipboard ({image.width()}x{image.height()}): ok")

    # ---------------------------------------------------------------- stamp
    win.canvas.stamp_text = "APPROVED"
    win.commit_stamp(0, fitz.Point(300, 640))
    pump(150)
    assert "APPROVED" in win.doc.page_text(0), "stamp text not on the page"
    print("stamp placement: ok")
    win.doc.undo()

    # ------------------------------------------------------------- comments
    win.doc.add_note(0, fitz.Point(420, 240), "Reviewer note")
    pump(150)
    win.side_tabs.setCurrentWidget(win.comments)
    win.comments.populate()
    pump(150)
    assert win.comments.list.count() >= 1, "comments panel is empty"
    win.comments.list.setCurrentRow(win.comments.list.count() - 1)
    assert win.comments._current() is not None
    win.comments.note.setPlainText("Edited via the panel")
    win.comments._save_note()
    pump(150)
    assert any(a["content"] == "Edited via the panel"
               for a in win.doc.all_annotations()), "comment edit did not stick"
    print("comments panel lists and edits: ok")

    # ------------------------------------------------------------ bookmarks
    win.doc.set_toc([[1, "First", 1]])
    win.side_tabs.setCurrentWidget(win.outline)
    win.outline.populate()
    pump(150)
    assert win.outline.tree.topLevelItemCount() == 1
    win.doc.add_bookmark("Second", page=0)
    win.outline.populate()
    assert win.outline.tree.topLevelItemCount() == 2, "bookmarks panel did not refresh"
    print("bookmarks panel: ok")

    # ---------------------------------------------------------------- forms
    win2 = MainWindow()
    win2.resize(1400, 900)
    win2.show()
    win2.open_path(build_form(os.path.join(TMP, "gui-form.pdf")))
    pump(300)
    assert win2.doc.has_form
    win2.side_tabs.setCurrentWidget(win2.forms)
    win2.forms.populate()
    pump(150)
    assert win2.forms.list.count() == 3, win2.forms.list.count()

    win2.set_tool(Tool.SELECT)
    assert win2.doc.field_at(0, fitz.Point(200, 106)) is not None
    target = canvas_point(win2.canvas, 0, 200, 106)
    click(win2.canvas, target, QEvent.MouseButtonPress)
    click(win2.canvas, target, QEvent.MouseButtonRelease, Qt.NoButton)
    pump(150)
    assert win2.canvas.active_field is not None, "clicking a field did not focus it"
    for ch in "Grace":
        key(win2.canvas, Qt.Key_unknown, ch)
    key(win2.canvas, Qt.Key_Return)
    pump(200)
    values = {f.name: f.value for f in win2.doc.form_fields()}
    assert values["fullname"] == "Grace", values
    print("click a form field and type into it: ok")

    box = win2.doc.field_at(0, fitz.Point(168, 147))
    assert box is not None and box.name == "subscribe", box
    spot = canvas_point(win2.canvas, 0, 168, 147)
    click(win2.canvas, spot, QEvent.MouseButtonPress)
    click(win2.canvas, spot, QEvent.MouseButtonRelease, Qt.NoButton)
    pump(200)
    assert {f.name: f.checked for f in win2.doc.form_fields()}["subscribe"], \
        "clicking the checkbox did not tick it"
    print("tick a checkbox by clicking it: ok")

    win2.forms.populate()
    listed = " ".join(win2.forms.list.item(i).text()
                      for i in range(win2.forms.list.count()))
    assert "Grace" in listed, listed
    print("form panel reflects canvas edits: ok")

    # ------------------------------------------------------------- compress
    from pdfstudio.dialogs import CompressDialog, human_size
    assert human_size(2500000).endswith("MB") and human_size(2048) == "2 KB"
    photo = make_photo(os.path.join(TMP, "gui-photo.png"), 900, 650)
    heavy = build_heavy(os.path.join(TMP, "gui-heavy.pdf"), photo, pages=2)
    win3 = MainWindow()
    win3.resize(1200, 800)
    win3.show()
    win3.open_path(heavy)
    pump(300)
    rep = win3.doc.image_report()
    assert rep["count"] >= 1 and rep["share"] > 0.4, rep
    dlg = CompressDialog(win3, rep)
    assert dlg.preset.currentData() == "balanced"
    opts = dlg.values()
    before = win3.doc.measure_size()
    result = win3.doc.compress(**opts)
    pump(200)
    assert result["after"] < before, result
    assert result["ratio"] > 0.3, result
    # the canvas must still render the compressed pages
    win3.canvas.invalidate_cache()
    pump(200)
    assert win3.canvas.pixmap_for(0) is not None, "compressed page failed to render"
    assert "Section 1" in win3.doc.page_text(0), "compression damaged the text"
    print(f"compress via UI: {human_size(before)} -> {human_size(result['after'])}"
          f" ({result['ratio']:.0%} smaller), page still renders: ok")
    win3.doc.undo()
    pump(200)
    assert win3.doc.measure_size() > result["after"] * 2, "undo did not restore"
    print("undo after compress restores the original: ok")

    # ---------------------------------------------------- custom window frame
    import sys as _sys
    from pdfstudio.titlebar import position_grips, use_custom_frame
    assert use_custom_frame(), "env override should force the custom frame"
    # the platform policy itself, checked as pure logic (no window needed):
    _forced = os.environ.pop("PDFSTUDIO_NATIVE_FRAME")
    assert use_custom_frame() == (_sys.platform != "darwin"), \
        "default should be custom frame everywhere except macOS"
    os.environ["PDFSTUDIO_NATIVE_FRAME"] = _forced
    assert win.use_custom_frame and win.title_bar is not None
    assert bool(win.windowFlags() & Qt.FramelessWindowHint), "window is not frameless"
    assert len(win.grips) == 8, "expected eight resize grips"
    titles = [a.text() for a in win.menu_bar.actions()]
    assert titles == ["&File", "&Edit", "&Tools", "&Pages", "&Document",
                      "&View", "&Help"], titles
    print("custom frame: frameless window, menus in the title bar: ok")

    # title reflects the document and its modified state
    win.title_bar.refresh_title()
    assert "PDF Studio" in win.title_bar._full_title
    win.doc.dirty = True
    win._sync_ui()
    assert "●" in win.title_bar._full_title, win.title_bar._full_title
    win.doc.dirty = False
    win._sync_ui()
    assert "●" not in win.title_bar._full_title
    print("title bar shows the modified dot: ok")

    # maximise toggle + button glyph state + grip visibility
    win.title_bar.toggle_max_restore()
    pump(150)
    assert win.isMaximized(), "toggle did not maximise"
    assert win.title_bar.btn_max.restore_mode, "max button did not flip to restore"
    assert all(not g.isVisible() for g in win.grips), "grips visible while maximised"
    win.title_bar.toggle_max_restore()
    pump(150)
    assert not win.isMaximized()
    assert not win.title_bar.btn_max.restore_mode
    assert all(g.isVisible() for g in win.grips), "grips hidden after restore"
    print("maximise/restore via the custom button: ok")

    # grips hug the window edges after a resize
    win.resize(1100, 760)
    pump(120)
    position_grips(win, win.grips)
    right = next(g for g in win.grips if g.edges == Qt.RightEdge
                 and not (g.edges & Qt.TopEdge) and not (g.edges & Qt.BottomEdge))
    assert abs((right.x() + right.width()) - win.width()) <= 1, \
        f"right grip not on the edge: {right.geometry()} vs width {win.width()}"
    print("resize grips track the window edges: ok")

    # manual resize fallback (the path used when startSystemResize is refused)
    os.environ["PDFSTUDIO_FORCE_MANUAL_RESIZE"] = "1"
    try:
        start_w = win.width()
        grip_centre = right.rect().center()
        gpos = right.mapToGlobal(grip_centre)
        press = QMouseEvent(QEvent.MouseButtonPress, QPointF(grip_centre),
                            QPointF(gpos), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(right, press)
        move = QMouseEvent(QEvent.MouseMove, QPointF(grip_centre.x() + 90, grip_centre.y()),
                           QPointF(gpos.x() + 90, gpos.y()),
                           Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(right, move)
        release = QMouseEvent(QEvent.MouseButtonRelease, QPointF(grip_centre),
                              QPointF(gpos.x() + 90, gpos.y()),
                              Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
        QApplication.sendEvent(right, release)
        pump(120)
        assert win.width() >= start_w + 80, \
            f"manual resize fallback did not grow the window: {start_w} -> {win.width()}"
        print(f"manual edge-resize fallback ({start_w} -> {win.width()}px): ok")
    finally:
        os.environ.pop("PDFSTUDIO_FORCE_MANUAL_RESIZE", None)

    # close button actually closes (clean document, no prompt)
    probe = MainWindow()
    probe.show()
    pump(100)
    assert probe.title_bar is not None
    probe.title_bar.btn_close.click()
    pump(150)
    assert not probe.isVisible(), "close button did not close the window"
    print("close button closes the window: ok")

    # the escape hatch restores the native frame
    os.environ["PDFSTUDIO_NATIVE_FRAME"] = "1"
    try:
        native = MainWindow()
        assert not native.use_custom_frame and native.title_bar is None
        assert not bool(native.windowFlags() & Qt.FramelessWindowHint)
        assert native.menuBar() is native.menu_bar, "native mode lost the menu bar"
        native.close()
    finally:
        os.environ["PDFSTUDIO_NATIVE_FRAME"] = "0"
    print("PDFSTUDIO_NATIVE_FRAME escape hatch: ok")

    if shot:
        win.set_tool(Tool.EDIT_TEXT)
        pump(400)
        win.grab().save(shot)
        print(f"screenshot: {shot}")

    print("\nALL GUI TESTS PASSED")


if __name__ == "__main__":
    main()
