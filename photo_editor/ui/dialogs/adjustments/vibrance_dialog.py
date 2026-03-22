"""Vibrance — single gradient slider, debounced preview."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFrame, QVBoxLayout

from ...styles import render_qss
from ...theme import ThemeManager
from ...widgets.gradient_slider_row import GradientSliderRow
from .adjustment_preview_timing import PREVIEW_DEBOUNCE_MS


class VibranceDialog(QDialog):
    params_changed = Signal(dict)

    def __init__(self, title: str, params: dict, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("VibranceDialog")
        self.setWindowTitle(title)
        self.setMinimumWidth(400)

        v = int(round(float(params.get("vibrance", 0))))
        v = max(-100, min(100, v))

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._emit_params)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        body = QFrame()
        body.setObjectName("vibranceBody")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(12)

        self._row = GradientSliderRow(
            "Vibrance",
            slider_min=-100,
            slider_max=100,
            value=v,
            groove_key="vibrance",
            label_width=120,
            on_change=lambda: self._preview_timer.start(),
        )
        bl.addWidget(self._row)

        outer.addWidget(body, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.setObjectName("vibranceDialogButtons")
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
        return {"vibrance": int(self._row.logical_value())}
