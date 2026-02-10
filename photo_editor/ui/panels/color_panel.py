"""Color panel — compact wheel + opacity slider.

Layout:
 ┌─────────────────────────────┐
 │  FG / BG swatches ⇄ Swap   │
 ├─────────────────────────────┤
 │  ┌─────────────────────┐    │
 │  │  HSV Colour Wheel   │    │
 │  │  (ring + triangle)  │    │
 │  └─────────────────────┘    │
 ├─────────────────────────────┤
 │  Opacity slider             │
 └─────────────────────────────┘

Everything routes through ``ColorManager`` so the whole app
stays in sync automatically.

For full color editing (sliders, swatches, gradient), use the
``ColorDropdown`` widget placed in the properties panel.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QMouseEvent,
    QPaintEvent,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
    QFrame,
)

from ...core.color import Color
from ...core.color_engine import ColorManager
from ..widgets.color_wheel import ColorWheel


# ============================================================================
# FG/BG Swatch pair (overlapping rounded squares)
# ============================================================================

class _FgBgSwatch(QWidget):
    """Foreground/background colour indicator — modern overlapping rounded squares."""

    fg_clicked = Signal()
    bg_clicked = Signal()
    swap_clicked = Signal()
    reset_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(68, 58)
        self._fg = Color.black()
        self._bg = Color.white()
        self._editing_fg = True
        self.setMouseTracking(True)

    def set_colors(self, fg: Color, bg: Color) -> None:
        self._fg = fg
        self._bg = bg
        self.update()

    @property
    def editing_fg(self) -> bool:
        return self._editing_fg

    def paintEvent(self, ev: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = 5.0

        # Background swatch (behind, offset)
        bg_rect = QRectF(20, 16, 34, 34)
        r, g, b, a = self._bg.to_rgb8()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 30))
        p.drawRoundedRect(bg_rect.adjusted(1, 1, 1, 1), radius, radius)
        p.setBrush(QColor(r, g, b, a))
        border = QColor(180, 180, 180) if not self._editing_fg else QColor(80, 80, 80)
        p.setPen(QPen(border, 1.5 if not self._editing_fg else 1.0))
        p.drawRoundedRect(bg_rect, radius, radius)

        # Foreground swatch (front, offset)
        fg_rect = QRectF(4, 2, 34, 34)
        r, g, b, a = self._fg.to_rgb8()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawRoundedRect(fg_rect.adjusted(1, 1, 1, 1), radius, radius)
        p.setBrush(QColor(r, g, b, a))
        border = QColor(220, 220, 220) if self._editing_fg else QColor(80, 80, 80)
        p.setPen(QPen(border, 1.5 if self._editing_fg else 1.0))
        p.drawRoundedRect(fg_rect, radius, radius)

        # Swap icon
        p.setPen(QColor(150, 150, 150))
        font = p.font()
        font.setPixelSize(11)
        p.setFont(font)
        p.drawText(52, 13, "⇄")
        p.drawText(4, 56, "◧")
        p.end()

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        x, y = ev.position().x(), ev.position().y()
        if x > 46 and y < 18:
            self.swap_clicked.emit()
            return
        if x < 18 and y > 44:
            self.reset_clicked.emit()
            return
        fg_rect = QRectF(4, 2, 34, 34)
        if fg_rect.contains(x, y):
            self._editing_fg = True
            self.fg_clicked.emit()
            self.update()
            return
        bg_rect = QRectF(20, 16, 34, 34)
        if bg_rect.contains(x, y):
            self._editing_fg = False
            self.bg_clicked.emit()
            self.update()
            return


# ============================================================================
# Opacity slider — rounded gradient bar showing alpha
# ============================================================================

class _OpacitySlider(QWidget):
    """Rounded pill-shaped opacity slider showing color→transparent gradient."""

    value_changed = Signal(float)       # 0→1, live
    value_committed = Signal(float)     # 0→1, on release

    _TRACK_H = 14
    _THUMB_R = 7
    _MARGIN_X = 8

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._value = 1.0
        self._color = Color.black()
        self._dragging = False
        self.setFixedHeight(self._TRACK_H + 6)
        self.setMinimumWidth(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    def set_value(self, v: float) -> None:
        v = max(0.0, min(1.0, v))
        if v != self._value:
            self._value = v
            self.update()

    def value(self) -> float:
        return self._value

    def set_color(self, c: Color) -> None:
        self._color = c
        self.update()

    def _track_rect(self) -> QRectF:
        h = self._TRACK_H
        y = (self.height() - h) / 2.0
        return QRectF(self._MARGIN_X, y, self.width() - 2 * self._MARGIN_X, h)

    def _thumb_center(self) -> QPointF:
        tr = self._track_rect()
        return QPointF(tr.left() + self._value * tr.width(), tr.center().y())

    def paintEvent(self, ev: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        tr = self._track_rect()
        radius = tr.height() / 2.0

        # Checkerboard clipped to track
        clip = QPainterPath()
        clip.addRoundedRect(tr, radius, radius)
        p.setClipPath(clip)
        cs = 5
        for y in range(int(tr.top()), int(tr.bottom()) + 1, cs):
            for x in range(int(tr.left()), int(tr.right()) + 1, cs):
                ix = (x - int(tr.left())) // cs
                iy = (y - int(tr.top())) // cs
                c = QColor(68, 68, 68) if (ix + iy) % 2 == 0 else QColor(88, 88, 88)
                p.fillRect(x, y, cs, cs, c)

        # Alpha gradient
        r, g, b, _ = self._color.to_rgb8()
        grad = QLinearGradient(tr.left(), 0, tr.right(), 0)
        grad.setColorAt(0, QColor(r, g, b, 0))
        grad.setColorAt(1, QColor(r, g, b, 255))
        p.setBrush(grad)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(tr, radius, radius)
        p.setClipping(False)

        # Border
        p.setPen(QPen(QColor(55, 55, 55), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(tr.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        # Thumb
        tc = self._thumb_center()
        rad = self._THUMB_R + (1 if self._dragging else 0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawEllipse(tc + QPointF(0, 1), rad + 1, rad + 1)
        p.setBrush(QColor(255, 255, 255))
        p.setPen(QPen(QColor(40, 40, 40), 1.5))
        p.drawEllipse(tc, rad, rad)

        # Inner alpha dot
        alpha_col = QColor(r, g, b, int(self._value * 255))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha_col)
        p.drawEllipse(tc, rad - 3, rad - 3)
        p.end()

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._update_from_pos(ev.position().x())

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        if self._dragging:
            self._update_from_pos(ev.position().x())

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        if self._dragging:
            self._dragging = False
            self.value_committed.emit(self._value)
            self.update()

    def _update_from_pos(self, x: float) -> None:
        tr = self._track_rect()
        frac = max(0.0, min(1.0, (x - tr.left()) / max(1, tr.width())))
        frac = round(frac, 2)
        if frac != self._value:
            self._value = frac
            self.update()
            self.value_changed.emit(self._value)


# ============================================================================
# Main ColorPanel — wheel + opacity only
# ============================================================================

class ColorPanel(QWidget):
    """Compact colour panel with HSV wheel and opacity slider.

    Emits legacy signals for backward compatibility:
    - fg_changed(Color)
    - bg_changed(Color)
    """

    fg_changed = Signal(object)
    bg_changed = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mgr = ColorManager.instance()
        self._updating = False
        self._build_ui()
        self._wire()
        self._sync_from_manager()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # FG/BG swatch row
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(6)
        self._fgbg = _FgBgSwatch()
        swatch_row.addWidget(self._fgbg)
        swatch_row.addStretch()

        _btn_style = (
            "QPushButton {"
            "  background: #363636; border: 1px solid #484848; border-radius: 5px;"
            "  color: #aaa; font-size: 11px;"
            "}"
            "QPushButton:hover { border: 1px solid #5a8abf; color: #ddd; }"
            "QPushButton:pressed { background: #404040; }"
        )
        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)
        self._swap_btn = QPushButton("⇄")
        self._swap_btn.setFixedSize(26, 22)
        self._swap_btn.setToolTip("Swap FG/BG  (X)")
        self._swap_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._swap_btn.setStyleSheet(_btn_style)
        self._reset_btn = QPushButton("◧")
        self._reset_btn.setFixedSize(26, 22)
        self._reset_btn.setToolTip("Reset to Black/White  (D)")
        self._reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_btn.setStyleSheet(_btn_style)
        btn_col.addWidget(self._swap_btn)
        btn_col.addWidget(self._reset_btn)
        btn_col.addStretch()
        swatch_row.addLayout(btn_col)
        layout.addLayout(swatch_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #3a3a3a; border: none;")
        layout.addWidget(sep)

        # Color wheel
        self._wheel = ColorWheel()
        self._wheel.setMinimumHeight(180)
        self._wheel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._wheel, 1)

        # Opacity row
        opacity_row = QHBoxLayout()
        opacity_row.setSpacing(6)
        lbl = QLabel("Opacity")
        lbl.setStyleSheet(
            "color: #999; font-size: 11px; font-weight: 600;"
            "font-family: 'Segoe UI', 'Inter', sans-serif;"
        )
        lbl.setFixedWidth(44)
        opacity_row.addWidget(lbl)

        self._opacity_slider = _OpacitySlider()
        opacity_row.addWidget(self._opacity_slider, 1)

        self._opacity_spin = QSpinBox()
        self._opacity_spin.setRange(0, 100)
        self._opacity_spin.setSuffix("%")
        self._opacity_spin.setFixedWidth(56)
        self._opacity_spin.setFixedHeight(20)
        self._opacity_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._opacity_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._opacity_spin.setStyleSheet(
            "QSpinBox {"
            "  background: #333; border: 1px solid #484848; border-radius: 4px;"
            "  color: #ddd; font-size: 11px; padding: 0 2px;"
            "  font-family: 'Cascadia Code', 'Consolas', monospace;"
            "}"
            "QSpinBox:focus { border: 1px solid #5a8abf; }"
        )
        opacity_row.addWidget(self._opacity_spin)
        layout.addLayout(opacity_row)

    def _wire(self) -> None:
        self._fgbg.swap_clicked.connect(self._on_swap)
        self._fgbg.reset_clicked.connect(self._on_reset)
        self._swap_btn.clicked.connect(self._on_swap)
        self._reset_btn.clicked.connect(self._on_reset)

        self._wheel.color_changed.connect(self._on_wheel_changed)
        self._wheel.color_committed.connect(self._on_wheel_committed)

        self._opacity_slider.value_changed.connect(self._on_opacity_slider)
        self._opacity_slider.value_committed.connect(self._on_opacity_committed)
        self._opacity_spin.valueChanged.connect(self._on_opacity_spin)

        self._mgr.foreground_changed.connect(self._on_mgr_fg)
        self._mgr.background_changed.connect(self._on_mgr_bg)

    def _sync_from_manager(self) -> None:
        self._updating = True
        fg = self._mgr.foreground
        bg = self._mgr.background
        self._fgbg.set_colors(fg, bg)
        self._wheel.set_color(fg)
        self._opacity_slider.set_value(fg.a)
        self._opacity_slider.set_color(fg)
        self._opacity_spin.setValue(int(fg.a * 100))
        self._updating = False

    # ---- Handlers -----------------------------------------------------------

    def _on_wheel_changed(self, c: Color) -> None:
        if self._updating:
            return
        self._updating = True
        alpha = self._opacity_slider.value()
        c = Color(c.r, c.g, c.b, alpha)
        self._opacity_slider.set_color(c)
        if self._fgbg.editing_fg:
            self._mgr.set_foreground_preview(c)
        else:
            self._mgr.set_background_preview(c)
        self._fgbg.set_colors(self._mgr.foreground, self._mgr.background)
        self._updating = False

    def _on_wheel_committed(self, c: Color) -> None:
        if self._fgbg.editing_fg:
            self._mgr.commit_foreground()
        else:
            self._mgr.commit_background()

    def _on_opacity_slider(self, v: float) -> None:
        if self._updating:
            return
        self._updating = True
        self._opacity_spin.setValue(int(v * 100))
        wc = self._wheel.color()
        c = Color(wc.r, wc.g, wc.b, v)
        if self._fgbg.editing_fg:
            self._mgr.set_foreground_preview(c)
        else:
            self._mgr.set_background_preview(c)
        self._fgbg.set_colors(self._mgr.foreground, self._mgr.background)
        self._updating = False

    def _on_opacity_committed(self, v: float) -> None:
        if self._fgbg.editing_fg:
            self._mgr.commit_foreground()
        else:
            self._mgr.commit_background()

    def _on_opacity_spin(self, v: int) -> None:
        if self._updating:
            return
        self._updating = True
        alpha = v / 100.0
        self._opacity_slider.set_value(alpha)
        wc = self._wheel.color()
        c = Color(wc.r, wc.g, wc.b, alpha)
        if self._fgbg.editing_fg:
            self._mgr.foreground = c
        else:
            self._mgr.background = c
        self._fgbg.set_colors(self._mgr.foreground, self._mgr.background)
        self._updating = False

    def _on_swap(self) -> None:
        self._mgr.swap()

    def _on_reset(self) -> None:
        self._mgr.reset()

    def _on_mgr_fg(self, c) -> None:
        if self._updating:
            return
        self._updating = True
        self._fgbg.set_colors(c, self._mgr.background)
        if self._fgbg.editing_fg:
            self._wheel.set_color(c)
            self._opacity_slider.set_value(c.a)
            self._opacity_slider.set_color(c)
            self._opacity_spin.setValue(int(c.a * 100))
        self._updating = False
        self.fg_changed.emit(c)

    def _on_mgr_bg(self, c) -> None:
        if self._updating:
            return
        self._updating = True
        self._fgbg.set_colors(self._mgr.foreground, c)
        if not self._fgbg.editing_fg:
            self._wheel.set_color(c)
            self._opacity_slider.set_value(c.a)
            self._opacity_slider.set_color(c)
            self._opacity_spin.setValue(int(c.a * 100))
        self._updating = False
        self.bg_changed.emit(c)

    # ---- Legacy compatibility -----------------------------------------------

    @property
    def foreground(self) -> Color:
        return self._mgr.foreground

    @property
    def background(self) -> Color:
        return self._mgr.background

    # ---- Legacy compatibility -----------------------------------------------

    @property
    def foreground(self) -> Color:
        return self._mgr.foreground

    @property
    def background(self) -> Color:
        return self._mgr.background
