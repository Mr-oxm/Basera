"""Main toolbar with grouped tool buttons, flyout sub-toolbars, and FG/BG colour swatches."""

from __future__ import annotations

from PySide6.QtCore import (
    Qt, Signal, QSize, QRectF, QPointF, QPoint, QTimer,
)
from PySide6.QtGui import (
    QFont, QIcon, QPixmap, QPainter, QPainterPath,
    QColor, QPen, QBrush, QLinearGradient, QMouseEvent, QPaintEvent,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QToolBar, QToolButton, QWidget, QVBoxLayout, QHBoxLayout,
    QSizePolicy, QFrame,
)

from ..core.color import Color
from ..core.color_engine import ColorManager
from ..core.enums import ToolType
from .shortcut_manager import ShortcutManager

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_ICO = 24  # icon drawing area
_BTN = 32  # button size
_CLR = QColor(210, 210, 210)  # default icon stroke colour
_CLR2 = QColor(160, 160, 160)  # secondary colour

# ---------------------------------------------------------------------------
# Tool-group definitions
# Each entry: (group_key, default_shortcut, [(ToolType, label, shortcut)])
# ---------------------------------------------------------------------------
_TOOL_GROUPS: list[tuple[str, str, list[tuple[ToolType, str, str]]]] = [
    ("move", "V", [
        (ToolType.MOVE, "Move", "V"),
    ]),
    ("marquee", "M", [
        (ToolType.RECT_SELECT, "Rectangular Marquee", "M"),
        (ToolType.ELLIPSE_SELECT, "Elliptical Marquee", "M"),
    ]),
    ("selection", "L", [
        (ToolType.LASSO, "Lasso", "L"),
        (ToolType.MAGIC_WAND, "Magic Wand", "W"),
    ]),
    ("crop", "C", [
        (ToolType.CROP, "Crop", "C"),
    ]),
    ("eyedropper", "I", [
        (ToolType.EYEDROPPER, "Eyedropper", "I"),
    ]),
    ("retouching", "J", [
        (ToolType.HEALING_BRUSH, "Healing Brush", "J"),
        (ToolType.CLONE_STAMP, "Clone Stamp", "S"),
    ]),
    ("brush", "B", [
        (ToolType.BRUSH, "Brush", "B"),
    ]),
    ("eraser", "E", [
        (ToolType.ERASER, "Eraser", "E"),
    ]),
    ("fill", "G", [
        (ToolType.GRADIENT, "Gradient", "G"),
        (ToolType.PAINT_BUCKET, "Paint Bucket", "K"),
    ]),
    ("pen", "P", [
        (ToolType.PEN, "Pen", "P"),
    ]),
    ("node", "A", [
        (ToolType.NODE, "Node", "A"),
    ]),
    ("shape", "U", [
        (ToolType.VECTOR_SHAPE, "Vector Shape", "U"),
    ]),
    ("text", "T", [
        (ToolType.TEXT, "Text", "T"),
    ]),
    ("navigate", "Z", [
        (ToolType.ZOOM, "Zoom", "Z"),
        (ToolType.PAN, "Pan", "H"),
    ]),
]

# ---------------------------------------------------------------------------
# Icon drawing helpers
# ---------------------------------------------------------------------------

def _px(size: int = _ICO) -> tuple[QPixmap, QPainter]:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pix, p


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


# ---- Individual tool icon painters ----------------------------------------

from PySide6.QtGui import QRadialGradient

_C_MAIN = QColor(230, 230, 240)
_C_MAIN_DARK = QColor(190, 190, 200)
_C_ACCENT = QColor(110, 180, 255)
_C_ACCENT_DIM = QColor(110, 180, 255, 75)
_C_BG = QColor(60, 60, 65)

def update_toolbar_icon_colors(palette: dict):
    global _C_MAIN, _C_MAIN_DARK, _C_ACCENT, _C_ACCENT_DIM, _C_BG
    _C_MAIN = QColor(palette['fg'])
    _C_MAIN_DARK = QColor(palette['fg_dim'])
    _C_ACCENT = QColor(palette['accent'])
    _C_ACCENT_DIM = QColor(palette['accent'])
    _C_ACCENT_DIM.setAlpha(75)
    _C_BG = QColor(palette['bg2'])

