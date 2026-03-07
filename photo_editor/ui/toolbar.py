"""Main toolbar with grouped tool buttons, flyout sub-toolbars, and FG/BG colour swatches."""

from __future__ import annotations

from PySide6.QtCore import (
    Qt, Signal, QSize, QRectF, QPointF, QPoint, QTimer,
)
from PySide6.QtGui import (
    QColor, QPen, QBrush, QPainter, QMouseEvent, QPaintEvent,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QToolBar, QToolButton, QWidget, QVBoxLayout, QHBoxLayout,
    QSizePolicy, QFrame,
)

from ..core.color import Color
from ..core.color_engine import ColorManager
from ..core.enums import ToolType
from .icons import tool_icon, update_tool_icon_colors
from .shortcut_manager import ShortcutManager
from .styles import render_qss

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
        self._container.setStyleSheet(render_qss("tool_flyout_container.qss", palette))
        
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
        from .theme import ThemeManager
        palette = ThemeManager.instance().active_palette

        for tool_type, label, _ in tools:
            btn = QToolButton()
            btn.setIcon(tool_icon(tool_type))
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
            btn.setStyleSheet(render_qss("tool_flyout_button.qss", palette))
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
        self.setIcon(tool_icon(tt))
        
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
        self.setStyleSheet(render_qss("toolbar.qss", palette))
        update_tool_icon_colors(palette)
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
