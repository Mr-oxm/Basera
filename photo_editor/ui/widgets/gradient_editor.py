"""Interactive gradient editor with draggable stops.

Features:
 • Click on the gradient bar to add stops
 • Drag stops to reposition
 • Double-click a stop to change its colour
 • Right-click a stop to remove it
 • Gradient direction selector (linear / radial / conical / diamond)
 • Preset gallery
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
    QScrollArea,
    QPushButton,
)

from ...core.color import Color, GradientStop, LinearGradient, RadialGradient, SolidFill, ColorFill
from ...core.color_engine import (
    GRADIENT_PRESETS,
    ConicalGradient,
    DiamondGradient,
    hsv_to_rgb,
)


# ============================================================================
# Stop handle bar
# ============================================================================

_HANDLE_H = 14
_BAR_H = 24
_TOTAL_H = _BAR_H + _HANDLE_H + 6
_BAR_RADIUS = 6


class GradientBar(QWidget):
    """The interactive gradient strip with draggable stop handles (modern design)."""

    stops_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(_TOTAL_H)
        self.setMinimumWidth(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._stops: list[GradientStop] = [
            GradientStop(0.0, Color.black()),
            GradientStop(1.0, Color.white()),
        ]
        self._selected_idx: int = 0
        self._dragging_idx: int = -1
        self._drag_offset: float = 0.0

    @property
    def stops(self) -> list[GradientStop]:
        return list(self._stops)

    @stops.setter
    def stops(self, s: list[GradientStop]) -> None:
        self._stops = sorted(s, key=lambda st: st.position)
        self._selected_idx = min(self._selected_idx, len(self._stops) - 1)
        self.update()

    @property
    def selected_index(self) -> int:
        return self._selected_idx

    def set_selected_color(self, c: Color) -> None:
        if 0 <= self._selected_idx < len(self._stops):
            old = self._stops[self._selected_idx]
            self._stops[self._selected_idx] = GradientStop(old.position, c)
            self.update()
            self.stops_changed.emit()

    # ---- Painting -----------------------------------------------------------

    def paintEvent(self, ev: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        bar_rect = QRectF(4, 2, w - 8, _BAR_H)

        # Checkerboard (clipped to rounded rect)
        clip_path = QPainterPath()
        clip_path.addRoundedRect(bar_rect, _BAR_RADIUS, _BAR_RADIUS)
        p.setClipPath(clip_path)
        cs = 5
        for y in range(int(bar_rect.top()), int(bar_rect.bottom()) + 1, cs):
            for x in range(int(bar_rect.left()), int(bar_rect.right()) + 1, cs):
                ix = (x - int(bar_rect.left())) // cs
                iy = (y - int(bar_rect.top())) // cs
                c = QColor(68, 68, 68) if (ix + iy) % 2 == 0 else QColor(88, 88, 88)
                p.fillRect(x, y, cs, cs, c)

        # Gradient fill
        grad = QLinearGradient(bar_rect.left(), 0, bar_rect.right(), 0)
        for stop in self._stops:
            r, g, b, a = stop.color.to_rgb8()
            grad.setColorAt(stop.position, QColor(r, g, b, a))
        p.setBrush(grad)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(bar_rect, _BAR_RADIUS, _BAR_RADIUS)
        p.setClipping(False)

        # Bar border
        p.setPen(QPen(QColor(50, 50, 50), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(bar_rect.adjusted(0.5, 0.5, -0.5, -0.5), _BAR_RADIUS, _BAR_RADIUS)

        # Stop handles — modern circular pill style
        handle_y = _BAR_H + 5
        for i, stop in enumerate(self._stops):
            x = bar_rect.left() + stop.position * bar_rect.width()
            is_sel = (i == self._selected_idx)
            hr = 6 if is_sel else 5

            # Connector line from bar to handle
            p.setPen(QPen(QColor(80, 80, 80), 1.0))
            p.drawLine(QPointF(x, _BAR_H + 2), QPointF(x, handle_y))

            # Shadow
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 40))
            p.drawEllipse(QPointF(x, handle_y + hr + 1), hr + 1, hr + 1)

            # Handle body
            r, g, b, a = stop.color.to_rgb8()
            p.setBrush(QColor(r, g, b, a))
            border_col = QColor(255, 255, 255) if is_sel else QColor(70, 70, 70)
            border_w = 2.0 if is_sel else 1.2
            p.setPen(QPen(border_col, border_w))
            p.drawEllipse(QPointF(x, handle_y + hr), hr, hr)

        p.end()

    # ---- Mouse interaction --------------------------------------------------

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        bar_rect = QRectF(4, 2, self.width() - 8, _BAR_H)
        if ev.button() == Qt.MouseButton.LeftButton:
            idx = self._hit_handle(ev.position())
            if idx >= 0:
                self._selected_idx = idx
                self._dragging_idx = idx
                self._drag_offset = ev.position().x() - (bar_rect.left() + self._stops[idx].position * bar_rect.width())
                self.update()
            else:
                # Add new stop
                pos = max(0.0, min(1.0, (ev.position().x() - bar_rect.left()) / max(1, bar_rect.width())))
                c = self._sample_at(pos)
                self._stops.append(GradientStop(pos, c))
                self._stops.sort(key=lambda s: s.position)
                self._selected_idx = next(
                    i for i, s in enumerate(self._stops) if s.position == pos
                )
                self._dragging_idx = self._selected_idx
                self.update()
                self.stops_changed.emit()

        elif ev.button() == Qt.MouseButton.RightButton:
            idx = self._hit_handle(ev.position())
            if idx >= 0 and len(self._stops) > 2:
                self._stops.pop(idx)
                self._selected_idx = max(0, min(self._selected_idx, len(self._stops) - 1))
                self.update()
                self.stops_changed.emit()

    def mouseDoubleClickEvent(self, ev: QMouseEvent) -> None:
        idx = self._hit_handle(ev.position())
        if idx >= 0:
            stop = self._stops[idx]
            r, g, b, a = stop.color.to_rgb8()
            qc = QColorDialog.getColor(QColor(r, g, b, a), self, "Stop Color",
                                        QColorDialog.ColorDialogOption.ShowAlphaChannel)
            if qc.isValid():
                new_c = Color.from_rgb8(qc.red(), qc.green(), qc.blue(), qc.alpha())
                self._stops[idx] = GradientStop(stop.position, new_c)
                self.update()
                self.stops_changed.emit()

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        if self._dragging_idx >= 0:
            bar_rect = QRectF(4, 2, self.width() - 8, _BAR_H)
            bw = max(1, bar_rect.width())
            pos = max(0.0, min(1.0, (ev.position().x() - bar_rect.left()) / bw))
            old = self._stops[self._dragging_idx]
            self._stops[self._dragging_idx] = GradientStop(pos, old.color)
            self._stops.sort(key=lambda s: s.position)
            self._dragging_idx = next(
                i for i, s in enumerate(self._stops) if s.color == old.color and abs(s.position - pos) < 0.001
            )
            self._selected_idx = self._dragging_idx
            self.update()
            self.stops_changed.emit()

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        self._dragging_idx = -1

    def _hit_handle(self, pos: QPointF) -> int:
        """Return index of the stop handle under *pos*, or -1."""
        bar_rect = QRectF(4, 2, self.width() - 8, _BAR_H)
        handle_y = _BAR_H + 5
        for i, stop in enumerate(self._stops):
            x = bar_rect.left() + stop.position * bar_rect.width()
            hr = 6 if i == self._selected_idx else 5
            cy = handle_y + hr
            # Circle hit
            dx = pos.x() - x
            dy = pos.y() - cy
            if dx * dx + dy * dy <= (hr + 4) ** 2:
                return i
            # Also hit on the bar itself near handle x
            if abs(pos.x() - x) < 8 and 0 <= pos.y() <= _BAR_H + 2:
                return i
        return -1

    def _sample_at(self, t: float) -> Color:
        """Linearly interpolate stops at position t."""
        if not self._stops:
            return Color.black()
        if t <= self._stops[0].position:
            return self._stops[0].color
        if t >= self._stops[-1].position:
            return self._stops[-1].color
        for i in range(len(self._stops) - 1):
            s0, s1 = self._stops[i], self._stops[i + 1]
            if s0.position <= t <= s1.position:
                span = s1.position - s0.position
                local = (t - s0.position) / span if span > 0 else 0
                return s0.color.lerp(s1.color, local)
        return self._stops[-1].color


# ============================================================================
# Preset strip
# ============================================================================

class _PresetStrip(QWidget):
    preset_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(4)
        for name, stops in GRADIENT_PRESETS.items():
            btn = QPushButton()
            btn.setFixedSize(36, 20)
            if len(stops) >= 2:
                r0, g0, b0, _ = stops[0].color.to_rgb8()
                r1, g1, b1, _ = stops[-1].color.to_rgb8()
                btn.setStyleSheet(
                    f"QPushButton {{"
                    f"  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                    f"  stop:0 rgb({r0},{g0},{b0}), stop:1 rgb({r1},{g1},{b1}));"
                    f"  border: 1px solid #444; border-radius: 4px;"
                    f"}}"
                    f"QPushButton:hover {{ border: 1px solid #7aacdf; }}"
                )
            btn.setToolTip(name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, n=name: self.preset_selected.emit(n))
            layout.addWidget(btn)
        layout.addStretch()


# ============================================================================
# Full Gradient Editor widget
# ============================================================================

class GradientEditor(QWidget):
    """Full gradient editor with bar, presets, and type selector.

    Signals
    -------
    gradient_changed(ColorFill)
    """

    gradient_changed = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Type selector row
        type_row = QHBoxLayout()
        type_row.setSpacing(6)
        lbl = QLabel("Type")
        lbl.setStyleSheet(
            "color: #888; font-size: 11px; font-weight: 600;"
            "font-family: 'Segoe UI', 'Inter', sans-serif;"
        )
        type_row.addWidget(lbl)
        self._type_combo = QComboBox()
        self._type_combo.addItems(["Linear", "Radial", "Conical", "Diamond"])
        self._type_combo.setFixedHeight(24)
        self._type_combo.setFixedWidth(90)
        self._type_combo.setStyleSheet(
            "QComboBox {"
            "  background: #363636; border: 1px solid #484848; border-radius: 5px;"
            "  color: #ccc; font-size: 11px; padding: 2px 8px;"
            "}"
            "QComboBox:hover { border: 1px solid #5a8abf; }"
            "QComboBox::drop-down { border: none; width: 16px; }"
            "QComboBox::down-arrow { image: none; border: none; }"
            "QComboBox QAbstractItemView {"
            "  background: #333; border: 1px solid #484848; border-radius: 4px;"
            "  color: #ccc; selection-background-color: #4a6fa5;"
            "}"
        )
        self._type_combo.currentIndexChanged.connect(self._emit_gradient)
        type_row.addWidget(self._type_combo)
        type_row.addStretch()

        # Reverse button
        rev_btn = QPushButton("⟳")
        rev_btn.setFixedSize(26, 24)
        rev_btn.setToolTip("Reverse gradient")
        rev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rev_btn.setStyleSheet(
            "QPushButton {"
            "  background: #363636; border: 1px solid #484848; border-radius: 5px;"
            "  color: #aaa; font-size: 13px;"
            "}"
            "QPushButton:hover { border: 1px solid #5a8abf; color: #ddd; }"
            "QPushButton:pressed { background: #404040; }"
        )
        rev_btn.clicked.connect(self._reverse)
        type_row.addWidget(rev_btn)
        layout.addLayout(type_row)

        # Gradient bar
        self._bar = GradientBar()
        self._bar.stops_changed.connect(self._emit_gradient)
        layout.addWidget(self._bar)

        # Presets
        self._presets = _PresetStrip()
        self._presets.preset_selected.connect(self._on_preset)
        layout.addWidget(self._presets)

    def gradient(self) -> ColorFill:
        """Build the current ColorFill from stops + type."""
        stops = tuple(self._bar.stops)
        idx = self._type_combo.currentIndex()
        if idx == 0:
            return LinearGradient(stops=stops)
        elif idx == 1:
            return RadialGradient(stops=stops)
        elif idx == 2:
            return ConicalGradient(stops=stops)
        elif idx == 3:
            return DiamondGradient(stops=stops)
        return LinearGradient(stops=stops)

    def set_stops(self, stops: list[GradientStop]) -> None:
        self._bar.stops = stops
        self._bar.update()

    def _emit_gradient(self) -> None:
        self.gradient_changed.emit(self.gradient())

    def _reverse(self) -> None:
        stops = self._bar.stops
        reversed_stops = [
            GradientStop(1.0 - s.position, s.color) for s in reversed(stops)
        ]
        self._bar.stops = reversed_stops
        self._emit_gradient()

    def _on_preset(self, name: str) -> None:
        preset = GRADIENT_PRESETS.get(name)
        if preset:
            self._bar.stops = list(preset)
            self._emit_gradient()