def _ico_move() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(QColor(0, 0, 0, 80), 2.5))
    c = _ICO / 2
    p.drawLine(QPointF(c+1, 4), QPointF(c+1, 22))
    p.drawLine(QPointF(4, c+1), QPointF(22, c+1))
    p.setPen(_pen(_C_MAIN, 1.5))
    p.setBrush(QBrush(_C_MAIN))
    p.drawLine(QPointF(c, 3), QPointF(c, 21))
    p.drawLine(QPointF(3, c), QPointF(21, c))
    for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
        tip = QPointF(c + dx * 9, c + dy * 9)
        poly = QPolygonF([tip, QPointF(tip.x() - dy*3 - dx*3, tip.y() - dx*3 - dy*3), QPointF(tip.x() + dy*3 - dx*3, tip.y() + dx*3 - dy*3)])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 80)))
        poly_shad = QPolygonF([QPointF(pt.x()+1, pt.y()+1) for pt in poly])
        p.drawPolygon(poly_shad)
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
    
    shad_path = path.translated(1, 1)
    p.setPen(_dash_pen(QColor(0, 0, 0, 80), 2))
    p.drawPath(shad_path)
    
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
    shad_poly = QPolygonF([QPointF(pt.x()+1, pt.y()+1) for pt in poly])
    
    p.setPen(_pen(QColor(0,0,0,80), 1.5))
    p.setBrush(QBrush(QColor(0,0,0,80)))
    p.drawPolygon(shad_poly)
    
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
    p.setBrush(QBrush(QColor(0,0,0,80)))
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
    p.setBrush(QBrush(QColor(0,0,0,80)))
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
    shad_poly = QPolygonF([QPointF(pt.x()+1, pt.y()+1) for pt in poly])
    
    p.setPen(_pen(QColor(0,0,0,80), 1.5))
    p.setBrush(QBrush(QColor(0,0,0,80)))
    p.drawPolygon(shad_poly)
    
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
    p.setBrush(QBrush(QColor(0,0,0,80)))
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
    r = QRectF(4, 5, 16, 14)
    
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(0,0,0,80)))
    p.drawRoundedRect(QRectF(5, 6, 16, 14), 2, 2)
    
    grad = QLinearGradient(r.topLeft(), r.bottomRight())
    grad.setColorAt(0.0, _C_ACCENT)
    grad.setColorAt(0.5, QColor(255, 100, 200)) # Extra pop!
    grad.setColorAt(1.0, QColor(40, 40, 120))
    p.setPen(_pen(_C_MAIN_DARK, 1))
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(r, 2, 2)
    p.end()
    return QIcon(pix)

def _ico_paint_bucket() -> QIcon:
    pix, p = _px()
    p.translate(10, 15)
    p.rotate(-30)
    
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(0,0,0,80)))
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
    p.drawEllipse(QPointF(11.5, 14), 1.5, 1.5) # highlight
    p.end()
    return QIcon(pix)

def _ico_text() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(QColor(0,0,0,80), 2.5))
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
    p.setPen(_pen(QColor(0,0,0,80), 1.5))
    p.setBrush(QColor(0,0,0,80))
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
    p.setPen(_pen(QColor(0,0,0,80), 2))
    p.drawEllipse(QPointF(11, 11), 6, 6)
    p.setPen(_pen(QColor(0,0,0,80), 2.5))
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
    
    shad_path = path.translated(1, 1)
    p.setPen(_pen(QColor(0,0,0,80), 1.5))
    p.setBrush(QBrush(QColor(0,0,0,80)))
    p.drawPath(shad_path)
    
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
    shad_poly = QPolygonF([QPointF(pt.x()+1, pt.y()+1) for pt in poly])
    
    p.setPen(_pen(QColor(0,0,0,80), 1.5))
    p.setBrush(QBrush(QColor(0,0,0,80)))
    p.drawPolygon(shad_poly)
    
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
    shad_poly = QPolygonF([QPointF(pt.x()+1, pt.y()+1) for pt in poly])
    
    p.setPen(_pen(QColor(0,0,0,80), 1.5))
    p.setBrush(QBrush(QColor(0,0,0,80)))
    p.drawPolygon(shad_poly)
    
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

def _ico_vector_shape() -> QIcon:
    pix, p = _px()
    path = QPainterPath()
    path.moveTo(6, 10)
    path.cubicTo(9, 4, 15, 4, 18, 10)
    path.cubicTo(15, 16, 9, 16, 6, 10)
    
    shad_path = path.translated(1, 1)
    p.setPen(_pen(QColor(0,0,0,80), 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(shad_path)
    
    p.setPen(_pen(_C_MAIN, 1.5))
    p.drawPath(path)
    
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_C_ACCENT))
    p.drawRect(QRectF(4, 8, 4, 4))
    p.drawRect(QRectF(16, 8, 4, 4))
    p.drawEllipse(QPointF(12, 5.5), 2, 2)
    p.drawEllipse(QPointF(12, 14.5), 2, 2)
    p.end()
    return QIcon(pix)


