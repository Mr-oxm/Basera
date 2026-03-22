"""Brightness / Contrast — gradient sliders, debounced preview."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFrame, QVBoxLayout

from ...styles import render_qss
from ...theme import ThemeManager
from ...widgets.gradient_slider_row import GradientSliderRow
from .adjustment_preview_timing import PREVIEW_DEBOUNCE_MS


class BrightnessContrastDialog(QDialog):
    params_changed = Signal(dict)

    def __init__(self, title: str, params: dict, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("BrightnessContrastDialog")
        self.setWindowTitle(title)
        self.setMinimumWidth(400)

        b = int(round(float(params.get("brightness", 0))))
        c = int(round(float(params.get("contrast", 0))))
        b = max(-100, min(100, b))
        c = max(-100, min(100, c))

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._emit_params)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        body = QFrame()
        body.setObjectName("brightnessContrastBody")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(12)

        def _schedule() -> None:
            self._preview_timer.start()

        self._row_brightness = GradientSliderRow(
            "Brightness",
            slider_min=-100,
            slider_max=100,
            value=b,
            groove_key="brightness",
            label_width=120,
            on_change=_schedule,
        )
        bl.addWidget(self._row_brightness)
        self._row_contrast = GradientSliderRow(
            "Contrast",
            slider_min=-100,
            slider_max=100,
            value=c,
            groove_key="contrast",
            label_width=120,
            on_change=_schedule,
        )
        bl.addWidget(self._row_contrast)

        outer.addWidget(body, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.setObjectName("brightnessContrastDialogButtons")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._apply_theme(ThemeManager.instance().active_palette)

    def _apply_theme(self, palette: dict) -> None:
        self.setStyleSheet(render_qss("adjustments_panel.qss", palette))

    def _emit_params(self) -> None:
        self.params_changed.emit(self.get_params())

    def get_params(self) -> dict:
        return {
            "brightness": int(self._row_brightness.logical_value()),
            "contrast": int(self._row_contrast.logical_value()),
        }
