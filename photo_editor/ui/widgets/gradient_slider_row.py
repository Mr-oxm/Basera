"""Reusable label + gradient groove slider + spin box for adjustment dialogs."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSizePolicy,
    QSpinBox,
    QWidget,
)

from ..theme import ThemeManager

# qlineargradient strings (groove only); handles/borders use theme palette.
GROOVE_PRESETS: dict[str, str] = {
    "bw": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #000000, stop:1 #ffffff)",
    "gamma": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #5c5c5c, stop:0.5 #a8a8a8, stop:1 #ffffff)",
    "hue_rainbow": (
        "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #ff0000, stop:0.17 #ffff00, stop:0.33 #00ff00, "
        "stop:0.5 #00ffff, stop:0.67 #0000ff, stop:0.83 #ff00ff, stop:1 #ff0000)"
    ),
    "sat": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #b0b0b0, stop:1 #e53935)",
    "lightness": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #404040, stop:1 #ffffff)",
    "cyan_red": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #26c6da, stop:1 #ef5350)",
    "magenta_green": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #ec407a, stop:1 #66bb6a)",
    "yellow_blue": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #ffee58, stop:1 #42a5f5)",
    "brightness": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #6e6e6e, stop:0.5 #bdbdbd, stop:1 #ffffff)",
    "contrast": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #9e9e9e, stop:0.5 #f5f5f5, stop:1 #9e9e9e)",
    "vibrance": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #b0b0b0, stop:1 #ab47bc)",
    "wb_temperature": (
        "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #1e88e5, stop:0.5 #9e9e9e, stop:1 #ffd54f)"
    ),
    "wb_tint": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #43a047, stop:0.5 #9e9e9e, stop:1 #e040fb)",
    "toning_sat": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #212121, stop:1 #ffffff)",
}


def _slider_stylesheet(palette: dict, groove_key: str) -> str:
    g = GROOVE_PRESETS.get(groove_key, GROOVE_PRESETS["bw"])
    border = palette["border_light"]
    card = palette["surface_card"]
    ab = palette["accent_border"]
    return f"""
    QSlider {{
      background: transparent;
    }}
    QSlider::groove:horizontal {{
      height: 12px;
      border-radius: 6px;
      border: 1px solid {border};
      background: {g};
    }}
    QSlider::sub-page:horizontal,
    QSlider::add-page:horizontal {{
      background: transparent;
      border: none;
      height: 12px;
    }}
    QSlider::handle:horizontal {{
      width: 14px;
      height: 14px;
      margin: -5px 0;
      background: {card};
      border: 2px solid {ab};
      border-radius: 8px;
    }}
    """


def _spin_stylesheet(palette: dict) -> str:
    return f"""
    QSpinBox, QDoubleSpinBox {{
      background-color: {palette["input_bg"]};
      border: 1px solid {palette["input_border"]};
      border-radius: 8px;
      padding: 4px 8px;
      color: {palette["fg"]};
      min-width: 36px;
      max-width: 52px;
      min-height: 24px;
      padding: 3px 6px;
    }}
    """


class GradientSliderRow(QWidget):
    """Horizontal row: label | themed gradient slider | spin box.

    ``valueChanged`` fires for logical value: ``int`` for mode ``int``,
    ``float`` for mode ``gamma`` or ``float_spin``.
    """

    valueChanged = Signal(object)

    def __init__(
        self,
        label: str,
        *,
        slider_min: int = 0,
        slider_max: int = 255,
        value: int = 0,
        spin_min: int | None = None,
        spin_max: int | None = None,
        groove_key: str = "bw",
        label_width: int = 120,
        mode: str = "int",
        gamma_min: float = 0.1,
        gamma_max: float = 10.0,
        gamma_value: float = 1.0,
        float_spin: bool = False,
        float_min: float = -100.0,
        float_max: float = 100.0,
        float_value: float = 0.0,
        float_step: float = 1.0,
        float_decimals: int = 1,
        on_change: Callable[[], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._mode = mode
        self._on_change = on_change
        self._groove_key = groove_key

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self._lbl = QLabel(label)
        self._lbl.setFixedWidth(label_width)
        lay.addWidget(self._lbl)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimumHeight(22)

        if mode == "gamma":
            self._slider.setRange(10, 1000)
            gv = int(round(gamma_value * 100))
            self._slider.setValue(max(10, min(1000, gv)))
            self._spin = QDoubleSpinBox()
            self._spin.setRange(gamma_min, gamma_max)
            self._spin.setSingleStep(0.01)
            self._spin.setDecimals(2)
            self._spin.setValue(float(gamma_value))
        elif float_spin:
            self._mode = "float_spin"
            self._slider.setRange(int(float_min * 10), int(float_max * 10))
            self._slider.setValue(int(round(float_value * 10)))
            self._spin = QDoubleSpinBox()
            self._spin.setRange(float_min, float_max)
            self._spin.setSingleStep(float_step)
            self._spin.setDecimals(float_decimals)
            self._spin.setValue(float_value)
        else:
            smin = spin_min if spin_min is not None else slider_min
            smax = spin_max if spin_max is not None else slider_max
            self._slider.setRange(slider_min, slider_max)
            self._slider.setValue(int(value))
            self._spin = QSpinBox()
            self._spin.setRange(int(smin), int(smax))
            self._spin.setValue(int(value))

        self._spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._spin.setMaximumWidth(68 if isinstance(self._spin, QDoubleSpinBox) else 48)
        self._slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._slider.setMinimumWidth(100)

        lay.addWidget(self._slider, 1)
        lay.addWidget(self._spin, 0, Qt.AlignmentFlag.AlignRight)

        self._wire()
        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._apply_theme(ThemeManager.instance().active_palette)

    def _wire(self) -> None:
        if self._mode == "gamma":

            def on_sl(v: int) -> None:
                self._spin.blockSignals(True)
                self._spin.setValue(round(v / 100.0, 2))
                self._spin.blockSignals(False)
                self._emit_change()

            def on_sp(v: float) -> None:
                self._slider.blockSignals(True)
                self._slider.setValue(int(round(v * 100)))
                self._slider.blockSignals(False)
                self._emit_change()

            self._slider.valueChanged.connect(on_sl)
            self._spin.valueChanged.connect(on_sp)
        elif self._mode == "float_spin":

            def on_sl_f(v: int) -> None:
                self._spin.blockSignals(True)
                self._spin.setValue(round(v / 10.0, 4))
                self._spin.blockSignals(False)
                self._emit_change()

            def on_sp_f(v: float) -> None:
                self._slider.blockSignals(True)
                self._slider.setValue(int(round(v * 10)))
                self._slider.blockSignals(False)
                self._emit_change()

            self._slider.valueChanged.connect(on_sl_f)
            self._spin.valueChanged.connect(on_sp_f)
        else:

            def on_sl_i(v: int) -> None:
                self._spin.blockSignals(True)
                self._spin.setValue(v)
                self._spin.blockSignals(False)
                self._emit_change()

            def on_sp_i(v: int) -> None:
                self._slider.blockSignals(True)
                self._slider.setValue(int(v))
                self._slider.blockSignals(False)
                self._emit_change()

            self._slider.valueChanged.connect(on_sl_i)
            self._spin.valueChanged.connect(on_sp_i)

    def _emit_change(self) -> None:
        self.valueChanged.emit(self.logical_value())
        if self._on_change is not None:
            self._on_change()

    def _apply_theme(self, palette: dict) -> None:
        self._slider.setStyleSheet(_slider_stylesheet(palette, self._groove_key))
        self._spin.setStyleSheet(_spin_stylesheet(palette))
        self._lbl.setStyleSheet(f"color: {palette['fg']}; background: transparent;")

    def logical_value(self) -> int | float:
        if self._mode == "gamma":
            return float(self._spin.value())
        if self._mode == "float_spin":
            return float(self._spin.value())
        return int(self._slider.value())

    def set_value(self, v: int | float, *, block: bool = False) -> None:
        if block:
            self._slider.blockSignals(True)
            self._spin.blockSignals(True)
        try:
            if self._mode == "gamma":
                fv = float(v)
                self._spin.setValue(fv)
                self._slider.setValue(max(10, min(1000, int(round(fv * 100)))))
            elif self._mode == "float_spin":
                fv = float(v)
                self._spin.setValue(fv)
                self._slider.setValue(int(round(fv * 10)))
            else:
                iv = int(v)
                self._slider.setValue(iv)
                self._spin.setValue(iv)
        finally:
            if block:
                self._slider.blockSignals(False)
                self._spin.blockSignals(False)

    def block_signals(self, b: bool) -> None:
        self._slider.blockSignals(b)
        self._spin.blockSignals(b)

    def set_label(self, text: str) -> None:
        self._lbl.setText(text)

    def slider_widget(self) -> QSlider:
        return self._slider
