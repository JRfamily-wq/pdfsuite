#!/usr/bin/env python3
"""Offscreen GUI test — drives the real window with synthesized input.

Run: QT_QPA_PLATFORM=offscreen python tests/test_gui.py [screenshot.png]
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fitz
from PySide6.QtCore import QEvent, QPoint, QPointF, QEventLoop, Qt, QTimer
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from pdfstudio import theme
from pdfstudio.canvas import Tool
from pdfstudio.main_window import MainWindow
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

    if shot:
        win.set_tool(Tool.EDIT_TEXT)
        pump(400)
        win.grab().save(shot)
        print(f"screenshot: {shot}")

    print("\nALL GUI TESTS PASSED")


if __name__ == "__main__":
    main()