_ICON_MAP: dict[ToolType, callable] = {
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


def _tool_icon(tool_type: ToolType) -> QIcon:
    factory = _ICON_MAP.get(tool_type)
    if factory:
        return factory()
    pix, p = _px()
    p.setPen(_CLR)
    p.setFont(QFont("Segoe UI", 10))
    p.drawText(QRectF(0, 0, _ICO, _ICO), Qt.AlignmentFlag.AlignCenter, "?")
    p.end()
    return QIcon(pix)


# ---------------------------------------------------------------------------
# Flyout popup for multi-tool groups
# ---------------------------------------------------------------------------

class _ToolFlyout(QWidget):
    """Popup panel showing alternate tools in the same group."""

    tool_chosen = Signal(ToolType)

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self._container = QFrame(self)
        self._container.setObjectName("flyoutContainer")
        
        from .theme import ThemeManager
        palette = ThemeManager.instance().active_palette
        self._container.setStyleSheet(
            f"#flyoutContainer {{ background: {palette['bg2']}; border: 1px solid {palette['border']}; border-radius: 4px; }}"
        )
        
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._container)

        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(2)
        self._buttons: list[QToolButton] = []

    def populate(
        self, tools: list[tuple[ToolType, str, str]], active_type: ToolType,
    ) -> None:
        for btn in self._buttons:
            self._layout.removeWidget(btn)
            btn.deleteLater()
        self._buttons.clear()

        mgr = ShortcutManager.instance()

        for tool_type, label, _ in tools:
            btn = QToolButton()
            btn.setIcon(_tool_icon(tool_type))
            btn.setIconSize(QSize(_ICO, _ICO))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            
            # Lookup dynamic shortcut
            action_id = f"tool_{tool_type.name.lower()}"
            shortcut = mgr.binding(action_id)
            sc_text = f" ({shortcut})" if shortcut else ""
            
            btn.setText(f"  {label} {sc_text}")
            btn.setFixedHeight(_BTN)
            btn.setMinimumWidth(160)
            btn.setCheckable(True)
            btn.setChecked(tool_type == active_type)
            btn.setStyleSheet(
                "QToolButton { text-align: left; padding: 3px 8px; color: #ccc;"
                "             background: transparent; border: none; border-radius: 3px; }"
                "QToolButton:hover { background: #505050; }"
                "QToolButton:checked { background: #4a6fa5; }"
            )
            btn.clicked.connect(lambda _c, t=tool_type: self._pick(t))
            self._layout.addWidget(btn)
            self._buttons.append(btn)
        self.adjustSize()

    def _pick(self, tool_type: ToolType) -> None:
        self.tool_chosen.emit(tool_type)
        self.close()

    def show_beside(self, ref_widget: QWidget) -> None:
        pos = ref_widget.mapToGlobal(QPoint(ref_widget.width() + 2, 0))
        self.move(pos)
        self.show()


# ---------------------------------------------------------------------------
# Tool-group button
# ---------------------------------------------------------------------------

