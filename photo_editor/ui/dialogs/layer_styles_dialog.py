"""Photoshop-style Layer Styles dialog.

Features
--------
* Left sidebar: checkable list of style instances, **+** button to add
  duplicates, **−** button to remove selected.
* Right side: stacked settings panels with colour pickers, sliders,
  an interactive **angle dial** widget, and a **blend mode** combo.
"""

from __future__ import annotations

import math
import copy
from typing import Any
from uuid import uuid4

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QMouseEvent
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QSlider, QSpinBox,
    QStackedWidget, QVBoxLayout, QWidget,
)

from ...core.color import Color
from ...core.enums import BlendMode
from ..widgets.color_dropdown import ColorDropdown
from ...styles.bevel_emboss import BevelEmboss
from ...styles.color_overlay import ColorOverlay
from ...styles.drop_shadow import DropShadow
from ...styles.gradient_overlay import GradientOverlay
from ...styles.inner_glow import InnerGlow
from ...styles.inner_shadow import InnerShadow
from ...styles.outer_glow import OuterGlow
from ...styles.pattern_overlay import PatternOverlay
from ...styles.satin import Satin
from ...styles.stroke import Stroke
from ...styles.style_base import LayerStyle

# ── Ordered list of all style types ──────────────────────────────────────

_STYLE_TYPES: list[tuple[str, type[LayerStyle]]] = [
    ("Drop Shadow", DropShadow),
    ("Inner Shadow", InnerShadow),
    ("Outer Glow", OuterGlow),
    ("Inner Glow", InnerGlow),
    ("Bevel and Emboss", BevelEmboss),
    ("Satin", Satin),
    ("Color Overlay", ColorOverlay),
    ("Gradient Overlay", GradientOverlay),
    ("Pattern Overlay", PatternOverlay),
    ("Stroke", Stroke),
]

_STYLE_CLASS_MAP: dict[str, type[LayerStyle]] = {n: c for n, c in _STYLE_TYPES}

# ═══════════════════════════════════════════════════════════════════════════
#  Helper widgets
# ═══════════════════════════════════════════════════════════════════════════

_LBL_STYLE = "font-size: 9pt; color: #ccc;"
_HEADER_STYLE = "font-size: 10pt; font-weight: bold; color: #ddd; margin-bottom: 4px;"


# ── Color swatch button (wraps ColorDropdown) ───────────────────────────

class _ColorButton(QWidget):
    """Wrapper around ``ColorDropdown`` that speaks [r,g,b] float lists."""

    color_changed = Signal(list)  # [r, g, b] floats 0-1

    def __init__(self, color: list[float], parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._dropdown = ColorDropdown(show_gradient=False, show_wheel=True)
        lay.addWidget(self._dropdown)
        self._color = list(color)
        self._dropdown.set_color(Color(color[0], color[1], color[2]))
        self._dropdown.color_committed.connect(self._on_committed)
        self._dropdown.color_changed.connect(self._on_live)

    @property
    def color(self) -> list[float]:
        return list(self._color)

    def set_color(self, color: list[float]) -> None:
        self._color = list(color)
        self._dropdown.set_color(Color(color[0], color[1], color[2]))

    def _on_committed(self, c: Color) -> None:
        self._color = [c.r, c.g, c.b]
        self.color_changed.emit(self._color)

    def _on_live(self, c: Color) -> None:
        self._color = [c.r, c.g, c.b]
        self.color_changed.emit(self._color)


# ── Angle dial widget ───────────────────────────────────────────────────

class AngleDial(QWidget):
    """Interactive circular angle picker (Photoshop-style).

    Draws a circle with a line from centre to the edge indicating the
    current angle.  Click / drag anywhere on the widget to change it.
    """

    angle_changed = Signal(int)

    _SIZE = 64

    def __init__(self, angle: int = 120, parent=None) -> None:
        super().__init__(parent)
        self._angle = angle % 360
        self.setFixedSize(self._SIZE, self._SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @property
    def angle(self) -> int:
        return self._angle

    def set_angle(self, angle: int) -> None:
        angle = angle % 360
        if angle != self._angle:
            self._angle = angle
            self.update()
            self.angle_changed.emit(self._angle)

    # ── Painting ─────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._SIZE
        cx, cy = s / 2, s / 2
        r = s / 2 - 4

        # Outer circle
        p.setPen(QPen(QColor(80, 80, 80), 1.2))
        p.setBrush(QBrush(QColor(40, 40, 40)))
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # Tick marks every 45°
        p.setPen(QPen(QColor(70, 70, 70), 1))
        for deg in range(0, 360, 45):
            rad = math.radians(deg)
            x1 = cx + (r - 3) * math.cos(rad)
            y1 = cy - (r - 3) * math.sin(rad)
            x2 = cx + r * math.cos(rad)
            y2 = cy - r * math.sin(rad)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # Centre dot
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(180, 180, 180))
        p.drawEllipse(QPointF(cx, cy), 2.5, 2.5)

        # Angle line
        rad = math.radians(self._angle)
        ex = cx + (r - 2) * math.cos(rad)
        ey = cy - (r - 2) * math.sin(rad)
        p.setPen(QPen(QColor(0, 140, 255), 2))
        p.drawLine(QPointF(cx, cy), QPointF(ex, ey))

        # End dot
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 160, 255))
        p.drawEllipse(QPointF(ex, ey), 3.5, 3.5)

        p.end()

    # ── Mouse interaction ────────────────────────────────────────────────

    def _angle_from_pos(self, pos) -> int:
        cx, cy = self._SIZE / 2, self._SIZE / 2
        dx = pos.x() - cx
        dy = -(pos.y() - cy)  # Qt y is inverted
        a = math.degrees(math.atan2(dy, dx)) % 360
        return int(round(a))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_angle(self._angle_from_pos(event.position()))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.set_angle(self._angle_from_pos(event.position()))


