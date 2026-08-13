"""Toolbar/window icons drawn at runtime with QPainter — no binary assets."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QIcon, QPainter, QPainterPath, QPen,
                           QPixmap, QPolygonF, QTransform)

INK = QColor(70, 74, 82)
ACCENT = QColor(200, 40, 40)


def _painter(size: int = 24):
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    return pix, painter


def _pen(color=INK, width=1.8):
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 32, 64, 128, 256):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        margin = size * 0.06
        rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(198, 40, 40))
        painter.drawRoundedRect(rect, size * 0.18, size * 0.18)
        painter.setPen(QColor("white"))
        font = QFont("Arial", int(size * 0.34), QFont.Bold)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, "PDF")
        painter.end()
        icon.addPixmap(pix)
    return icon


def tool_icon(name: str) -> QIcon:
    pix, p = _painter()
    p.setPen(_pen())
    p.setBrush(Qt.NoBrush)

    if name == "select":
        path = QPainterPath(QPointF(7, 4))
        for pt in [(7, 18), (11, 14.5), (14, 20), (16.2, 18.8), (13.4, 13.4), (18, 13)]:
            path.lineTo(QPointF(*pt))
        path.closeSubpath()
        p.setBrush(QColor(INK))
        p.drawPath(path)

    elif name == "text":
        font = QFont("Georgia", 13, QFont.Bold)
        p.setFont(font)
        p.drawText(QRectF(0, 0, 24, 24), Qt.AlignCenter, "T")
        p.drawLine(QPointF(5, 20.5), QPointF(19, 20.5))

    elif name == "edittext":
        font = QFont("Georgia", 12, QFont.Bold)
        p.setFont(font)
        p.drawText(QRectF(1, 1, 16, 20), Qt.AlignCenter, "A")
        p.setPen(_pen(ACCENT, 2.0))
        p.drawLine(QPointF(13, 18), QPointF(20, 11))
        p.drawLine(QPointF(20, 11), QPointF(21.5, 12.5))
        p.drawLine(QPointF(21.5, 12.5), QPointF(14.5, 19.5))

    elif name == "highlight":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 214, 0, 170))
        p.drawRect(QRectF(4, 9, 16, 8))
        p.setPen(_pen())
        p.drawLine(QPointF(4, 6), QPointF(20, 6))
        p.drawLine(QPointF(4, 20), QPointF(20, 20))

    elif name == "rect":
        p.drawRect(QRectF(4.5, 6.5, 15, 11))

    elif name == "ellipse":
        p.drawEllipse(QRectF(4.5, 6, 15, 12))

    elif name == "line":
        p.drawLine(QPointF(5, 19), QPointF(19, 5))

    elif name == "arrow":
        p.drawLine(QPointF(5, 19), QPointF(18, 6))
        p.drawLine(QPointF(18, 6), QPointF(12.5, 7.5))
        p.drawLine(QPointF(18, 6), QPointF(16.5, 11.5))

    elif name == "ink":
        path = QPainterPath(QPointF(4, 17))
        path.cubicTo(QPointF(8, 6), QPointF(11, 22), QPointF(15, 10))
        path.cubicTo(QPointF(17, 5), QPointF(19, 9), QPointF(20, 7))
        p.drawPath(path)

    elif name == "whiteout":
        p.setBrush(QColor("white"))
        p.drawRect(QRectF(4.5, 6.5, 15, 11))
        p.setPen(_pen(QColor(160, 164, 170), 1.2))
        p.drawLine(QPointF(7, 12), QPointF(17, 12))

    elif name == "redact":
        p.setBrush(QColor(30, 30, 34))
        p.drawRect(QRectF(4.5, 6.5, 15, 11))

    elif name == "image":
        p.drawRect(QRectF(4, 5.5, 16, 13))
        p.setBrush(QColor(INK))
        p.drawEllipse(QRectF(7, 8, 3, 3))
        path = QPainterPath(QPointF(5.5, 17.5))
        path.lineTo(QPointF(10.5, 12))
        path.lineTo(QPointF(13.5, 15))
        path.lineTo(QPointF(16.5, 11.5))
        path.lineTo(QPointF(19, 17.5))
        path.closeSubpath()
        p.drawPath(path)

    elif name == "note":
        p.drawRoundedRect(QRectF(4, 5, 16, 12), 2.5, 2.5)
        path = QPainterPath(QPointF(9, 17))
        path.lineTo(QPointF(8, 21))
        path.lineTo(QPointF(12.5, 17))
        p.setBrush(QColor(INK))
        p.drawPath(path)

    elif name == "zoom-in" or name == "zoom-out":
        p.drawEllipse(QRectF(4.5, 4.5, 11, 11))
        p.drawLine(QPointF(14.2, 14.2), QPointF(19.5, 19.5))
        p.drawLine(QPointF(7.5, 10), QPointF(12.5, 10))
        if name == "zoom-in":
            p.drawLine(QPointF(10, 7.5), QPointF(10, 12.5))

    elif name == "fit-width":
        p.drawRect(QRectF(4, 5, 16, 14))
        p.setPen(_pen(ACCENT, 1.6))
        p.drawLine(QPointF(6.5, 12), QPointF(17.5, 12))
        p.drawLine(QPointF(6.5, 12), QPointF(9, 9.5))
        p.drawLine(QPointF(6.5, 12), QPointF(9, 14.5))
        p.drawLine(QPointF(17.5, 12), QPointF(15, 9.5))
        p.drawLine(QPointF(17.5, 12), QPointF(15, 14.5))

    elif name == "fit-page":
        p.drawRect(QRectF(4, 4, 16, 16))
        p.setPen(_pen(ACCENT, 1.6))
        p.drawRect(QRectF(8, 8, 8, 8))

    elif name == "undo" or name == "redo":
        path = QPainterPath(QPointF(6, 10))
        path.cubicTo(QPointF(9, 6.5), QPointF(15, 6.5), QPointF(18, 10))
        path.cubicTo(QPointF(19.5, 12), QPointF(19.5, 14.5), QPointF(18, 16.5))
        p.drawPath(path)
        p.setBrush(QColor(INK))
        arrow = QPolygonF([QPointF(6, 10), QPointF(5, 5), QPointF(11, 7)])
        p.drawPolygon(arrow)
        p.end()
        if name == "redo":
            return QIcon(pix.transformed(QTransform(-1, 0, 0, 1, 0, 0)))
        return QIcon(pix)

    elif name == "open":
        p.drawRect(QRectF(4, 8, 16, 11))
        p.drawLine(QPointF(4, 8), QPointF(9, 8))
        p.drawLine(QPointF(9, 8), QPointF(11, 5.5))
        p.drawLine(QPointF(11, 5.5), QPointF(16, 5.5))
        p.drawLine(QPointF(16, 5.5), QPointF(16, 8))

    elif name == "save":
        p.drawRoundedRect(QRectF(4.5, 4.5, 15, 15), 1.5, 1.5)
        p.drawRect(QRectF(8, 4.5, 8, 5.5))
        p.drawRect(QRectF(7.5, 13, 9, 6.5))

    elif name == "new":
        p.drawRect(QRectF(6, 4, 12, 16))
        p.setPen(_pen(ACCENT, 1.8))
        p.drawLine(QPointF(12, 9), QPointF(12, 15))
        p.drawLine(QPointF(9, 12), QPointF(15, 12))

    elif name == "print":
        p.drawRect(QRectF(6, 4, 12, 5))
        p.drawRoundedRect(QRectF(4, 9, 16, 8), 1.5, 1.5)
        p.drawRect(QRectF(7, 14, 10, 6))

    elif name == "find":
        p.drawEllipse(QRectF(4.5, 4.5, 11, 11))
        p.drawLine(QPointF(14.2, 14.2), QPointF(19.5, 19.5))

    p.end()
    return QIcon(pix)


def color_swatch(color) -> QIcon:
    pix = QPixmap(24, 24)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(_pen(QColor(120, 120, 126), 1.2))
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(4, 4, 16, 16), 3, 3)
    p.end()
    return QIcon(pix)