class _ToolGroupButton(QToolButton):
    """Represents one tool group in the toolbar.

    * Click -> activate the group's *current* tool.
    * Right-click / long-press -> open the flyout to choose another tool.
    * A small triangle in the bottom-right corner indicates a multi-tool group.
    """

    tool_activated = Signal(ToolType)

    def __init__(
        self, group_key: str, tools: list[tuple[ToolType, str, str]], parent=None,
    ) -> None:
        super().__init__(parent)
        self._group_key = group_key
        self._tools = tools
        self._active_index = 0

        self.setFixedSize(_BTN, _BTN)
        self.setIconSize(QSize(_ICO, _ICO))
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_icon()

        self._flyout: _ToolFlyout | None = None
        if len(tools) > 1:
            self._flyout = _ToolFlyout()
            self._flyout.tool_chosen.connect(self._on_flyout_pick)

        self._long_press = QTimer(self)
        self._long_press.setSingleShot(True)
        self._long_press.setInterval(350)
        self._long_press.timeout.connect(self._show_flyout)

    @property
    def active_tool_type(self) -> ToolType:
        return self._tools[self._active_index][0]

    @property
    def tool_types(self) -> list[ToolType]:
        return [t[0] for t in self._tools]

    def set_active_tool(self, tool_type: ToolType) -> None:
        for i, (tt, _, _) in enumerate(self._tools):
            if tt == tool_type:
                self._active_index = i
                self._update_icon()
                return

    def _update_icon(self) -> None:
        tt, label, _ = self._tools[self._active_index]
        self.setIcon(_tool_icon(tt))
        
        mgr = ShortcutManager.instance()
        action_id = f"tool_{tt.name.lower()}"
        shortcut = mgr.binding(action_id)
        sc_text = f" ({shortcut})" if shortcut else ""

        extra = "  (right-click for more)" if len(self._tools) > 1 else ""
        self.setToolTip(f"{label}{sc_text}{extra}")

    def _show_flyout(self) -> None:
        if self._flyout:
            self._flyout.populate(self._tools, self.active_tool_type)
            self._flyout.show_beside(self)

    def _on_flyout_pick(self, tool_type: ToolType) -> None:
        self.set_active_tool(tool_type)
        self.setChecked(True)
        self.tool_activated.emit(tool_type)

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MouseButton.RightButton and self._flyout:
            self._show_flyout()
            return
        if ev.button() == Qt.MouseButton.LeftButton:
            self._long_press.start()
            ev.accept()
            return  # Don't let QToolButton start its own toggle tracking
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        if self._long_press.isActive():
            self._long_press.stop()
            self.setChecked(True)
            self.tool_activated.emit(self.active_tool_type)
            ev.accept()
            return  # Don't call super — it toggles the checked state back off
        super().mouseReleaseEvent(ev)

    def paintEvent(self, ev: QPaintEvent) -> None:
        super().paintEvent(ev)
        if len(self._tools) > 1:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            s = 5
            x = self.width() - s - 3
            y = self.height() - s - 3
            tri = QPolygonF([
                QPointF(x + s, y + s),
                QPointF(x, y + s),
                QPointF(x + s, y),
            ])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(180, 180, 180))
            p.drawPolygon(tri)
            p.end()


# ---------------------------------------------------------------------------
# FG / BG colour swatch widget (Photoshop-style overlapping squares)
# ---------------------------------------------------------------------------

