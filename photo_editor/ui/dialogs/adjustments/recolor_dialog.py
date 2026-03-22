"""Recolor — from/to hue band with amount."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFrame, QVBoxLayout

from ...styles import render_qss
from ...theme import ThemeManager
from ...widgets.gradient_slider_row import GradientSliderRow
from .adjustment_preview_timing import PREVIEW_DEBOUNCE_MS


class RecolorDialog(QDialog):
    params_changed = Signal(dict)

    def __init__(self, title: str, params: dict, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("RecolorDialog")
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        fh = int(round(float(params.get("from_hue", 0)) % 360))
        th = int(round(float(params.get("to_hue", 60)) % 360))
        wd = int(round(max(4.0, min(180.0, float(params.get("width", 45))))))
        am = int(round(max(0.0, min(100.0, float(params.get("amount", 100))))))

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._emit_params)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        body = QFrame()
        body.setObjectName("recolorBody")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(12)

        def _schedule() -> None:
            self._preview_timer.start()

        self._row_from = GradientSliderRow(
            "From hue",
            slider_min=0,
            slider_max=359,
            value=fh,
            groove_key="hue_rainbow",
            label_width=120,
            on_change=_schedule,
        )
        bl.addWidget(self._row_from)
        self._row_to = GradientSliderRow(
            "To hue",
            slider_min=0,
            slider_max=359,
            value=th,
            groove_key="hue_rainbow",
            label_width=120,
            on_change=_schedule,
        )
        bl.addWidget(self._row_to)
        self._row_width = GradientSliderRow(
            "Range",
            slider_min=10,
            slider_max=180,
            value=wd,
            groove_key="lightness",
            label_width=120,
            on_change=_schedule,
        )
        bl.addWidget(self._row_width)
        self._row_amount = GradientSliderRow(
            "Amount",
            slider_min=0,
            slider_max=100,
            value=am,
            groove_key="sat",
            label_width=120,
            on_change=_schedule,
        )
        bl.addWidget(self._row_amount)

        outer.addWidget(body, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.setObjectName("recolorDialogButtons")
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
            "from_hue": float(self._row_from.logical_value()),
            "to_hue": float(self._row_to.logical_value()),
            "width": float(self._row_width.logical_value()),
            "amount": float(self._row_amount.logical_value()),
        }
