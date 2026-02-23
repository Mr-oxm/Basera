"""Tabbed color dropdown — reusable popup with Swatches, Color, Gradient tabs.

This widget is a button showing the current color that, when clicked, opens
a floating popup with three tabs:
  • Swatches  — palette grid + recent
  • Color     — RGB/HSV/HSL/CMYK sliders + hex
  • Gradient  — interactive gradient editor

Designed for use in the properties panel or anywhere a color picker is needed.
Routes through ``ColorManager`` for global sync.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPoint, QRectF, QSize, QTimer
from PySide6.QtGui import (
    QColor,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabBar,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
    QApplication,
    QGraphicsDropShadowEffect,
)

from ...core.color import Color, GradientStop
from ...core.color_engine import ColorManager
from ...vector.style import FillPaint, SolidPaint, GradientPaint, GradientType
from .color_sliders import ColorSliders
from .color_wheel import ColorWheel
from .gradient_editor import GradientEditor
from .swatch_grid import SwatchGrid


# ============================================================================
# Tab bar styled for the popup
# ============================================================================

_TAB_STYLE = """
QTabBar {
    background: transparent;
    border: none;
}
QTabBar::tab {
    background: #333;
    color: #999;
    border: none;
    padding: 6px 14px;
    font-size: 11px;
    font-weight: 600;
    font-family: 'Segoe UI', 'Inter', sans-serif;
    border-bottom: 2px solid transparent;
    margin-right: 1px;
}
QTabBar::tab:hover {
    color: #ccc;
    background: #3a3a3a;
}
QTabBar::tab:selected {
    color: #e0e0e0;
    background: #3a3a3a;
    border-bottom: 2px solid #5a8abf;
}
"""


# ============================================================================
# Popup panel (the floating dropdown)
# ============================================================================

class _ColorPopup(QWidget):
    """Floating popup with tabbed color content.

    Parameters
    ----------
    show_gradient : bool
        If *True* the Gradient tab is included.
    show_wheel : bool
        If *True* a compact ``ColorWheel`` is shown above the sliders
        in the Color tab.
    """

    color_changed = Signal(object)       # Color — live preview
    color_committed = Signal(object)     # Color — final pick
    gradient_changed = Signal(object)    # ColorFill

    def __init__(
        self,
        *,
        show_gradient: bool = True,
        show_wheel: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumWidth(260)

        self._show_gradient = show_gradient
        self._show_wheel = show_wheel

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 80))

        # Inner container to apply shadow to
        self._container = QWidget(self)
        self._container.setObjectName("popupContainer")
        self._container.setGraphicsEffect(shadow)
        self._container.setStyleSheet(
            "#popupContainer {"
            "  background: #2e2e2e;"
            "  border: 1px solid #444;"
            "  border-radius: 8px;"
            "}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)  # room for shadow
        outer.addWidget(self._container)

        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Tab bar
        self._tabs = QTabBar()
        self._tabs.setStyleSheet(_TAB_STYLE)
        self._tabs.setExpanding(False)
        self._tabs.setDocumentMode(True)
        self._tabs.addTab("Swatches")
        self._tabs.addTab("Color")
        if show_gradient:
            self._tabs.addTab("Gradient")
        self._tabs.currentChanged.connect(self._on_tab)
        layout.addWidget(self._tabs)

        # Stacked pages
        self._stack = QStackedWidget()
        layout.addWidget(self._stack, 1)

        # Page 0: Swatches
        self._swatches = SwatchGrid()
        self._stack.addWidget(self._swatches)

        # Page 1: Color (optional wheel + sliders)
        color_page = QWidget()
        color_lay = QVBoxLayout(color_page)
        color_lay.setContentsMargins(0, 0, 0, 0)
        color_lay.setSpacing(4)

        self._wheel: ColorWheel | None = None
        if show_wheel:
            self._wheel = ColorWheel()
            self._wheel.setFixedHeight(160)
            self._wheel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            color_lay.addWidget(self._wheel)

        self._sliders = ColorSliders()
        color_lay.addWidget(self._sliders)
        self._stack.addWidget(color_page)

        # Page 2 (optional): Gradient editor
        self._gradient: GradientEditor | None = None
        if show_gradient:
            self._gradient = GradientEditor()
            self._stack.addWidget(self._gradient)

        # Wiring
        self._swatches.color_picked.connect(self._on_swatch_pick)
        self._sliders.color_changed.connect(self._on_slider_changed)
        self._sliders.color_committed.connect(self._on_slider_committed)
        if self._wheel:
            self._wheel.color_changed.connect(self._on_wheel_changed)
            self._wheel.color_committed.connect(self._on_wheel_committed)
        if self._gradient:
            self._gradient.gradient_changed.connect(self._on_gradient_changed)

        self._mgr = ColorManager.instance()
        self._mgr.history_changed.connect(self._swatches.refresh_recent)

        self._updating = False

    def set_color(self, c: Color) -> None:
        self._updating = True
        self._sliders.set_color(c)
        if self._wheel:
            self._wheel.set_color(c)
        self._updating = False

    def set_paint(self, paint: FillPaint) -> None:
        """Set the active paint (Solid or Gradient)."""
        self._updating = True
        
        if isinstance(paint, SolidPaint):
            c = Color(*paint.color)
            self._sliders.set_color(c)
            if self._wheel:
                self._wheel.set_color(c)
            
            # If we are on Gradient tab, maybe switch to Color or Swatches?
            # Prefer Color tab if coming from Gradient
            if self._tabs.currentIndex() == 2:
                self._tabs.setCurrentIndex(1)
                
        elif isinstance(paint, GradientPaint):
            if self._gradient:
                # Convert stops
                core_stops = [
                    GradientStop(s.offset, Color(*s.color)) 
                    for s in paint.stops
                ]
                self._gradient.set_stops(core_stops)
                
                # Set Type
                t_map = {
                    GradientType.LINEAR: "Linear",
                    GradientType.RADIAL: "Radial",
                    GradientType.CONICAL: "Conical",
                    GradientType.DIAMOND: "Diamond",
                }
                if paint.gradient_type in t_map:
                    self._gradient.set_gradient_type(t_map[paint.gradient_type])
                
                self._tabs.setCurrentIndex(2)
        
        self._updating = False

    def set_active_tab(self, index: int) -> None:
        """Programmatically switch to the tab at *index*."""
        if 0 <= index < self._tabs.count():
            self._tabs.setCurrentIndex(index)

    def _on_tab(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)

    def _on_swatch_pick(self, c: Color) -> None:
        self.color_committed.emit(c)

    def _on_slider_changed(self, c: Color) -> None:
        if not self._updating:
            self._updating = True
            if self._wheel:
                self._wheel.set_color(c)
            self._updating = False
            self.color_changed.emit(c)

    def _on_slider_committed(self, c: Color) -> None:
        if not self._updating:
            self.color_committed.emit(c)

    def _on_wheel_changed(self, c: Color) -> None:
        if not self._updating:
            self._updating = True
            self._sliders.set_color(c)
            self._updating = False
            self.color_changed.emit(c)

    def _on_wheel_committed(self, c: Color) -> None:
        if not self._updating:
            self.color_committed.emit(c)

    def _on_gradient_changed(self, fill) -> None:
        self.gradient_changed.emit(fill)

    def refresh_recent(self) -> None:
        self._swatches.refresh_recent()


# ============================================================================
# Color swatch button (the visible trigger)
# ============================================================================

class _ColorButton(QWidget):
    """Small rounded-rect button showing the current color or gradient."""

    clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._color = Color.black()
        self._gradient: GradientPaint | None = None
        self._hovered = False
        self.setFixedSize(32, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setToolTip("Click to open color picker")

    def set_color(self, c: Color) -> None:
        self._color = c
        self._gradient = None
        self.update()

    def set_gradient(self, grad: GradientPaint) -> None:
        self._gradient = grad
        self.update()

    def paintEvent(self, ev: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = 5.0

        # Checkerboard
        clip = QPainterPath()
        clip.addRoundedRect(rect, radius, radius)
        p.setClipPath(clip)
        cs = 4
        for y in range(int(rect.top()), int(rect.bottom()) + 1, cs):
            for x in range(int(rect.left()), int(rect.right()) + 1, cs):
                ix = (x - int(rect.left())) // cs
                iy = (y - int(rect.top())) // cs
                c = QColor(68, 68, 68) if (ix + iy) % 2 == 0 else QColor(88, 88, 88)
                p.fillRect(x, y, cs, cs, c)
        p.setClipping(False)

        if self._gradient is not None and self._gradient.stops:
            # Render gradient preview
            from PySide6.QtGui import QLinearGradient
            grad = QLinearGradient(rect.left(), rect.center().y(),
                                   rect.right(), rect.center().y())
            for stop in self._gradient.stops:
                r8, g8, b8, a8 = (int(stop.color[0] * 255),
                                   int(stop.color[1] * 255),
                                   int(stop.color[2] * 255),
                                   int(stop.color[3] * 255) if len(stop.color) > 3 else 255)
                # Support both vector.style (offset) and core.color (position) stops
                pos = getattr(stop, 'offset', None) or getattr(stop, 'position', 0.0)
                grad.setColorAt(pos, QColor(r8, g8, b8, a8))
            p.setBrush(grad)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, radius, radius)
        else:
            # Color fill
            r, g, b, a = self._color.to_rgb8()
            p.setBrush(QColor(r, g, b, a))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, radius, radius)

        # Border
        if self._hovered:
            p.setPen(QPen(QColor(255, 255, 255, 40), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, radius, radius)
            p.setPen(QPen(QColor(110, 180, 255, 100), 1.0))
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius - 1, radius - 1)
        else:
            p.setPen(QPen(QColor(255, 255, 255, 15), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, radius, radius)
        p.end()

    def enterEvent(self, ev) -> None:
        self._hovered = True
        self.update()

    def leaveEvent(self, ev) -> None:
        self._hovered = False
        self.update()

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


# ============================================================================
# Public: ColorDropdown (button + popup)
# ============================================================================

class ColorDropdown(QWidget):
    """A color-button that opens a tabbed popup (Swatches / Color / Gradient).

    Parameters
    ----------
    label : str
        Optional text label shown before the swatch button.
    show_gradient : bool
        Include the Gradient tab in the popup (default *True*).
    show_wheel : bool
        Include a colour wheel above the sliders in the Color tab
        (default *False*).

    Signals
    -------
    color_changed(Color)
        Live preview during slider drag.
    color_committed(Color)
        Final color pick (swatch click or slider release).
    gradient_changed(ColorFill)
        Gradient changed from the gradient tab.
    """

    color_changed = Signal(object)
    color_committed = Signal(object)
    gradient_changed = Signal(object)

    def __init__(
        self,
        label: str = "",
        *,
        show_gradient: bool = True,
        show_wheel: bool = False,
        default_tab: int = 0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._show_gradient = show_gradient
        self._show_wheel = show_wheel
        self._default_tab = default_tab

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        if label:
            lbl = QLabel(label)
            lbl.setStyleSheet(
                "color: #999; font-size: 11px; font-weight: 600;"
                "font-family: 'Segoe UI', 'Inter', sans-serif;"
            )
            layout.addWidget(lbl)

        self._btn = _ColorButton()
        self._btn.clicked.connect(self._toggle_popup)
        layout.addWidget(self._btn)

        self._popup: _ColorPopup | None = None
        self._color = Color.black()
        self._paint: FillPaint | None = None  # track active paint (Solid or Gradient)

    # ---- Public API ---------------------------------------------------------

    def color(self) -> Color:
        return self._color

    def set_color(self, c: Color) -> None:
        self._color = c
        self._paint = SolidPaint((c.r, c.g, c.b, c.a))
        self._btn.set_color(c)
        if self._popup and self._popup.isVisible():
            self._popup.set_color(c)

    def set_paint(self, paint: FillPaint) -> None:
        self._paint = paint
        if isinstance(paint, SolidPaint):
            self._color = Color(*paint.color)
            self._btn.set_color(self._color)
        elif isinstance(paint, GradientPaint):
            # Show gradient preview in button
            eff = paint.color_at(0.5)
            self._color = Color(*eff)
            self._btn.set_gradient(paint)
            
        self._ensure_popup()
        self._popup.set_paint(paint)

    # ---- Popup management ---------------------------------------------------

    def _ensure_popup(self) -> None:
        if self._popup is None:
            self._popup = _ColorPopup(
                show_gradient=self._show_gradient,
                show_wheel=self._show_wheel,
            )
            self._popup.color_changed.connect(self._on_live)
            self._popup.color_committed.connect(self._on_commit)
            self._popup.gradient_changed.connect(self._on_gradient_from_popup)

    def _toggle_popup(self) -> None:
        self._ensure_popup()
        if self._popup.isVisible():
            self._popup.hide()
        else:
            # Restore the full paint state (gradient or solid)
            if isinstance(self._paint, GradientPaint):
                self._popup.set_paint(self._paint)
            else:
                self._popup.set_color(self._color)
            # Position below the button
            pos = self._btn.mapToGlobal(QPoint(0, self._btn.height() + 4))
            self._popup.move(pos)
            self._popup.show()
            # Apply default tab on first open (or always for gradient mode)
            if self._default_tab:
                self._popup.set_active_tab(self._default_tab)

    def _on_gradient_from_popup(self, fill) -> None:
        """Update button preview when gradient changes in the popup."""
        # Convert core ColorFill to a GradientPaint for button preview
        from ...core.color import LinearGradient, RadialGradient
        from ...core.color_engine import ConicalGradient, DiamondGradient
        if isinstance(fill, (LinearGradient, RadialGradient, ConicalGradient, DiamondGradient)):
            from ...vector.style import GradientType as GT, GradientStop as VGS
            gtype = GT.LINEAR
            if isinstance(fill, RadialGradient):
                gtype = GT.RADIAL
            elif isinstance(fill, ConicalGradient):
                gtype = GT.CONICAL
            elif isinstance(fill, DiamondGradient):
                gtype = GT.DIAMOND
            stops = [
                VGS(s.position, (s.color.r, s.color.g, s.color.b, s.color.a))
                for s in fill.stops
            ]
            gpaint = GradientPaint(gradient_type=gtype, stops=stops)
            self._paint = gpaint
            self._btn.set_gradient(gpaint)
        self.gradient_changed.emit(fill)

    def _on_live(self, c: Color) -> None:
        self._color = c
        self._paint = SolidPaint((c.r, c.g, c.b, c.a))
        self._btn.set_color(c)
        self.color_changed.emit(c)

    def _on_commit(self, c: Color) -> None:
        self._color = c
        self._paint = SolidPaint((c.r, c.g, c.b, c.a))
        self._btn.set_color(c)
        self.color_committed.emit(c)