class _FGBGWidget(QWidget):
    """Classic foreground / background colour swatches.

    Click -> swap.  Double-click -> reset to black / white.
    """

    swap_requested = Signal()
    reset_requested = Signal()

    _SIZE = 44

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(self._SIZE, self._SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("FG / BG  -  click to swap, double-click to reset (D)")
        self._fg = Color.black()
        self._bg = Color.white()

    def set_colors(self, fg: Color, bg: Color) -> None:
        self._fg = fg
        self._bg = bg
        self.update()

    def paintEvent(self, ev: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._SIZE

        # BG square (bottom-right, behind)
        bg_rect = QRectF(s * 0.32, s * 0.32, s * 0.52, s * 0.52)
        r, g, b, a = self._bg.to_rgb8()
        p.setPen(QPen(QColor(100, 100, 100), 1.2))
        p.setBrush(QColor(r, g, b, a))
        p.drawRoundedRect(bg_rect, 2, 2)

        # FG square (top-left, in front)
        fg_rect = QRectF(s * 0.12, s * 0.12, s * 0.52, s * 0.52)
        r, g, b, a = self._fg.to_rgb8()
        p.setPen(QPen(QColor(200, 200, 200), 1.4))
        p.setBrush(QColor(r, g, b, a))
        p.drawRoundedRect(fg_rect, 2, 2)

        # Swap arrows (top-right)
        p.setPen(QPen(QColor(160, 160, 160), 1.0))
        ax, ay = s * 0.78, s * 0.12
        aw = 6
        p.drawLine(QPointF(ax, ay), QPointF(ax + aw, ay))
        p.drawLine(QPointF(ax + aw, ay), QPointF(ax + aw - 2, ay - 2))
        p.drawLine(QPointF(ax + aw, ay + aw), QPointF(ax, ay + aw))
        p.drawLine(QPointF(ax, ay + aw), QPointF(ax + 2, ay + aw + 2))

        # Default mini-squares (bottom-left)
        ds = 6
        dx, dy = s * 0.04, s * 0.82
        p.setPen(QPen(QColor(160, 160, 160), 0.8))
        p.setBrush(QColor(0, 0, 0))
        p.drawRect(QRectF(dx, dy, ds, ds))
        p.setBrush(QColor(255, 255, 255))
        p.drawRect(QRectF(dx + ds * 0.45, dy - ds * 0.45, ds, ds))

        p.end()

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self.swap_requested.emit()

    def mouseDoubleClickEvent(self, ev: QMouseEvent) -> None:
        self.reset_requested.emit()


# ---------------------------------------------------------------------------
# Main editor toolbar
# ---------------------------------------------------------------------------

class EditorToolbar(QToolBar):
    """Vertical tool bar on the left side of the editor with grouped tools
    and FG/BG colour swatches."""

    tool_selected = Signal(ToolType)

    def __init__(self, parent=None) -> None:
        super().__init__("Tools", parent)
        self.setMovable(False)
        self.setFloatable(False)
        self.setIconSize(QSize(_ICO, _ICO))
        
        from .theme import ThemeManager
        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        
        self._group_buttons: list[_ToolGroupButton] = []
        self._tool_to_group: dict[ToolType, _ToolGroupButton] = {}
        self._col_mgr = ColorManager.instance()
        self._shortcut_mgr = ShortcutManager.instance()
        self._shortcut_mgr.shortcuts_changed.connect(self._refresh_tooltips)
        self._build()
        self._apply_theme(ThemeManager.instance().active_palette)

    def _apply_theme(self, palette: dict) -> None:
        self.setStyleSheet(
            f"QToolBar {{ background: {palette['bg3']}; border: none; spacing: 0px; padding: 4px 0px; }}"
            f"QToolBar QWidget {{ background: transparent; }}"
            f"QToolBar::separator {{ background: {palette['border']}; height: 1px; margin: 4px 6px; }}"
        )
        update_toolbar_icon_colors(palette)
        self._refresh_tooltips()
        self._fg_bg.update()

    @staticmethod
    def _centered_wrapper(widget: QWidget, v_margin: int = 1) -> QWidget:
        """Wrap *widget* in a container that centres it horizontally."""
        wrapper = QWidget()
        lay = QHBoxLayout(wrapper)
        lay.setContentsMargins(0, v_margin, 0, v_margin)
        lay.setSpacing(0)
        lay.addStretch()
        lay.addWidget(widget)
        lay.addStretch()
        return wrapper

    def _build(self) -> None:
        for _group_key, _shortcut, tools in _TOOL_GROUPS:
            gbtn = _ToolGroupButton(_group_key, tools, self)
            gbtn.tool_activated.connect(self._on_tool_activated)
            self.addWidget(self._centered_wrapper(gbtn))
            self._group_buttons.append(gbtn)
            for tt, _, _ in tools:
                self._tool_to_group[tt] = gbtn

        # Default selection
        if ToolType.BRUSH in self._tool_to_group:
            self._tool_to_group[ToolType.BRUSH].setChecked(True)

        # Spacer pushes colour swatches to the bottom
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        spacer.setStyleSheet("background: transparent;")
        self.addWidget(spacer)

        # FG / BG colour swatches
        self.addSeparator()
        self._fg_bg = _FGBGWidget()
        self._fg_bg.swap_requested.connect(self._col_mgr.swap)
        self._fg_bg.reset_requested.connect(self._col_mgr.reset)
        self.addWidget(self._centered_wrapper(self._fg_bg, v_margin=4))

        self._col_mgr.foreground_changed.connect(self._on_color_changed)
        self._col_mgr.background_changed.connect(self._on_color_changed)
        self._fg_bg.set_colors(self._col_mgr.foreground, self._col_mgr.background)

    def _refresh_tooltips(self) -> None:
        """Update tooltips on all group buttons when shortcuts change."""
        for gbtn in self._group_buttons:
            gbtn._update_icon()

    def _on_tool_activated(self, tool_type: ToolType) -> None:
        sender = self._tool_to_group.get(tool_type)
        for gbtn in self._group_buttons:
            gbtn.setChecked(gbtn is sender)
        self.tool_selected.emit(tool_type)

    def _on_color_changed(self, _color=None) -> None:
        self._fg_bg.set_colors(self._col_mgr.foreground, self._col_mgr.background)

    def select_tool(self, tool_type: ToolType) -> None:
        gbtn = self._tool_to_group.get(tool_type)
        if gbtn:
            gbtn.set_active_tool(tool_type)
            for b in self._group_buttons:
                b.setChecked(b is gbtn)
            self.tool_selected.emit(tool_type)
