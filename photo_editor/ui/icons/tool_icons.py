"""Central toolbar icon builders."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)

from ...core.enums import ToolType


_ICO = 24
_CLR = QColor(210, 210, 210)

_C_MAIN = QColor(230, 230, 240)
_C_MAIN_DARK = QColor(190, 190, 200)
_C_ACCENT = QColor(110, 180, 255)
_C_ACCENT_DIM = QColor(110, 180, 255, 75)
_C_BG = QColor(60, 60, 65)


def update_tool_icon_colors(palette: dict) -> None:
    global _C_MAIN, _C_MAIN_DARK, _C_ACCENT, _C_ACCENT_DIM, _C_BG
    _C_MAIN = QColor(palette["fg"])
    _C_MAIN_DARK = QColor(palette["fg_dim"])
    _C_ACCENT = QColor(palette["accent"])
    _C_ACCENT_DIM = QColor(palette["accent"])
    _C_ACCENT_DIM.setAlpha(75)
    _C_BG = QColor(palette["bg2"])


def _px(size: int = _ICO) -> tuple[QPixmap, QPainter]:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pix, painter


def _pen(color: QColor = _CLR, width: float = 1.6) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _dash_pen(color: QColor = _CLR, width: float = 1.4) -> QPen:
    pen = QPen(color, width, Qt.PenStyle.DashLine)
    pen.setDashPattern([3, 3])
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


def _ico_move() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(QColor(0, 0, 0, 80), 2.5))
    center = _ICO / 2
    p.drawLine(QPointF(center + 1, 4), QPointF(center + 1, 22))
    p.drawLine(QPointF(4, center + 1), QPointF(22, center + 1))
    p.setPen(_pen(_C_MAIN, 1.5))
    p.setBrush(QBrush(_C_MAIN))
    p.drawLine(QPointF(center, 3), QPointF(center, 21))
    p.drawLine(QPointF(3, center), QPointF(21, center))
    for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
        tip = QPointF(center + dx * 9, center + dy * 9)
        poly = QPolygonF([
            tip,
            QPointF(tip.x() - dy * 3 - dx * 3, tip.y() - dx * 3 - dy * 3),
            QPointF(tip.x() + dy * 3 - dx * 3, tip.y() + dx * 3 - dy * 3),
        ])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 80)))
        p.drawPolygon(QPolygonF([QPointF(pt.x() + 1, pt.y() + 1) for pt in poly]))
        p.setPen(_pen(_C_MAIN, 1))
        p.setBrush(QBrush(_C_MAIN))
        p.drawPolygon(poly)
    p.end()
    return QIcon(pix)


def _ico_rect_select() -> QIcon:
    pix, p = _px()
    p.setPen(_dash_pen(QColor(0, 0, 0, 80), 1.6))
    p.drawRect(QRectF(5, 6, 16, 14))
    p.setPen(_dash_pen(_C_MAIN, 1.2))
    p.setBrush(QBrush(_C_ACCENT_DIM))
    p.drawRect(QRectF(4, 5, 16, 14))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_C_ACCENT)
    p.drawRect(3, 4, 3, 3)
    p.drawRect(18, 17, 3, 3)
    p.end()
    return QIcon(pix)


def _ico_ellipse_select() -> QIcon:
    pix, p = _px()
    p.setPen(_dash_pen(QColor(0, 0, 0, 80), 1.6))
    p.drawEllipse(QRectF(4, 6, 18, 14))
    p.setPen(_dash_pen(_C_MAIN, 1.2))
    p.setBrush(QBrush(_C_ACCENT_DIM))
    p.drawEllipse(QRectF(3, 5, 18, 14))
    p.end()
    return QIcon(pix)


def _ico_lasso() -> QIcon:
    pix, p = _px()
    path = QPainterPath()
    path.moveTo(10, 18)
    path.cubicTo(2, 12, 6, 2, 14, 4)
    path.cubicTo(22, 6, 20, 14, 15, 17)
    path.cubicTo(13, 18, 11, 19, 10, 18)
    p.setPen(_dash_pen(QColor(0, 0, 0, 80), 2))
    p.drawPath(path.translated(1, 1))
    p.setPen(_dash_pen(_C_MAIN, 1.5))
    p.drawPath(path)
    p.setPen(_pen(_C_MAIN, 1.5))
    p.drawLine(QPointF(10, 18), QPointF(8, 22))
    p.end()
    return QIcon(pix)


def _ico_magic_wand() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(QColor(0, 0, 0, 80), 2.5))
    p.drawLine(QPointF(6, 20), QPointF(16, 10))
    p.setPen(_pen(_C_MAIN, 2))
    p.drawLine(QPointF(5, 19), QPointF(15, 9))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_C_ACCENT)
    p.drawEllipse(QPointF(15, 9), 2.5, 2.5)
    p.drawEllipse(QPointF(19, 5), 1.5, 1.5)
    p.drawEllipse(QPointF(11, 4), 1, 1)
    p.drawEllipse(QPointF(20, 11), 1, 1)
    p.setBrush(QColor(255, 255, 255))
    p.drawEllipse(QPointF(15, 9), 1, 1)
    p.end()
    return QIcon(pix)


def _ico_crop() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(QColor(0, 0, 0, 80), 2.5))
    p.drawLine(QPointF(6, 5), QPointF(6, 19))
    p.drawLine(QPointF(5, 6), QPointF(19, 6))
    p.drawLine(QPointF(19, 6), QPointF(19, 21))
    p.drawLine(QPointF(6, 19), QPointF(21, 19))
    p.setPen(_pen(_C_MAIN, 2))
    p.drawLine(QPointF(5, 4), QPointF(5, 18))
    p.drawLine(QPointF(4, 5), QPointF(18, 5))
    p.drawLine(QPointF(18, 5), QPointF(18, 20))
    p.drawLine(QPointF(5, 18), QPointF(20, 18))
    p.setPen(_pen(_C_ACCENT_DIM, 1))
    p.drawLine(QPointF(9, 5), QPointF(9, 18))
    p.drawLine(QPointF(14, 5), QPointF(14, 18))
    p.drawLine(QPointF(5, 9), QPointF(18, 9))
    p.drawLine(QPointF(5, 14), QPointF(18, 14))
    p.end()
    return QIcon(pix)


def _ico_eyedropper() -> QIcon:
    pix, p = _px()
    p.translate(2, -2)
    poly = QPolygonF([QPointF(5, 20), QPointF(8, 17), QPointF(17, 8), QPointF(19, 10), QPointF(10, 19)])
    p.setPen(_pen(QColor(0, 0, 0, 80), 1.5))
    p.setBrush(QBrush(QColor(0, 0, 0, 80)))
    p.drawPolygon(QPolygonF([QPointF(pt.x() + 1, pt.y() + 1) for pt in poly]))
    grad = QLinearGradient(17, 8, 5, 20)
    grad.setColorAt(0, _C_MAIN)
    grad.setColorAt(1, _C_MAIN_DARK)
    p.setPen(_pen(_C_MAIN, 1.5))
    p.setBrush(QBrush(grad))
    p.drawPolygon(poly)
    p.setBrush(QBrush(_C_ACCENT))
    p.drawEllipse(QPointF(18, 7), 2.5, 2.5)
    p.drawLine(QPointF(5, 20), QPointF(3, 22))
    p.end()
    return QIcon(pix)


def _ico_healing() -> QIcon:
    pix, p = _px()
    p.translate(12, 12)
    p.rotate(45)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(0, 0, 0, 80)))
    p.drawRoundedRect(QRectF(-3, -9, 8, 20), 4, 4)
    p.setPen(_pen(_C_MAIN, 1))
    grad = QLinearGradient(-4, -10, 4, 10)
    grad.setColorAt(0, _C_BG)
    grad.setColorAt(1, _C_MAIN_DARK)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(QRectF(-4, -10, 8, 20), 4, 4)
    p.setPen(_dash_pen(_C_ACCENT, 1))
    p.drawLine(QPointF(-4, -2), QPointF(4, -2))
    p.drawLine(QPointF(-4, 2), QPointF(4, 2))
    p.end()
    return QIcon(pix)


def _ico_clone_stamp() -> QIcon:
    pix, p = _px()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(0, 0, 0, 80)))
    p.drawRoundedRect(QRectF(7, 13, 12, 6), 2, 2)
    p.setPen(_pen(_C_MAIN, 1.5))
    grad = QLinearGradient(6, 12, 6, 18)
    grad.setColorAt(0, _C_MAIN_DARK)
    grad.setColorAt(1, _C_BG)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(QRectF(6, 12, 12, 6), 2, 2)
    p.setPen(_pen(_C_MAIN, 2))
    p.drawLine(QPointF(12, 5), QPointF(12, 12))
    p.drawEllipse(QPointF(12, 4), 3, 2)
    p.setPen(_pen(_C_ACCENT, 2))
    p.drawLine(QPointF(5, 20), QPointF(19, 20))
    p.end()
    return QIcon(pix)


def _ico_brush() -> QIcon:
    pix, p = _px()
    poly = QPolygonF([QPointF(17, 3), QPointF(20, 6), QPointF(12, 14), QPointF(9, 11)])
    p.setPen(_pen(QColor(0, 0, 0, 80), 1.5))
    p.setBrush(QBrush(QColor(0, 0, 0, 80)))
    p.drawPolygon(QPolygonF([QPointF(pt.x() + 1, pt.y() + 1) for pt in poly]))
    grad = QLinearGradient(17, 3, 9, 11)
    grad.setColorAt(0, _C_MAIN)
    grad.setColorAt(1, _C_BG)
    p.setPen(_pen(_C_MAIN, 1.5))
    p.setBrush(QBrush(grad))
    p.drawPolygon(poly)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_C_ACCENT))
    tip = QPainterPath()
    tip.moveTo(9, 11)
    tip.lineTo(12, 14)
    tip.cubicTo(10, 20, 5, 22, 4, 21)
    tip.cubicTo(3, 20, 5, 15, 9, 11)
    p.drawPath(tip)
    p.end()
    return QIcon(pix)


def _ico_eraser() -> QIcon:
    pix, p = _px()
    p.translate(12, 12)
    p.rotate(-45)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(0, 0, 0, 80)))
    p.drawRoundedRect(QRectF(-5, -9, 12, 20), 2, 2)
    p.setPen(_pen(_C_MAIN, 1))
    grad = QLinearGradient(-6, -10, 6, 10)
    grad.setColorAt(0, _C_MAIN)
    grad.setColorAt(0.5, _C_MAIN_DARK)
    grad.setColorAt(1, _C_BG)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(QRectF(-6, -10, 12, 20), 2, 2)
    p.setBrush(QBrush(_C_ACCENT))
    p.drawRect(QRectF(-6, 2, 12, 8))
    p.end()
    return QIcon(pix)


def _ico_gradient() -> QIcon:
    pix, p = _px()
    rect = QRectF(4, 5, 16, 14)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(0, 0, 0, 80)))
    p.drawRoundedRect(QRectF(5, 6, 16, 14), 2, 2)
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0.0, _C_ACCENT)
    grad.setColorAt(0.5, QColor(255, 100, 200))
    grad.setColorAt(1.0, QColor(40, 40, 120))
    p.setPen(_pen(_C_MAIN_DARK, 1))
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(rect, 2, 2)
    p.end()
    return QIcon(pix)


def _ico_paint_bucket() -> QIcon:
    pix, p = _px()
    p.translate(10, 15)
    p.rotate(-30)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(0, 0, 0, 80)))
    p.drawRect(QRectF(-5, -7, 12, 12))
    p.drawEllipse(QPointF(1, -7), 6, 2)
    p.setPen(_pen(_C_MAIN, 1))
    grad = QLinearGradient(-6, -8, 6, 4)
    grad.setColorAt(0, _C_MAIN)
    grad.setColorAt(1, _C_BG)
    p.setBrush(QBrush(grad))
    p.drawRect(QRectF(-6, -8, 12, 12))
    p.drawEllipse(QPointF(0, -8), 6, 2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_C_ACCENT))
    drop = QPainterPath()
    drop.moveTo(10, 5)
    drop.cubicTo(6, 12, 12, 18, 14, 15)
    drop.cubicTo(16, 12, 10, 5, 10, 5)
    p.drawPath(drop)
    p.setBrush(QColor(255, 255, 255, 150))
    p.drawEllipse(QPointF(11.5, 14), 1.5, 1.5)
    p.end()
    return QIcon(pix)


def _ico_text() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(QColor(0, 0, 0, 80), 2.5))
    p.drawLine(QPointF(6, 6), QPointF(20, 6))
    p.drawLine(QPointF(13, 6), QPointF(13, 20))
    p.setPen(_pen(_C_MAIN, 2))
    p.drawLine(QPointF(5, 5), QPointF(19, 5))
    p.drawLine(QPointF(12, 5), QPointF(12, 19))
    p.drawLine(QPointF(9, 19), QPointF(15, 19))
    p.drawLine(QPointF(5, 5), QPointF(5, 8))
    p.drawLine(QPointF(19, 5), QPointF(19, 8))
    p.end()
    return QIcon(pix)


def _ico_shape() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(QColor(0, 0, 0, 80), 1.5))
    p.setBrush(QColor(0, 0, 0, 80))
    p.drawRect(QRectF(5, 5, 10, 10))
    p.drawEllipse(QPointF(17, 17), 5, 5)
    p.setPen(_pen(_C_MAIN, 1.5))
    p.setBrush(QBrush(_C_ACCENT_DIM))
    p.drawRect(QRectF(4, 4, 10, 10))
    grad = QRadialGradient(15, 15, 5)
    grad.setColorAt(0, QColor(255, 255, 255))
    grad.setColorAt(0.3, _C_ACCENT)
    grad.setColorAt(1, QColor(50, 100, 200))
    p.setBrush(QBrush(grad))
    p.drawEllipse(QPointF(16, 16), 5, 5)
    p.end()
    return QIcon(pix)


def _ico_zoom() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(QColor(0, 0, 0, 80), 2))
    p.drawEllipse(QPointF(11, 11), 6, 6)
    p.setPen(_pen(QColor(0, 0, 0, 80), 2.5))
    p.drawLine(QPointF(15.5, 15.5), QPointF(21, 21))
    p.setPen(_pen(_C_MAIN, 2))
    p.setBrush(QBrush(_C_ACCENT_DIM))
    p.drawEllipse(QPointF(10, 10), 6, 6)
    p.setPen(_pen(_C_MAIN, 2.5))
    p.drawLine(QPointF(14.5, 14.5), QPointF(20, 20))
    p.setPen(_pen(_C_ACCENT, 1.5))
    p.drawLine(QPointF(10, 7), QPointF(10, 13))
    p.drawLine(QPointF(7, 10), QPointF(13, 10))
    p.end()
    return QIcon(pix)


def _ico_pan() -> QIcon:
    pix, p = _px()
    path = QPainterPath()
    path.moveTo(9, 18)
    path.lineTo(6, 12)
    path.arcTo(QRectF(4, 9, 3, 3), 180, -180)
    path.lineTo(7, 7)
    path.arcTo(QRectF(7, 5, 3, 3), 180, -180)
    path.lineTo(10, 6)
    path.arcTo(QRectF(10, 4, 3, 3), 180, -180)
    path.lineTo(13, 7)
    path.arcTo(QRectF(13, 6, 3, 3), 180, -180)
    path.lineTo(16, 13)
    path.cubicTo(18, 16, 13, 20, 9, 18)
    p.setPen(_pen(QColor(0, 0, 0, 80), 1.5))
    p.setBrush(QBrush(QColor(0, 0, 0, 80)))
    p.drawPath(path.translated(1, 1))
    p.setPen(_pen(_C_MAIN, 1))
    grad = QLinearGradient(4, 4, 18, 20)
    grad.setColorAt(0, _C_MAIN)
    grad.setColorAt(1, _C_BG)
    p.setBrush(QBrush(grad))
    p.drawPath(path)
    p.end()
    return QIcon(pix)


def _ico_pen() -> QIcon:
    pix, p = _px()
    p.translate(12, 12)
    p.rotate(-45)
    poly = QPolygonF([QPointF(-3, -10), QPointF(3, -10), QPointF(3, 2), QPointF(0, 10), QPointF(-3, 2)])
    p.setPen(_pen(QColor(0, 0, 0, 80), 1.5))
    p.setBrush(QBrush(QColor(0, 0, 0, 80)))
    p.drawPolygon(QPolygonF([QPointF(pt.x() + 1, pt.y() + 1) for pt in poly]))
    p.setPen(_pen(_C_MAIN, 1))
    grad = QLinearGradient(-3, -10, 0, 10)
    grad.setColorAt(0, _C_MAIN_DARK)
    grad.setColorAt(1, _C_BG)
    p.setBrush(QBrush(grad))
    p.drawPolygon(poly)
    p.setPen(_pen(_C_ACCENT, 1))
    p.drawLine(QPointF(0, 2), QPointF(0, 8))
    p.end()
    return QIcon(pix)


def _ico_node() -> QIcon:
    pix, p = _px()
    poly = QPolygonF([QPointF(6, 4), QPointF(6, 18), QPointF(10, 14), QPointF(14, 21), QPointF(16, 20), QPointF(12, 13), QPointF(17, 13)])
    p.setPen(_pen(QColor(0, 0, 0, 80), 1.5))
    p.setBrush(QBrush(QColor(0, 0, 0, 80)))
    p.drawPolygon(QPolygonF([QPointF(pt.x() + 1, pt.y() + 1) for pt in poly]))
    p.setPen(_pen(_C_MAIN, 1))
    grad = QLinearGradient(6, 4, 17, 21)
    grad.setColorAt(0, _C_MAIN)
    grad.setColorAt(1, _C_BG)
    p.setBrush(QBrush(grad))
    p.drawPolygon(poly)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_C_ACCENT))
    p.drawRect(QRectF(4, 2, 4, 4))
    p.drawRect(QRectF(15, 11, 4, 4))
    p.end()
    return QIcon(pix)


_ICON_MAP: dict[ToolType, Callable[[], QIcon]] = {
    ToolType.MOVE: _ico_move,
    ToolType.RECT_SELECT: _ico_rect_select,
    ToolType.ELLIPSE_SELECT: _ico_ellipse_select,
    ToolType.LASSO: _ico_lasso,
    ToolType.MAGIC_WAND: _ico_magic_wand,
    ToolType.CROP: _ico_crop,
    ToolType.EYEDROPPER: _ico_eyedropper,
    ToolType.HEALING_BRUSH: _ico_healing,
    ToolType.CLONE_STAMP: _ico_clone_stamp,
    ToolType.BRUSH: _ico_brush,
    ToolType.ERASER: _ico_eraser,
    ToolType.GRADIENT: _ico_gradient,
    ToolType.PAINT_BUCKET: _ico_paint_bucket,
    ToolType.TEXT: _ico_text,
    ToolType.PEN: _ico_pen,
    ToolType.NODE: _ico_node,
    ToolType.VECTOR_SHAPE: _ico_shape,
    ToolType.ZOOM: _ico_zoom,
    ToolType.PAN: _ico_pan,
}


def tool_icon(tool_type: ToolType) -> QIcon:
    factory = _ICON_MAP.get(tool_type)
    if factory:
        return factory()
    pix, p = _px()
    p.setPen(_CLR)
    p.setFont(QFont("Segoe UI", 10))
    p.drawText(QRectF(0, 0, _ICO, _ICO), Qt.AlignmentFlag.AlignCenter, "?")
    p.end()
    return QIcon(pix)
