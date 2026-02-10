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
    ("text", "T", [
        (ToolType.TEXT, "Text", "T"),
    ]),
    ("shape", "U", [
        (ToolType.SHAPE, "Shape", "U"),
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

def _ico_move() -> QIcon:
    pix, p = _px()
    p.setPen(_pen())
    c = _ICO / 2
    m, ah = 4, 3
    p.drawLine(QPointF(c, m), QPointF(c, _ICO - m))
    p.drawLine(QPointF(m, c), QPointF(_ICO - m, c))
    for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
        tip = QPointF(c + dx * (c - m), c + dy * (c - m))
        if dy == -1:
            p.drawLine(tip, QPointF(tip.x() - ah, tip.y() + ah))
            p.drawLine(tip, QPointF(tip.x() + ah, tip.y() + ah))
        elif dy == 1:
            p.drawLine(tip, QPointF(tip.x() - ah, tip.y() - ah))
            p.drawLine(tip, QPointF(tip.x() + ah, tip.y() - ah))
        elif dx == -1:
            p.drawLine(tip, QPointF(tip.x() + ah, tip.y() - ah))
            p.drawLine(tip, QPointF(tip.x() + ah, tip.y() + ah))
        elif dx == 1:
            p.drawLine(tip, QPointF(tip.x() - ah, tip.y() - ah))
            p.drawLine(tip, QPointF(tip.x() - ah, tip.y() + ah))
    p.end()
    return QIcon(pix)


def _ico_rect_select() -> QIcon:
    pix, p = _px()
    p.setPen(_dash_pen())
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(4, 5, _ICO - 8, _ICO - 10))
    p.end()
    return QIcon(pix)


def _ico_ellipse_select() -> QIcon:
    pix, p = _px()
    p.setPen(_dash_pen())
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(3, 4, _ICO - 6, _ICO - 8))
    p.end()
    return QIcon(pix)


def _ico_lasso() -> QIcon:
    pix, p = _px()
    p.setPen(_pen())
    path = QPainterPath()
    path.moveTo(8, 18)
    path.cubicTo(3, 10, 6, 3, 13, 4)
    path.cubicTo(20, 5, 21, 12, 17, 16)
    path.cubicTo(14, 19, 10, 20, 8, 18)
    p.drawPath(path)
    p.drawLine(QPointF(7, 20), QPointF(9, 22))
    p.end()
    return QIcon(pix)


def _ico_magic_wand() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(width=1.8))
    p.drawLine(QPointF(5, 19), QPointF(17, 7))
    sp = _pen(QColor(255, 220, 100), 1.4)
    p.setPen(sp)
    cx, cy, s = 19, 5, 3
    p.drawLine(QPointF(cx, cy - s), QPointF(cx, cy + s))
    p.drawLine(QPointF(cx - s, cy), QPointF(cx + s, cy))
    p.drawLine(QPointF(cx - 2, cy - 2), QPointF(cx + 2, cy + 2))
    p.drawLine(QPointF(cx + 2, cy - 2), QPointF(cx - 2, cy + 2))
    p.end()
    return QIcon(pix)


def _ico_crop() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(width=2.0))
    p.drawLine(QPointF(5, 4), QPointF(5, 15))
    p.drawLine(QPointF(5, 4), QPointF(16, 4))
    p.drawLine(QPointF(19, 20), QPointF(19, 9))
    p.drawLine(QPointF(19, 20), QPointF(8, 20))
    p.end()
    return QIcon(pix)


def _ico_eyedropper() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(width=1.6))
    path = QPainterPath()
    path.moveTo(6, 20)
    path.lineTo(9, 17)
    path.lineTo(17, 9)
    path.lineTo(19, 11)
    path.lineTo(11, 19)
    path.lineTo(8, 22)
    path.closeSubpath()
    p.drawPath(path)
    p.setBrush(QBrush(_CLR2))
    p.drawEllipse(QPointF(18, 6), 3, 3)
    p.setPen(_pen(width=1.2))
    p.drawLine(QPointF(6, 20), QPointF(4, 22))
    p.end()
    return QIcon(pix)


