"""Main toolbar with tool buttons, icons, and quick-access controls."""

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction, QActionGroup, QFont, QIcon, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QToolBar, QToolButton

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


class EditorToolbar(QToolBar):
    """Vertical tool bar on the left side of the editor."""

    tool_selected = Signal(ToolType)

    def __init__(self, parent=None) -> None:
        super().__init__("Tools", parent)
        self.setIconSize(QSize(28, 28))
        self._group = QActionGroup(self)
        self._group.setExclusive(True)
        self._actions: dict[ToolType, QAction] = {}
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

    def select_tool(self, tool_type: ToolType) -> None:
        action = self._actions.get(tool_type)
        if action:
            action.setChecked(True)
            self.tool_selected.emit(tool_type)
