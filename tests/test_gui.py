#!/usr/bin/env python3
"""Offscreen GUI smoke test. Run: QT_QPA_PLATFORM=offscreen python tests/test_gui.py [shot.png]

Exercises the window against a real document without any dialogs:
tools that draw directly, navigation, zoom, find, undo, annotation selection.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz
from PySide6.QtWidgets import QApplication

from test_document import TMP, make_sample
from pdfstudio.main_window import MainWindow
from pdfstudio.page_view import Tool


def wait(app, ms=250):
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main():
    shot = sys.argv[1] if len(sys.argv) > 1 else None
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.resize(1280, 860)
    window.show()

    sample = make_sample(os.path.join(TMP, "gui-sample.pdf"))
    window.open_path(sample)
    wait(app)
    assert window.doc.is_open() and window.doc.page_count == 3
    assert window.view._pixmap is not None, "page did not render"
    print("open+render: ok")

    # navigation & zoom
    window.goto_page(1)
    assert window.current_page == 1
    window.goto_page(0)
    window.zoom_steps(1)
    window.zoom_steps(-1)
    window.fit_page()
    window.fit_width()
    wait(app)
    print("nav/zoom: ok")

    # direct tool commits (no dialogs)
    window.set_tool(Tool.RECT)
    window.commit_rubber(Tool.RECT, fitz.Rect(100, 300, 260, 380))
    window.commit_rubber(Tool.HIGHLIGHT, fitz.Rect(70, 90, 180, 110))
    window.commit_line(Tool.ARROW, fitz.Point(120, 420), fitz.Point(320, 470))
    window.commit_ink([(100, 500), (150, 530), (200, 490), (260, 540)])
    wait(app)
    assert len(list(window.doc.page(0).annots())) == 4
    print("tool commits: ok")

    # selection + delete via UI path
    assert window.select_annot_at(fitz.Point(180, 340))
    window.delete_selected_annot()
    wait(app)
    assert len(list(window.doc.page(0).annots())) == 3
    print("select/delete annotation: ok")

    # whiteout + undo through actions
    window.commit_rubber(Tool.WHITEOUT, fitz.Rect(60, 80, 200, 120))
    assert not window.doc.search_page(0, "PAGE-1")
    window.action_undo()
    assert window.doc.search_page(0, "PAGE-1")
    print("whiteout+undo: ok")

    # find
    window.find_bar_show()
    window._find("PAGE-3", False)
    wait(app)
    assert window.current_page == 2, "find did not jump to page 3"
    window.find_bar.hide_bar()
    window.goto_page(0)
    print("find: ok")

    # synthesized mouse drag with the rectangle tool (full event path)
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    def send_mouse(widget, kind, pos, buttons=Qt.LeftButton):
        event = QMouseEvent(kind, QPointF(pos),
                            QPointF(widget.mapToGlobal(pos)),
                            Qt.LeftButton, buttons, Qt.NoModifier)
        QApplication.sendEvent(widget, event)

    window.set_tool(Tool.RECT)
    before = len(list(window.doc.page(0).annots()))
    start, end = QPoint(120, 120), QPoint(260, 220)
    expected = window.view.to_page_rect(
        __import__("PySide6.QtCore", fromlist=["QRect"]).QRect(start, end))
    send_mouse(window.view, QEvent.MouseButtonPress, start)
    send_mouse(window.view, QEvent.MouseMove, QPoint(200, 180))
    send_mouse(window.view, QEvent.MouseMove, end)
    send_mouse(window.view, QEvent.MouseButtonRelease, end, buttons=Qt.NoButton)
    wait(app)
    page0 = window.doc.page(0)  # annots must not outlive their page
    annots = list(page0.annots())
    assert len(annots) == before + 1, "mouse drag did not create an annotation"
    got = annots[-1].rect
    assert abs(got.x0 - expected.x0) < 6 and abs(got.y0 - expected.y0) < 6, \
        f"annotation landed at {got}, expected near {expected}"
    print("mouse drag -> rectangle: ok")

    # page ops through window paths
    window.rotate_pages(90)
    assert window.doc.page(0).rotation == 90
    window.action_undo()
    window.move_page_by(1)
    assert window.doc.page_text(1).find("PAGE-1") >= 0
    window.action_undo()
    wait(app, 600)  # let thumbnails render

    if shot:
        window.grab().save(shot)
        print(f"screenshot: {shot}")

    print("\nALL GUI TESTS PASSED")


if __name__ == "__main__":
    main()