def _ico_healing() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(width=1.6))
    c = _ICO / 2
    w, h = 4, 10
    p.setBrush(QBrush(QColor(180, 180, 180, 60)))
    p.drawRoundedRect(QRectF(c - w, c - h, w * 2, h * 2), 2, 2)
    p.drawRoundedRect(QRectF(c - h, c - w, h * 2, w * 2), 2, 2)
    p.end()
    return QIcon(pix)


def _ico_clone_stamp() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(width=1.5))
    p.drawLine(QPointF(12, 4), QPointF(12, 10))
    p.setBrush(QBrush(QColor(180, 180, 180, 80)))
    p.drawRoundedRect(QRectF(5, 10, 14, 5), 2, 2)
    p.drawLine(QPointF(4, 18), QPointF(20, 18))
    p.drawEllipse(QPointF(12, 4), 2.5, 2)
    p.end()
    return QIcon(pix)


def _ico_brush() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(width=1.4))
    p.drawLine(QPointF(18, 3), QPointF(10, 13))
    p.setPen(_pen(width=2.2))
    p.drawLine(QPointF(10, 13), QPointF(8, 16))
    path = QPainterPath()
    path.moveTo(8, 16)
    path.cubicTo(6, 18, 4, 20, 5, 21)
    path.cubicTo(6, 22, 8, 20, 8, 16)
    p.setPen(_pen(width=1.0))
    p.setBrush(QBrush(_CLR))
    p.drawPath(path)
    p.end()
    return QIcon(pix)


def _ico_eraser() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(width=1.4))
    poly = QPolygonF([
        QPointF(7, 19), QPointF(4, 14),
        QPointF(14, 5), QPointF(20, 7),
        QPointF(10, 16), QPointF(7, 19),
    ])
    p.setBrush(QBrush(QColor(200, 170, 170, 100)))
    p.drawPolygon(poly)
    p.drawLine(QPointF(10, 16), QPointF(4, 14))
    p.end()
    return QIcon(pix)


def _ico_gradient() -> QIcon:
    pix, p = _px()
    r = QRectF(4, 5, _ICO - 8, _ICO - 10)
    grad = QLinearGradient(r.topLeft(), r.topRight())
    grad.setColorAt(0.0, QColor(40, 40, 40))
    grad.setColorAt(1.0, QColor(220, 220, 220))
    p.setPen(_pen(width=1.2))
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(r, 2, 2)
    p.end()
    return QIcon(pix)


def _ico_paint_bucket() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(width=1.4))
    path = QPainterPath()
    path.moveTo(6, 8)
    path.lineTo(6, 18)
    path.lineTo(16, 18)
    path.lineTo(18, 8)
    path.closeSubpath()
    p.setBrush(QBrush(QColor(180, 180, 180, 80)))
    p.drawPath(path)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(8, 3, 8, 8), 30 * 16, 120 * 16)
    p.setPen(_pen(QColor(100, 160, 220), 1.4))
    p.setBrush(QBrush(QColor(100, 160, 220)))
    drop = QPainterPath()
    drop.moveTo(20, 14)
    drop.cubicTo(20, 16, 18, 19, 20, 19)
    drop.cubicTo(22, 19, 20, 16, 20, 14)
    p.drawPath(drop)
    p.end()
    return QIcon(pix)


def _ico_text() -> QIcon:
    pix, p = _px()
    p.setPen(_CLR)
    f = QFont("Georgia", 16, QFont.Weight.Bold)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    p.setFont(f)
    p.drawText(QRectF(0, 0, _ICO, _ICO), Qt.AlignmentFlag.AlignCenter, "T")
    p.end()
    return QIcon(pix)


def _ico_shape() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(width=1.4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(4, 6, 10, 10))
    p.drawEllipse(QPointF(17, 13), 5, 5)
    p.end()
    return QIcon(pix)


def _ico_zoom() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(width=1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(10, 10), 6.5, 6.5)
    p.setPen(_pen(width=2.2))
    p.drawLine(QPointF(15, 15), QPointF(21, 21))
    p.setPen(_pen(width=1.2))
    p.drawLine(QPointF(10, 7.5), QPointF(10, 12.5))
    p.drawLine(QPointF(7.5, 10), QPointF(12.5, 10))
    p.end()
    return QIcon(pix)


