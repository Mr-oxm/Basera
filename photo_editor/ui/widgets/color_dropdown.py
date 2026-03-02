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
from ..theme import ThemeManager


# ============================================================================
# Tab bar styled for the popup
# ============================================================================

def _tab_style(palette: dict) -> str:
    return f"""
QTabBar {{
    background: transparent;
    border: none;
}}
QTabBar::tab {{
    background: {palette['bg2']};
    color: {palette['fg_dim']};
    border: none;
    padding: 6px 14px;
    font-size: 11px;
    font-weight: 600;
    font-family: 'Segoe UI', 'Inter', sans-serif;
    border-bottom: 2px solid transparent;
    margin-right: 1px;
}}
QTabBar::tab:hover {{
    color: {palette['fg']};
    background: {palette['hover']};
}}
QTabBar::tab:selected {{
    color: {palette.get('fg_accent', '#ffffff')};
    background: {palette['bg1']};
    border-bottom: 2px solid {palette['accent']};
}}
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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)  # room for shadow
        outer.addWidget(self._container)

        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Tab bar
        self._tabs = QTabBar()
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

        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._apply_theme(ThemeManager.instance().active_palette)

        self._updating = False

    def _apply_theme(self, palette: dict) -> None:
        self._container.setStyleSheet(
            "#popupContainer {"
            f"  background: {palette['bg2']};"
            f"  border: 1px solid {palette['border']};"
            "  border-radius: 8px;"
            "}"
        )
        self._tabs.setStyleSheet(_tab_style(palette))

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
    """Small rounded-rect button showing the current color or gradient.

    When *none_mode* is True the swatch shows a red ⊘ (no-entry) symbol
    indicating that fill or stroke is disabled.
    """

    clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._color = Color.black()
        self._gradient: GradientPaint | None = None
        self._hovered = False
        self._none_mode = False
        self.setFixedSize(32, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setToolTip("Click to open color picker")

    def set_none_mode(self, none: bool) -> None:
        self._none_mode = none
        self.update()

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

        # Checkerboard background (always drawn)
        clip = QPainterPath()
        clip.addRoundedRect(rect, radius, radius)
        p.setClipPath(clip)
        cs = 4
        palette = ThemeManager.instance().active_palette
        c1 = QColor(palette['bg1']).darker(110)
        c2 = QColor(palette['bg1']).lighter(110)
        for y in range(int(rect.top()), int(rect.bottom()) + 1, cs):
            for x in range(int(rect.left()), int(rect.right()) + 1, cs):
                ix = (x - int(rect.left())) // cs
                iy = (y - int(rect.top())) // cs
                c = c1 if (ix + iy) % 2 == 0 else c2
                p.fillRect(x, y, cs, cs, c)
        p.setClipping(False)

        if self._none_mode:
            # Draw ⊘ stop-sign: thin circle + diagonal line in vivid red
            cx = rect.center().x()
            cy = rect.center().y()
            r_val = min(rect.width(), rect.height()) / 2.0 - 2.0
            red = QColor(220, 50, 50)
            p.setPen(QPen(red, 2.0, Qt.PenStyle.SolidLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - r_val, cy - r_val, r_val * 2, r_val * 2))
            diag = r_val * 0.70
            p.drawLine(
                QRectF(cx - diag, cy - diag, diag * 2, diag * 2).bottomLeft(),
                QRectF(cx - diag, cy - diag, diag * 2, diag * 2).topRight(),
            )
        elif self._gradient is not None and self._gradient.stops:
            # Render gradient preview
            from PySide6.QtGui import QLinearGradient
            grad = QLinearGradient(rect.left(), rect.center().y(),
                                   rect.right(), rect.center().y())
            for stop in self._gradient.stops:
                r8, g8, b8, a8 = (int(stop.color[0] * 255),
                                   int(stop.color[1] * 255),
                                   int(stop.color[2] * 255),
                                   int(stop.color[3] * 255) if len(stop.color) > 3 else 255)
                pos = getattr(stop, 'offset', None) or getattr(stop, 'position', 0.0)
                grad.setColorAt(pos, QColor(r8, g8, b8, a8))
            p.setBrush(grad)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, radius, radius)
        else:
            # Solid color fill
            r, g, b, a = self._color.to_rgb8()
            p.setBrush(QColor(r, g, b, a))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, radius, radius)

        # Border
        if self._hovered:
            p.setPen(QPen(QColor(palette['border_light']), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, radius, radius)
            p.setPen(QPen(QColor(palette['accent']), 1.0))
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius - 1, radius - 1)
        else:
            p.setPen(QPen(QColor(palette['border']), 1.0))
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
    none_toggled = Signal(bool)   # True = none/disabled, False = has paint

    def __init__(
        self,
        label: str = "",
        *,
        show_gradient: bool = True,
        show_wheel: bool = False,
        default_tab: int = 0,
        show_none_btn: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._show_gradient = show_gradient
        self._show_wheel = show_wheel
        self._default_tab = default_tab
        self._is_none = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        if label:
            self._lbl = QLabel(label)
            layout.addWidget(self._lbl)

        self._btn = _ColorButton()
        self._btn.clicked.connect(self._toggle_popup)
        layout.addWidget(self._btn)

        # Optional ⊘ toggle button to disable fill/stroke
        self._none_btn: QPushButton | None = None
        if show_none_btn:
            self._none_btn = QPushButton("⊘")
            self._none_btn.setFixedSize(18, 18)
            self._none_btn.setCheckable(True)
            self._none_btn.setToolTip("Toggle none (disable fill/stroke)")
            self._none_btn.setStyleSheet(
                "QPushButton { font-size: 11px; padding: 0; border: 1px solid rgba(255,255,255,0.1);"
                " border-radius: 3px; background: rgba(0,0,0,0.2); color: #888; }"
                "QPushButton:checked { color: #e05555; border-color: #c04040;"
                " background: rgba(200,40,40,0.2); }"
                "QPushButton:hover { background: rgba(255,255,255,0.1); }"
            )
            self._none_btn.toggled.connect(self._on_none_toggled)
            layout.addWidget(self._none_btn)

        self._popup: _ColorPopup | None = None
        self._color = Color.black()
        self._paint: FillPaint | None = None  # track active paint (Solid or Gradient)

        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._apply_theme(ThemeManager.instance().active_palette)

    def _apply_theme(self, palette: dict) -> None:
        if hasattr(self, '_lbl') and self._lbl:
            self._lbl.setStyleSheet(
                f"color: {palette['fg_dim']}; font-size: 11px; font-weight: 600;"
                "font-family: 'Segoe UI', 'Inter', sans-serif;"
            )
        self._btn.update()

    # ---- None toggle --------------------------------------------------------

    def _on_none_toggled(self, checked: bool) -> None:
        self._is_none = checked
        self._btn.set_none_mode(checked)
        self.none_toggled.emit(checked)

    def set_none(self, none: bool) -> None:
        """Programmatically set the none state (disables/re-enables the paint)."""
        self._is_none = none
        self._btn.set_none_mode(none)
        if self._none_btn is not None:
            self._none_btn.blockSignals(True)
            self._none_btn.setChecked(none)
            self._none_btn.blockSignals(False)

    def is_none(self) -> bool:
        return self._is_none

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