# ── Blend mode combo helper ─────────────────────────────────────────────

def _blend_mode_combo(current: BlendMode = BlendMode.NORMAL) -> QComboBox:
    combo = QComboBox()
    for mode in BlendMode:
        combo.addItem(mode.name.replace("_", " ").title(), mode)
    idx = combo.findData(current)
    if idx >= 0:
        combo.setCurrentIndex(idx)
    return combo


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: #555;")
    return line


# ═══════════════════════════════════════════════════════════════════════════
#  Per-style settings panel (base)
# ═══════════════════════════════════════════════════════════════════════════

class _BaseStylePanel(QWidget):
    """Base class for a single-style parameter panel."""

    changed = Signal()

    def __init__(self, style: LayerStyle, parent=None) -> None:
        super().__init__(parent)
        self._style = style
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(6)

    # ── Row builders ─────────────────────────────────────────────────────

    def _add_header(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setStyleSheet(_HEADER_STYLE)
        self._layout.addWidget(lbl)
        self._layout.addWidget(_hline())

    def _add_blend_mode_row(self) -> QComboBox:
        row = QHBoxLayout()
        lbl = QLabel("Blend Mode:")
        lbl.setFixedWidth(90)
        lbl.setStyleSheet(_LBL_STYLE)
        row.addWidget(lbl)

        combo = _blend_mode_combo(self._style.params.blend_mode)
        # Track the "committed" mode so we can revert on popup-close
        self._blend_committed = self._style.params.blend_mode

        def _on_activated(i: int) -> None:
            """User explicitly selected a blend mode."""
            mode = combo.itemData(i)
            if mode is not None:
                self._style.params.blend_mode = mode
                self._blend_committed = mode
                self.changed.emit()

        def _on_highlight(i: int) -> None:
            """Preview blend mode while hovering in the dropdown."""
            mode = combo.itemData(i)
            if mode is not None:
                self._style.params.blend_mode = mode
                self.changed.emit()

        def _on_popup_hidden() -> None:
            """Revert to the committed mode if popup closed without
            an explicit selection (e.g. user pressed Escape)."""
            current_mode = combo.currentData()
            if current_mode != self._blend_committed:
                # The combo's current index didn't change → revert
                self._style.params.blend_mode = self._blend_committed
                self.changed.emit()

        combo.activated.connect(_on_activated)
        combo.highlighted.connect(_on_highlight)

        # QComboBox doesn't have a popup-hidden signal, so we use
        # an event filter on its view (the dropdown list).
        from PySide6.QtCore import QObject, QEvent

        class _PopupWatcher(QObject):
            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.Hide:
                    _on_popup_hidden()
                return False

        self._popup_watcher = _PopupWatcher(combo)
        combo.view().installEventFilter(self._popup_watcher)

        row.addWidget(combo)
        row.addStretch()
        self._layout.addLayout(row)
        return combo

    def _add_angle_row(self, label: str = "Angle", key: str = "angle") -> AngleDial:
        cur = int(self._style.params.extra.get(key, 120))
        row = QHBoxLayout()
        lbl = QLabel(f"{label}:")
        lbl.setFixedWidth(90)
        lbl.setStyleSheet(_LBL_STYLE)
        row.addWidget(lbl)

        dial = AngleDial(cur)
        row.addWidget(dial)

        spin = QSpinBox()
        spin.setRange(0, 359)
        spin.setSuffix("°")
        spin.setValue(cur)
        spin.setFixedWidth(70)
        row.addWidget(spin)
        row.addStretch()

        def _from_dial(v: int) -> None:
            spin.blockSignals(True)
            spin.setValue(v)
            spin.blockSignals(False)
            self._style.params.extra[key] = v
            self.changed.emit()

        def _from_spin(v: int) -> None:
            dial.blockSignals(True)
            dial.set_angle(v)
            dial.blockSignals(False)
            self._style.params.extra[key] = v
            self.changed.emit()

        dial.angle_changed.connect(_from_dial)
        spin.valueChanged.connect(_from_spin)
        self._layout.addLayout(row)
        return dial

    def _add_slider_row(
        self, label: str, key: str, min_val: int, max_val: int,
        value: int | None = None, suffix: str = "",
    ) -> QSlider:
        if value is None:
            value = int(self._style.params.extra.get(key, min_val))
        row = QHBoxLayout()
        lbl = QLabel(f"{label}:")
        lbl.setFixedWidth(90)
        lbl.setStyleSheet(_LBL_STYLE)
        row.addWidget(lbl)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(value)
        row.addWidget(slider, 1)

        val_lbl = QLabel(f"{value}{suffix}")
        val_lbl.setFixedWidth(45)
        val_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        val_lbl.setStyleSheet(_LBL_STYLE)
        row.addWidget(val_lbl)

        def _update(v: int) -> None:
            val_lbl.setText(f"{v}{suffix}")
            self._style.params.extra[key] = v
            self.changed.emit()

        slider.valueChanged.connect(_update)
        self._layout.addLayout(row)
        return slider

    def _add_opacity_row(
        self, label: str = "Opacity", key: str = "opacity",
    ) -> QSlider:
        val = int(self._style.params.extra.get(key, 0.75) * 100)
        row = QHBoxLayout()
        lbl = QLabel(f"{label}:")
        lbl.setFixedWidth(90)
        lbl.setStyleSheet(_LBL_STYLE)
        row.addWidget(lbl)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(val)
        row.addWidget(slider, 1)

        val_lbl = QLabel(f"{val} %")
        val_lbl.setFixedWidth(45)
        val_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        val_lbl.setStyleSheet(_LBL_STYLE)
        row.addWidget(val_lbl)

        def _update(v: int) -> None:
            val_lbl.setText(f"{v} %")
            self._style.params.extra[key] = v / 100.0
            self.changed.emit()

        slider.valueChanged.connect(_update)
        self._layout.addLayout(row)
        return slider

    def _add_color_row(
        self, label: str = "Color", key: str = "color",
    ) -> _ColorButton:
        row = QHBoxLayout()
        lbl = QLabel(f"{label}:")
        lbl.setFixedWidth(90)
        lbl.setStyleSheet(_LBL_STYLE)
        row.addWidget(lbl)

        color_val = self._style.params.extra.get(key, [0.0, 0.0, 0.0])
        btn = _ColorButton(color_val)

        def _on_color(c: list[float]) -> None:
            self._style.params.extra[key] = c
            self.changed.emit()

        btn.color_changed.connect(_on_color)
        row.addWidget(btn)
        row.addStretch()
        self._layout.addLayout(row)
        return btn

    def _add_combo_row(
        self, label: str, key: str, items: list[str],
        current: str | None = None,
    ) -> QComboBox:
        row = QHBoxLayout()
        lbl = QLabel(f"{label}:")
        lbl.setFixedWidth(90)
        lbl.setStyleSheet(_LBL_STYLE)
        row.addWidget(lbl)

        combo = QComboBox()
        combo.addItems(items)
        if current is None:
            current = str(self._style.params.extra.get(key, items[0]))
        idx = combo.findText(current, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            combo.setCurrentIndex(idx)

        def _on_change(i: int) -> None:
            self._style.params.extra[key] = combo.itemText(i).lower()
            self.changed.emit()

        combo.currentIndexChanged.connect(_on_change)
        row.addWidget(combo)
        row.addStretch()
        self._layout.addLayout(row)
        return combo


# ── Concrete style panels ────────────────────────────────────────────────

class _DropShadowPanel(_BaseStylePanel):
    def __init__(self, style: DropShadow, parent=None) -> None:
        super().__init__(style, parent)
        self._add_header("Drop Shadow")
        self._add_blend_mode_row()
        self._add_color_row()
        self._add_opacity_row()
        self._add_angle_row()
        self._add_slider_row("Distance", "distance", 0, 200, suffix=" px")
        self._add_slider_row("Spread", "spread", 0, 100, suffix=" %")
        self._add_slider_row("Size", "size", 0, 100, suffix=" px")
        self._layout.addStretch()


class _InnerShadowPanel(_BaseStylePanel):
    def __init__(self, style: InnerShadow, parent=None) -> None:
        super().__init__(style, parent)
        self._add_header("Inner Shadow")
        self._add_blend_mode_row()
        self._add_color_row()
        self._add_opacity_row()
        self._add_angle_row()
        self._add_slider_row("Distance", "distance", 0, 200, suffix=" px")
        self._add_slider_row("Choke", "choke", 0, 100, suffix=" %")
        self._add_slider_row("Size", "size", 0, 100, suffix=" px")
        self._layout.addStretch()


class _OuterGlowPanel(_BaseStylePanel):
    def __init__(self, style: OuterGlow, parent=None) -> None:
        super().__init__(style, parent)
        self._add_header("Outer Glow")
        self._add_blend_mode_row()
        self._add_color_row()
        self._add_opacity_row()
        self._add_slider_row("Spread", "spread", 0, 100, suffix=" %")
        self._add_slider_row("Size", "size", 0, 100, suffix=" px")
        self._layout.addStretch()


class _InnerGlowPanel(_BaseStylePanel):
    def __init__(self, style: InnerGlow, parent=None) -> None:
        super().__init__(style, parent)
        self._add_header("Inner Glow")
        self._add_blend_mode_row()
        self._add_color_row()
        self._add_opacity_row()
        self._add_slider_row("Choke", "choke", 0, 100, suffix=" %")
        self._add_slider_row("Size", "size", 0, 100, suffix=" px")
        self._layout.addStretch()


class _BevelEmbossPanel(_BaseStylePanel):
    def __init__(self, style: BevelEmboss, parent=None) -> None:
        super().__init__(style, parent)
        self._add_header("Bevel and Emboss")
        self._add_blend_mode_row()
        self._add_slider_row("Depth", "depth", 0, 30)
        self._add_slider_row("Size", "size", 0, 100, suffix=" px")
        self._add_slider_row("Soften", "soften", 0, 20, suffix=" px")
        self._add_angle_row()
        self._add_slider_row("Altitude", "altitude", 0, 90, suffix="°")
        self._layout.addStretch()


class _SatinPanel(_BaseStylePanel):
    def __init__(self, style: Satin, parent=None) -> None:
        super().__init__(style, parent)
        self._add_header("Satin")
        self._add_blend_mode_row()
        self._add_color_row()
        self._add_opacity_row()
        self._add_angle_row()
        self._add_slider_row("Distance", "distance", 0, 200, suffix=" px")
        self._add_slider_row("Size", "size", 0, 100, suffix=" px")
        self._layout.addStretch()


class _ColorOverlayPanel(_BaseStylePanel):
    def __init__(self, style: ColorOverlay, parent=None) -> None:
        super().__init__(style, parent)
        self._add_header("Color Overlay")
        self._add_blend_mode_row()
        self._add_color_row()
        self._add_opacity_row()
        self._layout.addStretch()


class _GradientOverlayPanel(_BaseStylePanel):
    def __init__(self, style: GradientOverlay, parent=None) -> None:
        super().__init__(style, parent)
        self._add_header("Gradient Overlay")
        self._add_blend_mode_row()
        self._add_color_row("Color 1", "color1")
        self._add_color_row("Color 2", "color2")
        self._add_opacity_row()
        self._add_angle_row()
        self._layout.addStretch()


class _PatternOverlayPanel(_BaseStylePanel):
    def __init__(self, style: PatternOverlay, parent=None) -> None:
        super().__init__(style, parent)
        self._add_header("Pattern Overlay")
        self._add_blend_mode_row()
        self._add_opacity_row()
        # Scale: slider mapped 10..500 → 0.1..5.0
        row = QHBoxLayout()
        lbl = QLabel("Scale:")
        lbl.setFixedWidth(90)
        lbl.setStyleSheet(_LBL_STYLE)
        row.addWidget(lbl)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(10, 500)
        cur = int(float(style.params.extra.get("scale", 1.0)) * 100)
        slider.setValue(cur)
        row.addWidget(slider, 1)
        val_lbl = QLabel(f"{cur} %")
        val_lbl.setFixedWidth(45)
        val_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        val_lbl.setStyleSheet(_LBL_STYLE)
        row.addWidget(val_lbl)

        def _update(v: int) -> None:
            val_lbl.setText(f"{v} %")
            style.params.extra["scale"] = v / 100.0
            self.changed.emit()

        slider.valueChanged.connect(_update)
        self._layout.addLayout(row)
        self._layout.addStretch()


class _StrokePanel(_BaseStylePanel):
    def __init__(self, style: Stroke, parent=None) -> None:
        super().__init__(style, parent)
        self._add_header("Stroke")
        self._add_blend_mode_row()
        self._add_color_row()
        self._add_opacity_row()
        self._add_slider_row("Size", "size", 1, 50, suffix=" px")
        self._add_combo_row(
            "Position", "position",
            ["Outside", "Inside", "Center"],
            current=str(
                style.params.extra.get("position", "outside")
            ).capitalize(),
        )
        self._layout.addStretch()


# ═══════════════════════════════════════════════════════════════════════════
#  Panel factory
# ═══════════════════════════════════════════════════════════════════════════

_PANEL_MAP: dict[str, type[_BaseStylePanel]] = {
    "Drop Shadow": _DropShadowPanel,
    "Inner Shadow": _InnerShadowPanel,
    "Outer Glow": _OuterGlowPanel,
    "Inner Glow": _InnerGlowPanel,
    "Bevel and Emboss": _BevelEmbossPanel,
    "Satin": _SatinPanel,
    "Color Overlay": _ColorOverlayPanel,
    "Gradient Overlay": _GradientOverlayPanel,
    "Pattern Overlay": _PatternOverlayPanel,
    "Stroke": _StrokePanel,
}


def _make_panel(style: LayerStyle) -> _BaseStylePanel:
    cls = _PANEL_MAP.get(style.name, _BaseStylePanel)
    return cls(style)


# ═══════════════════════════════════════════════════════════════════════════
#  Unique-keyed style entry (multiple instances of the same type)
# ═══════════════════════════════════════════════════════════════════════════

# Styles that support multiple instances ("+ / −" buttons)
_DUPLICATABLE: set[str] = {
    "Drop Shadow",
    "Inner Shadow",
    "Color Overlay",
    "Gradient Overlay",
    "Stroke",
}


class _StyleEntry:
    """Wraps a LayerStyle with a unique key so the dialog can hold
    multiple instances of the same style type."""

    __slots__ = ("key", "style", "panel", "is_duplicate")

    def __init__(self, style: LayerStyle, *, is_duplicate: bool = False) -> None:
        self.key: str = uuid4().hex[:8]
        self.style: LayerStyle = style
        self.panel: _BaseStylePanel | None = None
        self.is_duplicate: bool = is_duplicate


# ═══════════════════════════════════════════════════════════════════════════
#  Main dialog
# ═══════════════════════════════════════════════════════════════════════════

_LIST_STYLE = """
    QListWidget {
        background: #2a2a2a;
        border: 1px solid #555;
        border-radius: 3px;
        font-size: 10pt;
    }
    QListWidget::item { padding: 4px 6px; }
    QListWidget::item:selected { background: #0078d4; color: white; }
"""

# ── Inline row widget for list items ─────────────────────────────────────

_INLINE_BTN = """
    QPushButton {
        font-size: 11pt; font-weight: bold; padding: 0;
        border: none; background: transparent; color: #888;
        min-width: 20px; max-width: 20px;
        min-height: 20px; max-height: 20px;
    }
    QPushButton:hover { color: #fff; }
"""

_INLINE_DEL_BTN = """
    QPushButton {
        font-size: 11pt; font-weight: bold; padding: 0;
        border: none; background: transparent; color: #888;
        min-width: 20px; max-width: 20px;
        min-height: 20px; max-height: 20px;
    }
    QPushButton:hover { color: #e74c3c; }
"""


class _ClickableLabel(QLabel):
    """A QLabel that emits *clicked* on mouse press."""
    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.clicked.emit()
        super().mousePressEvent(event)


class _StyleRowWidget(QWidget):
    """Custom widget placed on each QListWidgetItem.

    Shows:  [☑]  Style Name   [+]  [−]
    Clicking the **name label** selects the row (switches panel).
    Only the small checkbox square toggles enabled/disabled.
    "+" only for duplicatable styles; "−" only for duplicate instances.
    """

    add_clicked = Signal(str)       # entry key
    remove_clicked = Signal(str)    # entry key
    check_toggled = Signal(str, bool)  # entry key, checked
    row_clicked = Signal(str)       # entry key – select this row

    def __init__(
        self, key: str, name: str, enabled: bool,
        show_add: bool, show_remove: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._key = key
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 2, 0)
        lay.setSpacing(4)

        # Small checkbox (no label text)
        self._cb = QCheckBox()
        self._cb.setChecked(enabled)
        self._cb.setStyleSheet("QCheckBox { spacing: 0px; }")
        self._cb.toggled.connect(lambda v: self.check_toggled.emit(self._key, v))
        lay.addWidget(self._cb)

        # Clickable name label – selects the row, does NOT toggle the checkbox
        self._name_lbl = _ClickableLabel(name)
        self._name_lbl.setStyleSheet("font-size: 10pt; color: #ddd;")
        self._name_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._name_lbl.clicked.connect(lambda: self.row_clicked.emit(self._key))
        lay.addWidget(self._name_lbl, 1)

        if show_add:
            add_btn = QPushButton("+")
            add_btn.setToolTip(f"Add another {name}")
            add_btn.setStyleSheet(_INLINE_BTN)
            add_btn.clicked.connect(lambda: self.add_clicked.emit(self._key))
            lay.addWidget(add_btn)

        if show_remove:
            del_btn = QPushButton("−")
            del_btn.setToolTip("Remove this style")
            del_btn.setStyleSheet(_INLINE_DEL_BTN)
            del_btn.clicked.connect(lambda: self.remove_clicked.emit(self._key))
            lay.addWidget(del_btn)


class LayerStylesDialog(QDialog):
    """Photoshop-style Layer Styles dialog.

    Supports **multiple instances** of the same style type (e.g. two
    Drop Shadows), per-style **blend modes**, and an interactive
    **angle dial**.

    The "+" button appears inline next to duplicatable styles
    (Drop Shadow, Inner Shadow, Color Overlay, Gradient Overlay, Stroke).
    Duplicated instances get a "−" button to remove them.
    """

    styles_accepted = Signal(list)

    def __init__(
        self,
        existing_styles: list[LayerStyle] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Layer Style")
        self.setMinimumSize(720, 520)
        self.resize(790, 560)

        # Internal ordered list of entries
        self._entries: list[_StyleEntry] = []

        if existing_styles:
            # Track which style names we've already seen to mark duplicates
            seen: dict[str, int] = {}
            for s in existing_styles:
                count = seen.get(s.name, 0)
                self._entries.append(
                    _StyleEntry(s, is_duplicate=(count > 0))
                )
                seen[s.name] = count + 1
        else:
            # Populate one (disabled) instance of each type
            for _name, cls in _STYLE_TYPES:
                inst = cls()
                inst.params.enabled = False
                self._entries.append(_StyleEntry(inst))

        self._build_ui()
        self._sync_list()

        if self._list.count():
            self._list.setCurrentRow(0)

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left column ─────────────────────────────────────────────────
        left = QVBoxLayout()
        left.setContentsMargins(8, 8, 0, 8)
        left.setSpacing(4)

        title = QLabel("Styles")
        title.setStyleSheet(
            "font-size: 11pt; font-weight: bold; color: #eee;"
            " margin-bottom: 4px;"
        )
        left.addWidget(title)

        self._list = QListWidget()
        self._list.setFixedWidth(220)
        self._list.setStyleSheet(_LIST_STYLE)
        self._list.currentRowChanged.connect(self._on_row_changed)
        left.addWidget(self._list, 1)

        # Move Up / Move Down buttons
        _reorder_style = (
            "QPushButton { font-size: 9pt; padding: 2px 8px;"
            " border: 1px solid #555; border-radius: 3px;"
            " background: #3a3a3a; color: #ccc; }"
            " QPushButton:hover { background: #4a4a4a; }"
        )
        reorder_row = QHBoxLayout()
        reorder_row.setSpacing(4)
        self._up_btn = QPushButton("▲ Up")
        self._up_btn.setStyleSheet(_reorder_style)
        self._up_btn.setToolTip("Move selected style up")
        self._up_btn.clicked.connect(self._on_move_up)
        reorder_row.addWidget(self._up_btn)
        self._dn_btn = QPushButton("▼ Down")
        self._dn_btn.setStyleSheet(_reorder_style)
        self._dn_btn.setToolTip("Move selected style down")
        self._dn_btn.clicked.connect(self._on_move_down)
        reorder_row.addWidget(self._dn_btn)
        reorder_row.addStretch()
        left.addLayout(reorder_row)
        root.addLayout(left)

        # ── Separator ────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #555;")
        root.addWidget(sep)

        # ── Right column ─────────────────────────────────────────────────
        right = QVBoxLayout()
        right.setContentsMargins(8, 8, 8, 8)
        right.setSpacing(8)

        self._stack = QStackedWidget()
        for entry in self._entries:
            self._ensure_panel(entry)
        right.addWidget(self._stack, 1)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        right.addWidget(btn_box)

        root.addLayout(right, 1)

    # ── List ↔ entries sync ──────────────────────────────────────────────

    def _sync_list(self, select_row: int | None = None) -> None:
        """Rebuild the QListWidget rows from ``self._entries``."""
        cur_row = self._list.currentRow() if select_row is None else select_row
        self._list.blockSignals(True)
        self._list.clear()

        for entry in self._entries:
            name = entry.style.name
            is_dup = entry.is_duplicate
            can_dup = name in _DUPLICATABLE

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, entry.key)
            item.setSizeHint(QSize(0, 28))
            self._list.addItem(item)

            row_w = _StyleRowWidget(
                key=entry.key,
                name=name,
                enabled=entry.style.params.enabled,
                show_add=can_dup,
                show_remove=is_dup,
            )
            row_w.check_toggled.connect(self._on_check_toggled)
            row_w.add_clicked.connect(self._on_add_duplicate)
            row_w.remove_clicked.connect(self._on_remove_entry)
            row_w.row_clicked.connect(self._on_row_clicked)
            self._list.setItemWidget(item, row_w)

        self._list.blockSignals(False)
        # Restore / clamp selection
        if self._list.count():
            target = min(max(cur_row, 0), self._list.count() - 1)
            self._list.setCurrentRow(target)
            self._on_row_changed(target)

    def _ensure_panel(self, entry: _StyleEntry) -> _BaseStylePanel:
        if entry.panel is None:
            panel = _make_panel(entry.style)
            entry.panel = panel
            self._stack.addWidget(panel)
        return entry.panel

    # ── Add / remove / reorder (inline) ────────────────────────────────────

    def _on_add_duplicate(self, key: str) -> None:
        """Duplicate the style identified by *key* and insert ABOVE it."""
        idx = self._index_of(key)
        if idx is None:
            return
        source = self._entries[idx]
        cls = _STYLE_CLASS_MAP.get(source.style.name)
        if cls is None:
            return
        inst = cls()
        inst.params.enabled = True
        inst.params.extra = copy.deepcopy(source.style.params.extra)
        inst.params.blend_mode = source.style.params.blend_mode

        new_entry = _StyleEntry(inst, is_duplicate=True)
        self._entries.insert(idx, new_entry)  # above
        self._ensure_panel(new_entry)
        self._sync_list(select_row=idx)
        # Trigger live preview
        if new_entry.panel:
            new_entry.panel.changed.emit()

    def _on_remove_entry(self, key: str) -> None:
        """Remove the duplicate entry identified by *key*."""
        idx = self._index_of(key)
        if idx is None:
            return
        entry = self._entries[idx]
        if not entry.is_duplicate:
            return  # safety: never remove the original
        self._entries.pop(idx)
        if entry.panel is not None:
            self._stack.removeWidget(entry.panel)
            entry.panel.deleteLater()
            entry.panel = None
        new_row = min(idx, len(self._entries) - 1)
        self._sync_list(select_row=new_row)
        # Trigger live preview
        self._emit_any_changed()

    def _on_move_up(self) -> None:
        """Move the currently selected style one position up."""
        idx = self._list.currentRow()
        if idx <= 0 or idx >= len(self._entries):
            return
        self._entries[idx - 1], self._entries[idx] = (
            self._entries[idx], self._entries[idx - 1]
        )
        self._sync_list(select_row=idx - 1)
        self._emit_any_changed()

    def _on_move_down(self) -> None:
        """Move the currently selected style one position down."""
        idx = self._list.currentRow()
        if idx < 0 or idx >= len(self._entries) - 1:
            return
        self._entries[idx], self._entries[idx + 1] = (
            self._entries[idx + 1], self._entries[idx]
        )
        self._sync_list(select_row=idx + 1)
        self._emit_any_changed()

    def _on_row_clicked(self, key: str) -> None:
        """Select the list row for the given key (panel follows)."""
        idx = self._index_of(key)
        if idx is not None:
            self._list.setCurrentRow(idx)

    # ── Slots ────────────────────────────────────────────────────────────

    def _on_row_changed(self, row: int) -> None:
        if 0 <= row < len(self._entries):
            entry = self._entries[row]
            self._ensure_panel(entry)
            self._stack.setCurrentWidget(entry.panel)

    def _on_check_toggled(self, key: str, checked: bool) -> None:
        for entry in self._entries:
            if entry.key == key:
                entry.style.params.enabled = checked
                if entry.panel:
                    entry.panel.changed.emit()
                break

    def _on_accept(self) -> None:
        self.styles_accepted.emit(self.get_styles())
        self.accept()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _index_of(self, key: str) -> int | None:
        for i, e in enumerate(self._entries):
            if e.key == key:
                return i
        return None

    def _emit_any_changed(self) -> None:
        """Emit changed on the first wired panel to trigger live preview."""
        for e in self._entries:
            if e.panel:
                e.panel.changed.emit()
                return

    # ── Public API (used by main_window for live preview) ────────────────

    @property
    def _panels(self) -> dict[str, _BaseStylePanel]:
        """``{key: panel}`` for every entry — main_window wires the
        ``changed`` signal of each panel for live preview."""
        return {e.key: self._ensure_panel(e) for e in self._entries}

    def get_styles(self) -> list[LayerStyle]:
        """All styles (enabled **and** disabled).

        Returned in *application order*: the **last** item in the dialog
        list (bottom) is applied first; the **first** item (top) is
        applied last — so top styles visually sit on top.
        """
        return [e.style for e in reversed(self._entries)]

    def get_enabled_styles(self) -> list[LayerStyle]:
        """Only enabled styles, in application order."""
        return [
            e.style for e in reversed(self._entries)
            if e.style.params.enabled
        ]
