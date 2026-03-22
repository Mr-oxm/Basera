"""Split toning — highlight/shadow hue & saturation + balance."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFrame, QVBoxLayout

from ...styles import render_qss
from ...theme import ThemeManager
from ...widgets.gradient_slider_row import GradientSliderRow
from .adjustment_preview_timing import PREVIEW_DEBOUNCE_MS


class SplitToningDialog(QDialog):
    params_changed = Signal(dict)

    def __init__(self, title: str, params: dict, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SplitToningDialog")
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        h_hi = int(round(float(params.get("highlights_hue", 0)) % 360))
        s_hi = int(round(max(0.0, min(100.0, float(params.get("highlights_saturation", 0))))))
        h_sh = int(round(float(params.get("shadows_hue", 0)) % 360))
        s_sh = int(round(max(0.0, min(100.0, float(params.get("shadows_saturation", 0))))))
        bal = int(round(max(0.0, min(100.0, float(params.get("balance", 50))))))

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._emit_params)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        body = QFrame()
        body.setObjectName("splitToningBody")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(12)

        def _schedule() -> None:
            self._preview_timer.start()

        self._row_h_hi = GradientSliderRow(
            "Highlights hue",
            slider_min=0,
            slider_max=359,
            value=h_hi,
            groove_key="hue_rainbow",
            label_width=130,
            on_change=_schedule,
        )
        bl.addWidget(self._row_h_hi)
        self._row_s_hi = GradientSliderRow(
            "Highlights saturation",
            slider_min=0,
            slider_max=100,
            value=s_hi,
            groove_key="toning_sat",
            label_width=130,
            on_change=_schedule,
        )
        bl.addWidget(self._row_s_hi)
        self._row_h_sh = GradientSliderRow(
            "Shadows hue",
            slider_min=0,
            slider_max=359,
            value=h_sh,
            groove_key="hue_rainbow",
            label_width=130,
            on_change=_schedule,
        )
        bl.addWidget(self._row_h_sh)
        self._row_s_sh = GradientSliderRow(
            "Shadows saturation",
            slider_min=0,
            slider_max=100,
            value=s_sh,
            groove_key="toning_sat",
            label_width=130,
            on_change=_schedule,
        )
        bl.addWidget(self._row_s_sh)
        self._row_bal = GradientSliderRow(
            "Balance",
            slider_min=0,
            slider_max=100,
            value=bal,
            groove_key="lightness",
            label_width=130,
            on_change=_schedule,
        )
        bl.addWidget(self._row_bal)

        outer.addWidget(body, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.setObjectName("splitToningDialogButtons")
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
            "highlights_hue": float(self._row_h_hi.logical_value()),
            "highlights_saturation": float(self._row_s_hi.logical_value()),
            "shadows_hue": float(self._row_h_sh.logical_value()),
            "shadows_saturation": float(self._row_s_sh.logical_value()),
            "balance": float(self._row_bal.logical_value()),
        }
