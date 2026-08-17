"""Vector icons drawn at runtime — no image assets to ship or lose."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QIcon, QPainter, QPainterPath, QPen,
                           QPixmap, QPolygonF, QTransform)

STROKE = QColor("#dfe3ea")
ACCENT = QColor("#4c8dff")
WARM = QColor("#ffc233")
DANGER = QColor("#e0555f")
SIZE = 22


def _canvas(size: int = SIZE):
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    return pix, painter


def _pen(color=None, width=1.7, cap=Qt.RoundCap):
    pen = QPen(color or STROKE)
    pen.setWidthF(width)
    pen.setCapStyle(cap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _text_icon(painter, letter, family="DejaVu Sans", size=12, bold=True,
               italic=False, rect=None, color=None):
    font = QFont(family)
    font.setPixelSize(size)
    font.setBold(bold)
    font.setItalic(italic)
    painter.setFont(font)
    painter.setPen(color or STROKE)
    painter.drawText(rect or QRectF(0, 0, SIZE, SIZE), Qt.AlignCenter, letter)


def _arrow_head(painter, tip: QPointF, angle: float, size=6.0):
    for spread in (0.5, -0.5):
        painter.drawLine(tip, QPointF(tip.x() - size * math.cos(angle + spread),
                                      tip.y() - size * math.sin(angle + spread)))


def icon(name: str) -> QIcon:
    pix, p = _canvas()
    p.setPen(_pen())
    p.setBrush(Qt.NoBrush)
    S = SIZE

    if name == "select":
        path = QPainterPath(QPointF(6, 3))
        for pt in [(6, 16.5), (9.6, 13.2), (12.3, 18.6), (14.4, 17.5),
                   (11.8, 12.3), (16.4, 11.8)]:
            path.lineTo(QPointF(*pt))
        path.closeSubpath()
        p.setBrush(STROKE)
        p.setPen(_pen(width=1.1))
        p.drawPath(path)

    elif name == "textselect":
        p.drawLine(QPointF(11, 4), QPointF(11, 18))
        p.drawLine(QPointF(8.5, 4), QPointF(13.5, 4))
        p.drawLine(QPointF(8.5, 18), QPointF(13.5, 18))
        p.setPen(_pen(ACCENT, 1.4))
        p.drawLine(QPointF(4, 8), QPointF(4, 14))
        p.drawLine(QPointF(18, 8), QPointF(18, 14))

    elif name == "edittext":
        _text_icon(p, "A", size=13, rect=QRectF(-3, -2, S, S))
        p.setPen(_pen(ACCENT, 1.8))
        path = QPainterPath(QPointF(12, 16.5))
        path.lineTo(QPointF(18.2, 10.2))
        path.lineTo(QPointF(19.8, 11.8))
        path.lineTo(QPointF(13.6, 18.1))
        path.closeSubpath()
        p.setBrush(QColor(76, 141, 255, 60))
        p.drawPath(path)
        p.drawLine(QPointF(12, 16.5), QPointF(11.4, 18.7))
        p.drawLine(QPointF(11.4, 18.7), QPointF(13.6, 18.1))

    elif name == "text":
        p.drawLine(QPointF(4.5, 6.5), QPointF(4.5, 4.5))
        p.drawLine(QPointF(4.5, 4.5), QPointF(17.5, 4.5))
        p.drawLine(QPointF(17.5, 4.5), QPointF(17.5, 6.5))
        p.drawLine(QPointF(11, 4.5), QPointF(11, 17.5))
        p.drawLine(QPointF(8, 17.5), QPointF(14, 17.5))

    elif name == "highlight":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 210, 60, 190))
        p.drawRect(QRectF(3.5, 9, 15, 6.5))
        p.setPen(_pen(width=1.5))
        p.drawLine(QPointF(3.5, 6), QPointF(18.5, 6))
        p.drawLine(QPointF(3.5, 18.5), QPointF(18.5, 18.5))

    elif name == "underline":
        _text_icon(p, "U", size=12, rect=QRectF(0, -3, S, S))
        p.setPen(_pen(ACCENT, 2.0))
        p.drawLine(QPointF(5, 17.5), QPointF(17, 17.5))

    elif name == "strikeout":
        _text_icon(p, "S", size=12, rect=QRectF(0, 0, S, S))
        p.setPen(_pen(DANGER, 2.0))
        p.drawLine(QPointF(4, 11), QPointF(18, 11))

    elif name == "rect":
        p.drawRect(QRectF(3.5, 5.5, 15, 11))

    elif name == "ellipse":
        p.drawEllipse(QRectF(3.5, 5.5, 15, 11))

    elif name == "line":
        p.drawLine(QPointF(4.5, 17.5), QPointF(17.5, 4.5))

    elif name == "arrow":
        p.drawLine(QPointF(4.5, 17.5), QPointF(17, 5))
        _arrow_head(p, QPointF(17, 5), math.atan2(-12.5, 12.5), 7)

    elif name == "ink":
        path = QPainterPath(QPointF(3.5, 15.5))
        path.cubicTo(QPointF(7, 5.5), QPointF(10, 20), QPointF(13.5, 9.5))
        path.cubicTo(QPointF(15.5, 4.5), QPointF(17, 8.5), QPointF(18.5, 6.5))
        p.drawPath(path)

    elif name == "whiteout":
        p.setBrush(QColor("#ffffff"))
        p.setPen(_pen(QColor("#8b93a1"), 1.3))
        p.drawRect(QRectF(3.5, 6.5, 15, 9))
        p.setPen(_pen(QColor("#c3c9d4"), 1.2))
        p.drawLine(QPointF(6, 11), QPointF(16, 11))

    elif name == "redact":
        p.setBrush(QColor("#14161a"))
        p.setPen(_pen(width=1.3))
        p.drawRect(QRectF(3.5, 6.5, 15, 9))

    elif name == "image":
        p.drawRoundedRect(QRectF(3.5, 4.5, 15, 13), 2, 2)
        p.setBrush(WARM)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(6.5, 7.5, 3, 3))
        p.setPen(_pen(width=1.5))
        p.setBrush(Qt.NoBrush)
        path = QPainterPath(QPointF(4.5, 16))
        path.lineTo(QPointF(9, 11))
        path.lineTo(QPointF(12, 14))
        path.lineTo(QPointF(15, 10.5))
        path.lineTo(QPointF(17.5, 16))
        p.drawPath(path)

    elif name == "note":
        p.setBrush(QColor(255, 202, 64, 60))
        p.drawRoundedRect(QRectF(3.5, 4.5, 15, 11), 2.5, 2.5)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath(QPointF(7.5, 15.5))
        path.lineTo(QPointF(6.5, 19.5))
        path.lineTo(QPointF(11, 15.5))
        p.drawPath(path)
        p.setPen(_pen(width=1.2))
        p.drawLine(QPointF(6.5, 8), QPointF(15.5, 8))
        p.drawLine(QPointF(6.5, 11.5), QPointF(13, 11.5))

    elif name in ("zoom-in", "zoom-out"):
        p.drawEllipse(QRectF(3.5, 3.5, 11, 11))
        p.setPen(_pen(width=2.0))
        p.drawLine(QPointF(13.2, 13.2), QPointF(18.5, 18.5))
        p.setPen(_pen(width=1.6))
        p.drawLine(QPointF(6.4, 9), QPointF(11.6, 9))
        if name == "zoom-in":
            p.drawLine(QPointF(9, 6.4), QPointF(9, 11.6))

    elif name == "fit-width":
        p.drawRect(QRectF(3.5, 4.5, 15, 13))
        p.setPen(_pen(ACCENT, 1.5))
        p.drawLine(QPointF(6, 11), QPointF(16, 11))
        _arrow_head(p, QPointF(6, 11), math.pi, 4)
        _arrow_head(p, QPointF(16, 11), 0, 4)

    elif name == "fit-page":
        p.drawRect(QRectF(3.5, 3.5, 15, 15))
        p.setPen(_pen(ACCENT, 1.5))
        p.drawRect(QRectF(7.5, 7.5, 7, 7))

    elif name in ("undo", "redo"):
        path = QPainterPath(QPointF(5.5, 9.5))
        path.cubicTo(QPointF(8.5, 5.5), QPointF(14.5, 5.5), QPointF(17, 9.5))
        path.cubicTo(QPointF(18.5, 11.8), QPointF(18.2, 14.5), QPointF(16.5, 16.5))
        p.drawPath(path)
        p.setBrush(STROKE)
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(5.5, 10.5), QPointF(3.2, 5.2),
                                 QPointF(9.6, 6.4)]))
        p.end()
        if name == "redo":
            return QIcon(pix.transformed(QTransform(-1, 0, 0, 1, 0, 0)))
        return QIcon(pix)

    elif name in ("rotate-left", "rotate-right"):
        p.drawArc(QRectF(4.5, 5, 13, 13), 30 * 16, 260 * 16)
        p.setBrush(STROKE)
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(16.6, 4.2), QPointF(18.6, 9.6),
                                 QPointF(13.2, 8.4)]))
        p.end()
        if name == "rotate-left":
            return QIcon(pix.transformed(QTransform(-1, 0, 0, 1, 0, 0)))
        return QIcon(pix)

    elif name == "new":
        p.drawPath(_doc_path())
        p.setPen(_pen(ACCENT, 1.8))
        p.drawLine(QPointF(11, 9.5), QPointF(11, 15.5))
        p.drawLine(QPointF(8, 12.5), QPointF(14, 12.5))

    elif name == "open":
        p.drawLine(QPointF(3.5, 16.5), QPointF(3.5, 6))
        p.drawLine(QPointF(3.5, 6), QPointF(8.5, 6))
        p.drawLine(QPointF(8.5, 6), QPointF(10.5, 8.5))
        p.drawLine(QPointF(10.5, 8.5), QPointF(16.5, 8.5))
        path = QPainterPath(QPointF(3.5, 16.5))
        path.lineTo(QPointF(6.5, 10.5))
        path.lineTo(QPointF(19.5, 10.5))
        path.lineTo(QPointF(16.5, 16.5))
        path.closeSubpath()
        p.drawPath(path)

    elif name == "save":
        p.drawRoundedRect(QRectF(3.5, 3.5, 15, 15), 2, 2)
        p.setBrush(QColor("#dfe3ea"))
        p.setPen(Qt.NoPen)
        p.drawRect(QRectF(7, 3.5, 8, 5))
        p.setPen(_pen(width=1.4))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(6.5, 12, 9, 6.5))

    elif name == "print":
        p.drawRect(QRectF(6, 3.5, 10, 4))
        p.drawRoundedRect(QRectF(3.5, 7.5, 15, 7.5), 1.5, 1.5)
        p.setBrush(QColor("#1c1f24"))
        p.drawRect(QRectF(6.5, 12.5, 9, 6))

    elif name == "find":
        p.drawEllipse(QRectF(4, 4, 10.5, 10.5))
        p.setPen(_pen(width=2.0))
        p.drawLine(QPointF(13.4, 13.4), QPointF(18.5, 18.5))

    elif name == "pages":
        p.drawRect(QRectF(3.5, 4.5, 6.5, 6))
        p.drawRect(QRectF(3.5, 12, 6.5, 6))
        p.setPen(_pen(QColor("#8b93a1"), 1.4))
        p.drawLine(QPointF(12.5, 6.5), QPointF(18.5, 6.5))
        p.drawLine(QPointF(12.5, 9.5), QPointF(18.5, 9.5))
        p.drawLine(QPointF(12.5, 14), QPointF(18.5, 14))
        p.drawLine(QPointF(12.5, 17), QPointF(18.5, 17))

    elif name == "outline":
        for i, y in enumerate((5.5, 10, 14.5)):
            p.setBrush(STROKE)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QRectF(4 + i * 1.5, y - 1.2, 2.4, 2.4))
            p.setPen(_pen(width=1.4))
            p.drawLine(QPointF(8.5 + i * 1.5, y), QPointF(18.5, y))

    elif name == "merge":
        p.drawRect(QRectF(3.5, 4.5, 8, 10))
        p.setPen(_pen(ACCENT, 1.6))
        p.drawRect(QRectF(10.5, 7.5, 8, 10))

    elif name == "delete":
        p.drawLine(QPointF(4.5, 6.5), QPointF(17.5, 6.5))
        p.drawLine(QPointF(9, 6.5), QPointF(9, 4.5))
        p.drawLine(QPointF(9, 4.5), QPointF(13, 4.5))
        p.drawLine(QPointF(13, 4.5), QPointF(13, 6.5))
        path = QPainterPath(QPointF(6, 6.5))
        path.lineTo(QPointF(7, 18))
        path.lineTo(QPointF(15, 18))
        path.lineTo(QPointF(16, 6.5))
        p.drawPath(path)

    elif name == "extract":
        p.drawRect(QRectF(3.5, 4.5, 9, 12))
        p.setPen(_pen(ACCENT, 1.6))
        p.drawLine(QPointF(14, 10.5), QPointF(19.5, 10.5))
        _arrow_head(p, QPointF(19.5, 10.5), 0, 5)

    elif name == "bold":
        _text_icon(p, "B", size=14)

    elif name == "italic":
        _text_icon(p, "I", size=14, italic=True)

    elif name == "copy":
        p.drawRect(QRectF(3.5, 3.5, 10, 12))
        p.setPen(_pen(ACCENT, 1.5))
        p.drawRect(QRectF(8, 7, 10, 12))

    elif name == "stamp":
        p.setPen(_pen(DANGER, 1.6))
        p.save()
        p.translate(11, 11)
        p.rotate(-14)
        p.drawRoundedRect(QRectF(-8.5, -5.5, 17, 11), 1.6, 1.6)
        font = QFont("DejaVu Sans")
        font.setPixelSize(7)
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRectF(-8.5, -5.5, 17, 11), Qt.AlignCenter, "OK")
        p.restore()

    elif name == "snapshot":
        p.setPen(_pen(width=1.6))
        for x0, y0, dx, dy in ((4, 4, 5, 0), (4, 4, 0, 5), (18, 4, -5, 0),
                               (18, 4, 0, 5), (4, 18, 5, 0), (4, 18, 0, -5),
                               (18, 18, -5, 0), (18, 18, 0, -5)):
            p.drawLine(QPointF(x0, y0), QPointF(x0 + dx, y0 + dy))
        p.setPen(_pen(ACCENT, 1.4))
        p.drawRect(QRectF(8, 8, 6, 6))

    elif name == "link":
        p.setPen(_pen(width=1.8))
        p.drawLine(QPointF(9, 13), QPointF(13, 9))
        p.drawArc(QRectF(2.5, 10.5, 9, 9), 200 * 16, 160 * 16)
        p.drawArc(QRectF(10.5, 2.5, 9, 9), 20 * 16, 160 * 16)

    elif name == "form":
        p.drawRoundedRect(QRectF(3.5, 4, 15, 14), 2, 2)
        p.setPen(_pen(QColor("#8b93a1"), 1.3))
        p.drawLine(QPointF(6.5, 8.5), QPointF(15.5, 8.5))
        p.drawLine(QPointF(6.5, 12), QPointF(15.5, 12))
        p.setPen(_pen(ACCENT, 1.7))
        p.drawLine(QPointF(6.5, 15.3), QPointF(11, 15.3))

    elif name == "compress":
        p.setPen(_pen(width=1.6))
        p.drawRect(QRectF(6, 3.5, 10, 4))
        p.drawRect(QRectF(6, 14.5, 10, 4))
        p.setPen(_pen(ACCENT, 1.8))
        p.drawLine(QPointF(11, 8.5), QPointF(11, 11))
        _arrow_head(p, QPointF(11, 11.6), math.pi / 2, 4.5)
        p.drawLine(QPointF(11, 13.5), QPointF(11, 11.9))
        p.setPen(_pen(QColor("#8b93a1"), 1.2))
        p.drawLine(QPointF(4, 11), QPointF(8, 11))
        p.drawLine(QPointF(14, 11), QPointF(18, 11))

    elif name == "attach":
        p.setPen(_pen(width=1.7))
        path = QPainterPath(QPointF(14.5, 6))
        path.lineTo(QPointF(7.5, 13))
        path.cubicTo(QPointF(5.6, 14.9), QPointF(8.1, 17.4), QPointF(10, 15.5))
        path.lineTo(QPointF(16.5, 9))
        path.cubicTo(QPointF(19.2, 6.3), QPointF(15.2, 2.3), QPointF(12.5, 5))
        path.lineTo(QPointF(6, 11.5))
        p.drawPath(path)

    elif name == "watermark":
        p.setPen(_pen(QColor("#8b93a1"), 1.4))
        p.drawRect(QRectF(3.5, 3.5, 15, 15))
        font = QFont("DejaVu Sans")
        font.setPixelSize(9)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(140, 150, 165))
        p.save()
        p.translate(11, 11)
        p.rotate(-35)
        p.drawText(QRectF(-9, -5, 18, 10), Qt.AlignCenter, "AB")
        p.restore()

    elif name == "numbering":
        p.setPen(_pen(QColor("#8b93a1"), 1.4))
        p.drawRect(QRectF(4.5, 3, 13, 16))
        font = QFont("DejaVu Sans")
        font.setPixelSize(8)
        p.setFont(font)
        p.setPen(STROKE)
        p.drawText(QRectF(4.5, 12, 13, 6), Qt.AlignCenter, "1")
        p.setPen(_pen(QColor("#8b93a1"), 1.1))
        for y in (6.5, 9):
            p.drawLine(QPointF(7, y), QPointF(15, y))

    elif name == "lock":
        p.drawRoundedRect(QRectF(5, 9.5, 12, 9), 1.8, 1.8)
        p.drawArc(QRectF(7.5, 3.5, 7, 10), 0, 180 * 16)
        p.setBrush(STROKE)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(9.9, 12.4, 2.2, 2.2))

    elif name == "props":
        p.drawRoundedRect(QRectF(4.5, 3.5, 13, 15), 2, 2)
        p.setPen(_pen(QColor("#8b93a1"), 1.3))
        for y in (7.5, 11, 14.5):
            p.drawLine(QPointF(7.5, y), QPointF(14.5, y))

    elif name == "sidebar":
        p.drawRoundedRect(QRectF(3.5, 4.5, 15, 13), 2, 2)
        p.setBrush(QColor("#8b93a1"))
        p.setPen(Qt.NoPen)
        p.drawRect(QRectF(3.5, 4.5, 5, 13))

    p.end()
    return QIcon(pix)


def _doc_path() -> QPainterPath:
    path = QPainterPath(QPointF(5.5, 3.5))
    path.lineTo(QPointF(13, 3.5))
    path.lineTo(QPointF(16.5, 7))
    path.lineTo(QPointF(16.5, 18.5))
    path.lineTo(QPointF(5.5, 18.5))
    path.closeSubpath()
    return path


def color_swatch(color, size: int = SIZE) -> QIcon:
    pix, p = _canvas(size)
    p.setPen(_pen(QColor("#6c7482"), 1.2))
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(3, 4, size - 6, size - 9), 3, 3)
    p.end()
    return QIcon(pix)


def app_icon() -> QIcon:
    result = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        margin = size * 0.07
        rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#c8323c"))
        p.drawRoundedRect(rect, size * 0.19, size * 0.19)
        # folded corner
        fold = QPolygonF([QPointF(rect.right() - size * 0.3, rect.top()),
                          QPointF(rect.right(), rect.top() + size * 0.3),
                          QPointF(rect.right(), rect.top())])
        p.setBrush(QColor(0, 0, 0, 45))
        p.drawPolygon(fold)
        font = QFont("DejaVu Sans")
        font.setPixelSize(max(6, int(size * 0.33)))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#ffffff"))
        p.drawText(rect.adjusted(0, size * 0.05, 0, 0), Qt.AlignCenter, "PDF")
        p.end()
        result.addPixmap(pix)
    return result