def _ico_pan() -> QIcon:
    pix, p = _px()
    p.setPen(_pen(width=1.3))
    path = QPainterPath()
    path.moveTo(8, 20)
    path.cubicTo(5, 17, 5, 13, 6, 10)
    path.lineTo(6, 8)
    path.cubicTo(6, 6, 8, 6, 8, 8)
    path.lineTo(8, 7)
    path.cubicTo(8, 5, 10, 5, 10, 7)
    path.lineTo(10, 6)
    path.cubicTo(10, 4, 12, 4, 12, 6)
    path.lineTo(12, 7)
    path.cubicTo(12, 5, 14, 5, 14, 7)
    path.lineTo(14, 8)
    path.lineTo(14, 10)
    path.cubicTo(16, 10, 18, 12, 18, 15)
    path.cubicTo(18, 18, 15, 21, 12, 21)
    path.lineTo(8, 20)
    p.setBrush(QBrush(QColor(200, 200, 200, 50)))
    p.drawPath(path)
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
    ToolType.SHAPE: _ico_shape,
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

class _ToolFlyout(QFrame):
    """Floating popup that appears beside a tool-group button to reveal
    all tools within the group."""

    tool_picked = Signal(ToolType)

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(
            "QFrame { background: #3a3a3a; border: 1px solid #555; border-radius: 4px; }"
        )
        self._layout = QVBoxLayout(self)
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

        for tool_type, label, shortcut in tools:
            btn = QToolButton()
            btn.setIcon(_tool_icon(tool_type))
            btn.setIconSize(QSize(_ICO, _ICO))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setText(f"  {label}  ({shortcut})")
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
        self.tool_picked.emit(tool_type)
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
        self.setStyleSheet(
            "QToolButton { background: transparent; border: 1px solid transparent;"
            "              border-radius: 4px; padding: 3px; }"
            "QToolButton:hover { background: #444; border-color: #555; }"
            "QToolButton:checked { background: #4a6fa5; border-color: #5a7fb5; }"
        )
        self._update_icon()

        self._flyout: _ToolFlyout | None = None
        if len(tools) > 1:
            self._flyout = _ToolFlyout()
            self._flyout.tool_picked.connect(self._on_flyout_pick)

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
        tt, label, shortcut = self._tools[self._active_index]
        self.setIcon(_tool_icon(tt))
        extra = "  (right-click for more)" if len(self._tools) > 1 else ""
        self.setToolTip(f"{label} ({shortcut}){extra}")

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
        self.setStyleSheet(
            "QToolBar { background: #333; border: none; spacing: 0px; padding: 4px 0px; }"
            "QToolBar QWidget { background: transparent; }"
            "QToolBar::separator { background: #444; height: 1px; margin: 4px 6px; }"
        )

        self._group_buttons: list[_ToolGroupButton] = []
        self._tool_to_group: dict[ToolType, _ToolGroupButton] = {}
        self._mgr = ColorManager.instance()
        self._build()

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
        self._fg_bg.swap_requested.connect(self._mgr.swap)
        self._fg_bg.reset_requested.connect(self._mgr.reset)
        self.addWidget(self._centered_wrapper(self._fg_bg, v_margin=4))

        self._mgr.foreground_changed.connect(self._on_color_changed)
        self._mgr.background_changed.connect(self._on_color_changed)
        self._fg_bg.set_colors(self._mgr.foreground, self._mgr.background)

    def _on_tool_activated(self, tool_type: ToolType) -> None:
        sender = self._tool_to_group.get(tool_type)
        for gbtn in self._group_buttons:
            gbtn.setChecked(gbtn is sender)
        self.tool_selected.emit(tool_type)

    def _on_color_changed(self, _color=None) -> None:
        self._fg_bg.set_colors(self._mgr.foreground, self._mgr.background)

    def select_tool(self, tool_type: ToolType) -> None:
        gbtn = self._tool_to_group.get(tool_type)
        if gbtn:
            gbtn.set_active_tool(tool_type)
            for b in self._group_buttons:
                b.setChecked(b is gbtn)
            self.tool_selected.emit(tool_type)
