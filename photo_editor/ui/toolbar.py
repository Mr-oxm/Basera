"""Main toolbar with tool buttons, icons, quick-access controls, and active colour circle."""

from PySide6.QtCore import Qt, Signal, QSize, QRectF, QPointF
from PySide6.QtGui import (
    QAction, QActionGroup, QFont, QIcon, QPixmap, QPainter,
    QColor, QPen, QBrush, QConicalGradient, QMouseEvent, QPaintEvent,
)
from PySide6.QtWidgets import QToolBar, QToolButton, QWidget, QSizePolicy

from ..core.color import Color
from ..core.color_engine import ColorManager
from ..core.enums import ToolType

# Tool info: (shortcut, label, icon_char)
_TOOLS: list[tuple[ToolType, str, str, str]] = [
    (ToolType.MOVE,           "V", "Move",            "\u2725"),
    (ToolType.BRUSH,          "B", "Brush",           "\u270E"),
    (ToolType.ERASER,         "E", "Eraser",          "\u2702"),
    (ToolType.CLONE_STAMP,    "S", "Clone Stamp",     "\u2399"),
    (ToolType.HEALING_BRUSH,  "J", "Healing Brush",   "\u2695"),
    (ToolType.GRADIENT,       "G", "Gradient",        "\u25A8"),
    (ToolType.PAINT_BUCKET,   "K", "Paint Bucket",    "\u25FC"),
    (ToolType.RECT_SELECT,    "M", "Rect Select",     "\u25A1"),
    (ToolType.ELLIPSE_SELECT, "M", "Ellipse Select",  "\u25CB"),
    (ToolType.LASSO,          "L", "Lasso",           "\u27E1"),
    (ToolType.MAGIC_WAND,     "W", "Magic Wand",      "\u2728"),
    (ToolType.TEXT,            "T", "Text",            "\u0054"),
    (ToolType.SHAPE,          "U", "Shape",           "\u25B3"),
    (ToolType.ZOOM,           "Z", "Zoom",            "\u2315"),
    (ToolType.PAN,            "H", "Pan",             "\u270B"),
    (ToolType.EYEDROPPER,     "I", "Eyedropper",      "\u2316"),
    (ToolType.CROP,           "C", "Crop",            "\u2B1A"),
]


def _make_icon(char: str, size: int = 28) -> QIcon:
    """Create a simple text-based icon pixmap."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setPen(QColor(220, 220, 220))
    font = QFont("Segoe UI Symbol", int(size * 0.52))
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    p.setFont(font)
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, char)
    p.end()
    return QIcon(pix)


# ============================================================================
# Active colour circle indicator
# ============================================================================

class _ColorCircleWidget(QWidget):
    """Displays FG/BG colors as overlapping circles in the toolbar.

    Clicking swaps; double-clicking resets to black/white.
    Shows a thin rainbow hue ring around the foreground circle.
    """

    swap_requested = Signal()
    reset_requested = Signal()

    _SIZE = 44

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(self._SIZE, self._SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("FG/BG – click to swap, double-click to reset")
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
        cx, cy = s / 2.0, s / 2.0
        outer_r = s / 2.0 - 2

        # Thin hue ring
        ring_w = 3
        grad = QConicalGradient(cx, cy, 0)
        from ..core.color_engine import hsv_to_rgb as _h2r
        for i in range(0, 361, 10):
            r, g, b = _h2r(float(i), 1.0, 1.0)
            grad.setColorAt(i / 360.0, QColor.fromRgbF(r, g, b))
        pen = QPen(QBrush(grad), ring_w)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), outer_r - ring_w / 2, outer_r - ring_w / 2)

        # Background circle (bottom-right, smaller)
        bg_r = outer_r * 0.38
        bg_cx = cx + 6
        bg_cy = cy + 5
        r, g, b, a = self._bg.to_rgb8()
        p.setPen(QPen(QColor(80, 80, 80), 1))
        p.setBrush(QColor(r, g, b, a))
        p.drawEllipse(QPointF(bg_cx, bg_cy), bg_r, bg_r)

        # Foreground circle (center, larger)
        fg_r = outer_r * 0.48
        fg_cx = cx - 3
        fg_cy = cy - 2
        r, g, b, a = self._fg.to_rgb8()
        p.setPen(QPen(QColor(200, 200, 200), 1.5))
        p.setBrush(QColor(r, g, b, a))
        p.drawEllipse(QPointF(fg_cx, fg_cy), fg_r, fg_r)

        p.end()

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self.swap_requested.emit()

    def mouseDoubleClickEvent(self, ev: QMouseEvent) -> None:
        self.reset_requested.emit()


class EditorToolbar(QToolBar):
    """Vertical tool bar on the left side of the editor."""

    tool_selected = Signal(ToolType)

    def __init__(self, parent=None) -> None:
        super().__init__("Tools", parent)
        self.setIconSize(QSize(28, 28))
        self._group = QActionGroup(self)
        self._group.setExclusive(True)
        self._actions: dict[ToolType, QAction] = {}
        self._mgr = ColorManager.instance()
        self._build()

    def _build(self) -> None:
        for tool_type, shortcut, label, icon_char in _TOOLS:
            action = QAction(_make_icon(icon_char), label, self)
            action.setCheckable(True)
            action.setToolTip(f"{label} ({shortcut})")
            action.setData(tool_type)
            action.triggered.connect(
                lambda checked, t=tool_type: self.tool_selected.emit(t),
            )
            self._group.addAction(action)
            self._actions[tool_type] = action
            self.addAction(action)

        if ToolType.BRUSH in self._actions:
            self._actions[ToolType.BRUSH].setChecked(True)

        # ---- Active colour circle at the bottom of the toolbar ----
        self.addSeparator()
        self._color_circle = _ColorCircleWidget()
        self._color_circle.swap_requested.connect(self._mgr.swap)
        self._color_circle.reset_requested.connect(self._mgr.reset)
        self.addWidget(self._color_circle)

        # Keep circle in sync with manager
        self._mgr.foreground_changed.connect(self._on_color_changed)
        self._mgr.background_changed.connect(self._on_color_changed)
        self._color_circle.set_colors(self._mgr.foreground, self._mgr.background)

    def _on_color_changed(self, _color=None) -> None:
        self._color_circle.set_colors(self._mgr.foreground, self._mgr.background)

    def select_tool(self, tool_type: ToolType) -> None:
        action = self._actions.get(tool_type)
        if action:
            action.setChecked(True)
            self.tool_selected.emit(tool_type)
