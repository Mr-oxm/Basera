"""Color model slider rows — RGB, HSV, HSL, CMYK with hex input.

Each model shows labelled sliders with live numeric fields.  The sliders
themselves render a gradient preview of what changing that channel would
look like (Affinity / Photoshop style).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize, QPointF, QRectF
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QMouseEvent,
    QPen,
)
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSlider,
    QVBoxLayout,
    QWidget,
    QSpinBox,
    QDoubleSpinBox,
    QStackedWidget,
    QSizePolicy,
)

from ...core.color import Color
from ...core.color_engine import (
    rgb_to_hsv, hsv_to_rgb,
    rgb_to_hsl, hsl_to_rgb,
    rgb_to_cmyk, cmyk_to_rgb,
)


# ============================================================================
# Gradient-preview slider
# ============================================================================

class _GradientSlider(QWidget):
    """A slider that draws a gradient background showing the effect of the channel.

    Modern design: rounded pill track, circular thumb with border + shadow.
    """

    value_changed = Signal(float)
    value_committed = Signal(float)

    _TRACK_H = 14        # px height of the gradient track
    _THUMB_R = 7          # thumb circle radius
    _MARGIN_X = 8         # horizontal padding so thumb isn't clipped

    def __init__(self, min_val: float = 0, max_val: float = 255,
                 decimals: int = 0, parent=None) -> None:
        super().__init__(parent)
        self._min = min_val
        self._max = max_val
        self._value = min_val
        self._decimals = decimals
        self._colors: list[tuple[float, QColor]] = []
        self.setFixedHeight(self._TRACK_H + 6)
        self.setMinimumWidth(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._dragging = False
        self._hovered = False
        self.setMouseTracking(True)

    def set_gradient(self, colors: list[tuple[float, QColor]]) -> None:
        self._colors = colors
        self.update()

    def set_value(self, v: float) -> None:
        v = max(self._min, min(self._max, v))
        if v != self._value:
            self._value = v
            self.update()

    def value(self) -> float:
        return self._value

    # ---- Geometry helpers ---------------------------------------------------

    def _track_rect(self) -> QRectF:
        h = self._TRACK_H
        y = (self.height() - h) / 2.0
        return QRectF(self._MARGIN_X, y, self.width() - 2 * self._MARGIN_X, h)

    def _frac(self) -> float:
        return (self._value - self._min) / (self._max - self._min) if self._max > self._min else 0.0

    def _thumb_center(self) -> QPointF:
        tr = self._track_rect()
        return QPointF(tr.left() + self._frac() * tr.width(), tr.center().y())

    # ---- Rendering ----------------------------------------------------------

    def paintEvent(self, ev: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        tr = self._track_rect()
        radius = tr.height() / 2.0

        # Checkerboard (clipped to rounded rect)
        path = QPainterPath()
        path.addRoundedRect(tr, radius, radius)
        p.setClipPath(path)
        cs = 5
        for y in range(int(tr.top()), int(tr.bottom()) + 1, cs):
            for x in range(int(tr.left()), int(tr.right()) + 1, cs):
                ix = (x - int(tr.left())) // cs
                iy = (y - int(tr.top())) // cs
                c = QColor(68, 68, 68) if (ix + iy) % 2 == 0 else QColor(88, 88, 88)
                p.fillRect(x, y, cs, cs, c)

        # Gradient fill
        if self._colors:
            grad = QLinearGradient(tr.left(), 0, tr.right(), 0)
            for pos, col in self._colors:
                grad.setColorAt(pos, col)
            p.setBrush(grad)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(tr, radius, radius)

        p.setClipping(False)

        # Track border — subtle
        p.setPen(QPen(QColor(55, 55, 55), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(tr.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        # Thumb
        tc = self._thumb_center()
        r = self._THUMB_R
        if self._dragging:
            r += 1  # slightly bigger when active

        # Shadow
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawEllipse(tc + QPointF(0, 1), r + 1, r + 1)

        # Thumb body (white)
        p.setBrush(QColor(255, 255, 255))
        p.setPen(QPen(QColor(40, 40, 40), 1.5))
        p.drawEllipse(tc, r, r)

        # Inner color dot
        if self._colors:
            # Sample current color
            frac = self._frac()
            sampled = self._sample_gradient(frac)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(sampled)
            p.drawEllipse(tc, r - 3, r - 3)

        p.end()

    def _sample_gradient(self, t: float) -> QColor:
        """Sample the gradient at position t (0-1)."""
        if not self._colors:
            return QColor(128, 128, 128)
        if t <= self._colors[0][0]:
            return self._colors[0][1]
        if t >= self._colors[-1][0]:
            return self._colors[-1][1]
        for i in range(len(self._colors) - 1):
            p0, c0 = self._colors[i]
            p1, c1 = self._colors[i + 1]
            if p0 <= t <= p1:
                f = (t - p0) / (p1 - p0) if (p1 - p0) > 0 else 0
                r = int(c0.red() + f * (c1.red() - c0.red()))
                g = int(c0.green() + f * (c1.green() - c0.green()))
                b = int(c0.blue() + f * (c1.blue() - c0.blue()))
                a = int(c0.alpha() + f * (c1.alpha() - c0.alpha()))
                return QColor(r, g, b, a)
        return self._colors[-1][1]

    # ---- Interaction --------------------------------------------------------

    def enterEvent(self, ev) -> None:
        self._hovered = True
        self.update()

    def leaveEvent(self, ev) -> None:
        self._hovered = False
        self.update()

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

    def _update_from_pos(self, x: float) -> None:
        tr = self._track_rect()
        frac = max(0.0, min(1.0, (x - tr.left()) / max(1, tr.width())))
        v = self._min + frac * (self._max - self._min)
        if self._decimals == 0:
            v = round(v)
        else:
            v = round(v, self._decimals)
        if v != self._value:
            self._value = v
            self.update()
            self.value_changed.emit(self._value)


# ============================================================================
# Single channel row: label + gradient slider + spinbox
# ============================================================================

class _ChannelRow(QWidget):
    value_changed = Signal(float)
    value_committed = Signal(float)

    # Per-channel accent colors for labels
    _LABEL_COLORS = {
        'R': '#e06060', 'G': '#50b850', 'B': '#5090e0',
        'H': '#d8a040', 'S': '#c070c0', 'V': '#a0a0a0', 'L': '#a0a0a0',
        'C': '#40c8c8', 'M': '#e060a0', 'Y': '#d8d040', 'K': '#909090',
        'A': '#b0b0b0',
    }

    def __init__(self, label: str, min_val: float, max_val: float,
                 decimals: int = 0, parent=None) -> None:
        super().__init__(parent)
        from ..styles import format_qss, render_qss
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(6)

        accent = self._LABEL_COLORS.get(label, '#aaa')
        lbl = QLabel(label)
        lbl.setFixedWidth(16)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            f"font-weight: 600; font-size: 11px; font-family: 'Segoe UI', 'Inter', sans-serif; color: {accent};"
        )
        layout.addWidget(lbl)

        self._slider = _GradientSlider(min_val, max_val, decimals)
        layout.addWidget(self._slider, 1)

        if decimals == 0:
            self._spin = QSpinBox()
            self._spin.setRange(int(min_val), int(max_val))
            self._spin.setFixedWidth(48)
        else:
            self._spin = QDoubleSpinBox()
            self._spin.setRange(min_val, max_val)
            self._spin.setDecimals(decimals)
            self._spin.setFixedWidth(56)
        self._spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._spin.setFixedHeight(20)
        self._spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._spin.setStyleSheet(format_qss("properties_spin.qss", max_w=56 if decimals else 48, accent="#5a8abf"))
        layout.addWidget(self._spin)

        self._slider.value_changed.connect(self._on_slider)
        self._slider.value_committed.connect(self._on_committed)
        self._spin.valueChanged.connect(self._on_spin)

    def set_gradient(self, colors: list[tuple[float, QColor]]) -> None:
        self._slider.set_gradient(colors)

    def set_value(self, v: float) -> None:
        self._slider.blockSignals(True)
        self._spin.blockSignals(True)
        self._slider.set_value(v)
        self._spin.setValue(int(v) if isinstance(self._spin, QSpinBox) else v)
        self._slider.blockSignals(False)
        self._spin.blockSignals(False)

    def value(self) -> float:
        return self._slider.value()

    def _on_slider(self, v: float) -> None:
        self._spin.blockSignals(True)
        self._spin.setValue(int(v) if isinstance(self._spin, QSpinBox) else v)
        self._spin.blockSignals(False)
        self.value_changed.emit(v)

    def _on_committed(self, v: float) -> None:
        self.value_committed.emit(v)

    def _on_spin(self, v) -> None:
        self._slider.blockSignals(True)
        self._slider.set_value(float(v))
        self._slider.blockSignals(False)
        self.value_changed.emit(float(v))


# ============================================================================
# Full model pages
# ============================================================================

class _RGBPage(QWidget):
    color_changed = Signal(object)
    color_committed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._r = _ChannelRow("R", 0, 255)
        self._g = _ChannelRow("G", 0, 255)
        self._b = _ChannelRow("B", 0, 255)
        self._a = _ChannelRow("A", 0, 255)
        for ch in (self._r, self._g, self._b, self._a):
            layout.addWidget(ch)
            ch.value_changed.connect(self._emit)
            ch.value_committed.connect(self._emit_committed)
        self._updating = False

    def set_color(self, c: Color) -> None:
        self._updating = True
        self._r.set_value(c.r * 255)
        self._g.set_value(c.g * 255)
        self._b.set_value(c.b * 255)
        self._a.set_value(c.a * 255)
        self._update_gradients(c)
        self._updating = False

    def _update_gradients(self, c: Color) -> None:
        r8, g8, b8 = int(c.r * 255), int(c.g * 255), int(c.b * 255)
        self._r.set_gradient([(0, QColor(0, g8, b8)), (1, QColor(255, g8, b8))])
        self._g.set_gradient([(0, QColor(r8, 0, b8)), (1, QColor(r8, 255, b8))])
        self._b.set_gradient([(0, QColor(r8, g8, 0)), (1, QColor(r8, g8, 255))])
        self._a.set_gradient([(0, QColor(r8, g8, b8, 0)), (1, QColor(r8, g8, b8, 255))])

    def _emit(self, _=None) -> None:
        if self._updating:
            return
        c = Color(self._r.value() / 255, self._g.value() / 255,
                  self._b.value() / 255, self._a.value() / 255)
        self._update_gradients(c)
        self.color_changed.emit(c)

    def _emit_committed(self, _=None) -> None:
        if self._updating:
            return
        c = Color(self._r.value() / 255, self._g.value() / 255,
                  self._b.value() / 255, self._a.value() / 255)
        self.color_committed.emit(c)


class _HSVPage(QWidget):
    color_changed = Signal(object)
    color_committed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._h = _ChannelRow("H", 0, 360)
        self._s = _ChannelRow("S", 0, 100)
        self._v = _ChannelRow("V", 0, 100)
        self._a = _ChannelRow("A", 0, 255)
        for ch in (self._h, self._s, self._v, self._a):
            layout.addWidget(ch)
            ch.value_changed.connect(self._emit)
            ch.value_committed.connect(self._emit_committed)
        self._updating = False

    def set_color(self, c: Color) -> None:
        self._updating = True
        h, s, v = rgb_to_hsv(c.r, c.g, c.b)
        self._h.set_value(h)
        self._s.set_value(s * 100)
        self._v.set_value(v * 100)
        self._a.set_value(c.a * 255)
        self._update_gradients(h, s, v, c.a)
        self._updating = False

    def _update_gradients(self, h, s, v, a) -> None:
        # Hue bar: rainbow
        hue_colors = []
        for i in range(7):
            hd = i * 60
            r, g, b = hsv_to_rgb(float(hd), s, v)
            hue_colors.append((i / 6.0, QColor.fromRgbF(r, g, b)))
        self._h.set_gradient(hue_colors)
        # Sat bar
        r0, g0, b0 = hsv_to_rgb(h, 0, v)
        r1, g1, b1 = hsv_to_rgb(h, 1, v)
        self._s.set_gradient([(0, QColor.fromRgbF(r0, g0, b0)), (1, QColor.fromRgbF(r1, g1, b1))])
        # Val bar
        r0, g0, b0 = hsv_to_rgb(h, s, 0)
        r1, g1, b1 = hsv_to_rgb(h, s, 1)
        self._v.set_gradient([(0, QColor.fromRgbF(r0, g0, b0)), (1, QColor.fromRgbF(r1, g1, b1))])
        # Alpha
        rc, gc, bc = hsv_to_rgb(h, s, v)
        self._a.set_gradient([(0, QColor.fromRgbF(rc, gc, bc, 0)), (1, QColor.fromRgbF(rc, gc, bc, 1))])

    def _emit(self, _=None) -> None:
        if self._updating:
            return
        h = self._h.value()
        s = self._s.value() / 100
        v = self._v.value() / 100
        a = self._a.value() / 255
        r, g, b = hsv_to_rgb(h, s, v)
        self.color_changed.emit(Color(r, g, b, a))

    def _emit_committed(self, _=None) -> None:
        if self._updating:
            return
        h = self._h.value()
        s = self._s.value() / 100
        v = self._v.value() / 100
        a = self._a.value() / 255
        r, g, b = hsv_to_rgb(h, s, v)
        self.color_committed.emit(Color(r, g, b, a))


class _HSLPage(QWidget):
    color_changed = Signal(object)
    color_committed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._h = _ChannelRow("H", 0, 360)
        self._s = _ChannelRow("S", 0, 100)
        self._l = _ChannelRow("L", 0, 100)
        self._a = _ChannelRow("A", 0, 255)
        for ch in (self._h, self._s, self._l, self._a):
            layout.addWidget(ch)
            ch.value_changed.connect(self._emit)
            ch.value_committed.connect(self._emit_committed)
        self._updating = False

    def set_color(self, c: Color) -> None:
        self._updating = True
        h, s, l = rgb_to_hsl(c.r, c.g, c.b)
        self._h.set_value(h)
        self._s.set_value(s * 100)
        self._l.set_value(l * 100)
        self._a.set_value(c.a * 255)
        self._updating = False

    def _emit(self, _=None) -> None:
        if self._updating:
            return
        h = self._h.value()
        s = self._s.value() / 100
        l = self._l.value() / 100
        a = self._a.value() / 255
        r, g, b = hsl_to_rgb(h, s, l)
        self.color_changed.emit(Color(r, g, b, a))

    def _emit_committed(self, _=None) -> None:
        if self._updating:
            return
        h = self._h.value()
        s = self._s.value() / 100
        l = self._l.value() / 100
        a = self._a.value() / 255
        r, g, b = hsl_to_rgb(h, s, l)
        self.color_committed.emit(Color(r, g, b, a))


class _CMYKPage(QWidget):
    color_changed = Signal(object)
    color_committed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._c = _ChannelRow("C", 0, 100)
        self._m = _ChannelRow("M", 0, 100)
        self._y = _ChannelRow("Y", 0, 100)
        self._k = _ChannelRow("K", 0, 100)
        for ch in (self._c, self._m, self._y, self._k):
            layout.addWidget(ch)
            ch.value_changed.connect(self._emit)
            ch.value_committed.connect(self._emit_committed)
        self._updating = False

    def set_color(self, c: Color) -> None:
        self._updating = True
        cm, mm, ym, km = rgb_to_cmyk(c.r, c.g, c.b)
        self._c.set_value(cm * 100)
        self._m.set_value(mm * 100)
        self._y.set_value(ym * 100)
        self._k.set_value(km * 100)
        self._updating = False

    def _emit(self, _=None) -> None:
        if self._updating:
            return
        r, g, b = cmyk_to_rgb(
            self._c.value() / 100, self._m.value() / 100,
            self._y.value() / 100, self._k.value() / 100,
        )
        self.color_changed.emit(Color(r, g, b))

    def _emit_committed(self, _=None) -> None:
        if self._updating:
            return
        r, g, b = cmyk_to_rgb(
            self._c.value() / 100, self._m.value() / 100,
            self._y.value() / 100, self._k.value() / 100,
        )
        self.color_committed.emit(Color(r, g, b))


# ============================================================================
# Public composite widget
# ============================================================================

class ColorSliders(QWidget):
    """Multi-model colour slider panel with RGB / HSV / HSL / CMYK tabs + hex input."""

    color_changed = Signal(object)  # Color (during drag)
    color_committed = Signal(object)  # Color (on mouse release)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        from ..styles import format_qss, render_qss
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Model selector row
        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        self._model_combo = QComboBox()
        self._model_combo.addItems(["RGB", "HSV", "HSL", "CMYK"])
        self._model_combo.setFixedHeight(24)
        self._model_combo.setFixedWidth(72)
        self._model_combo.setStyleSheet(format_qss("properties_combo.qss", widget="QComboBox", accent="#5a8abf"))
        self._model_combo.currentIndexChanged.connect(self._on_model_changed)
        top_row.addWidget(self._model_combo)
        top_row.addStretch()

        # Hex input
        hex_lbl = QLabel("#")
        hex_lbl.setStyleSheet("font-weight: 600; color: #777; font-size: 12px; font-family: 'Cascadia Code', 'Consolas', monospace;")
        top_row.addWidget(hex_lbl)
        self._hex_edit = QLineEdit()
        self._hex_edit.setFixedWidth(72)
        self._hex_edit.setFixedHeight(24)
        self._hex_edit.setMaxLength(8)
        self._hex_edit.setStyleSheet(
            render_qss(
                "control_line_edit.qss",
                selector="QLineEdit",
                bg="#333",
                border="#484848",
                radius=5,
                fg="#ddd",
                font_family="'Cascadia Code', 'Consolas', monospace'",
                font_size=11,
                padding="2px 6px",
                focus_border="#5a8abf",
                focus_bg="#333",
            )
        )
        self._hex_edit.returnPressed.connect(self._on_hex_enter)
        top_row.addWidget(self._hex_edit)
        layout.addLayout(top_row)

        # Stacked pages
        self._stack = QStackedWidget()
        self._rgb_page = _RGBPage()
        self._hsv_page = _HSVPage()
        self._hsl_page = _HSLPage()
        self._cmyk_page = _CMYKPage()
        self._stack.addWidget(self._rgb_page)
        self._stack.addWidget(self._hsv_page)
        self._stack.addWidget(self._hsl_page)
        self._stack.addWidget(self._cmyk_page)
        layout.addWidget(self._stack)

        for page in (self._rgb_page, self._hsv_page, self._hsl_page, self._cmyk_page):
            page.color_changed.connect(self._on_page_color)
            page.color_committed.connect(self._on_page_committed)

        self._color = Color.black()
        self._updating = False

    def set_color(self, c: Color) -> None:
        self._updating = True
        self._color = c
        self._rgb_page.set_color(c)
        self._hsv_page.set_color(c)
        self._hsl_page.set_color(c)
        self._cmyk_page.set_color(c)
        self._hex_edit.setText(c.to_hex().lstrip("#"))
        self._updating = False

    def _on_model_changed(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)

    def _on_page_color(self, c: Color) -> None:
        if self._updating:
            return
        self._color = c
        self._updating = True
        # Sync all pages
        idx = self._stack.currentIndex()
        if idx != 0:
            self._rgb_page.set_color(c)
        if idx != 1:
            self._hsv_page.set_color(c)
        if idx != 2:
            self._hsl_page.set_color(c)
        if idx != 3:
            self._cmyk_page.set_color(c)
        self._hex_edit.setText(c.to_hex().lstrip("#"))
        self._updating = False
        self.color_changed.emit(c)

    def _on_page_committed(self, c: Color) -> None:
        if self._updating:
            return
        self.color_committed.emit(c)

    def _on_hex_enter(self) -> None:
        txt = self._hex_edit.text().strip().lstrip("#")
        try:
            c = Color.from_hex("#" + txt)
            self._color = c
            self._updating = True
            self._rgb_page.set_color(c)
            self._hsv_page.set_color(c)
            self._hsl_page.set_color(c)
            self._cmyk_page.set_color(c)
            self._updating = False
            self.color_changed.emit(c)
        except ValueError:
            pass
