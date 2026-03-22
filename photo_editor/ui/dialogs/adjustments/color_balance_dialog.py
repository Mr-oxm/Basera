"""Color Balance — Shadows / Midtones / Highlights modes (RGB shifts per mode)."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...styles import render_qss
from ...theme import ThemeManager
from ...widgets.gradient_slider_row import GradientSliderRow
from .adjustment_preview_timing import PREVIEW_DEBOUNCE_MS

_MODES = ("shadows", "midtones", "highlights")
_MODE_LABEL = {"shadows": "Shadows", "midtones": "Midtones", "highlights": "Highlights"}
_PARAM_KEY = {
    "shadows": "shadows_rgb",
    "midtones": "midtones_rgb",
    "highlights": "highlights_rgb",
}


def _read_triplet(params: dict, base: str) -> tuple[float, float, float]:
    key = _PARAM_KEY[base]
    v = params.get(key)
    if isinstance(v, (list, tuple)) and len(v) >= 3:
        return float(v[0]), float(v[1]), float(v[2])
    return (
        float(params.get(f"{key}_r", 0)),
        float(params.get(f"{key}_g", 0)),
        float(params.get(f"{key}_b", 0)),
    )


class ColorBalanceDialog(QDialog):
    params_changed = Signal(dict)

    def __init__(self, title: str, params: dict, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ColorBalanceDialog")
        self.setWindowTitle(title)
        self.setMinimumWidth(400)

        self._state = {
            m: list(_read_triplet(params, m)) for m in _MODES
        }
        self._active = "midtones"
        if "balance_mode" in params and params["balance_mode"] in _MODES:
            self._active = params["balance_mode"]

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._emit_params)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        body = QFrame()
        body.setObjectName("colorBalanceBody")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(12)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_group.buttonClicked.connect(self._on_mode_button_clicked)
        for m in _MODES:
            btn = QPushButton(_MODE_LABEL[m])
            btn.setObjectName("colorBalanceModeButton")
            btn.setCheckable(True)
            self._mode_group.addButton(btn)
            btn.setProperty("mode", m)
            mode_row.addWidget(btn, 1)
        bl.addLayout(mode_row)

        def _schedule_preview() -> None:
            self._sync_active_from_widgets()
            self._preview_timer.start()

        self._row_cyan_red = GradientSliderRow(
            "Cyan / Red",
            slider_min=-100,
            slider_max=100,
            value=0,
            groove_key="cyan_red",
            label_width=120,
            on_change=_schedule_preview,
        )
        bl.addWidget(self._row_cyan_red)
        self._row_magenta_green = GradientSliderRow(
            "Magenta / Green",
            slider_min=-100,
            slider_max=100,
            value=0,
            groove_key="magenta_green",
            label_width=120,
            on_change=_schedule_preview,
        )
        bl.addWidget(self._row_magenta_green)
        self._row_yellow_blue = GradientSliderRow(
            "Yellow / Blue",
            slider_min=-100,
            slider_max=100,
            value=0,
            groove_key="yellow_blue",
            label_width=120,
            on_change=_schedule_preview,
        )
        bl.addWidget(self._row_yellow_blue)

        hint = QLabel(
            "Each mode adjusts color cast in that tonal range. "
            "Shadows affect dark pixels, highlights bright pixels, midtones the middle.",
        )
        hint.setWordWrap(True)
        hint.setObjectName("colorBalanceHint")
        bl.addWidget(hint)

        outer.addWidget(body, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.setObjectName("colorBalanceDialogButtons")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._apply_mode_buttons()
        self._load_widgets_from_active()
        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._apply_theme(ThemeManager.instance().active_palette)

    def _emit_params(self) -> None:
        self.params_changed.emit(self.get_params())

    def _on_mode_button_clicked(self, btn: QWidget) -> None:
        m = btn.property("mode")
        if isinstance(m, str) and m in _MODES:
            self._set_mode(m)

    def _apply_theme(self, palette: dict) -> None:
        self.setStyleSheet(render_qss("adjustments_panel.qss", palette))
        h = self.findChild(QLabel, "colorBalanceHint")
        if h:
            h.setStyleSheet(f"color: {palette['fg_dim']}; font-size: 11px;")

    def _apply_mode_buttons(self) -> None:
        self._mode_group.blockSignals(True)
        for btn in self._mode_group.buttons():
            m = btn.property("mode")
            btn.setChecked(m == self._active)
        self._mode_group.blockSignals(False)

    def _set_mode(self, m: str) -> None:
        self._sync_active_from_widgets()
        self._active = m
        self._load_widgets_from_active()
        self._preview_timer.start()

    def _sync_active_from_widgets(self) -> None:
        self._state[self._active] = [
            int(self._row_cyan_red.logical_value()),
            int(self._row_magenta_green.logical_value()),
            int(self._row_yellow_blue.logical_value()),
        ]

    def _load_widgets_from_active(self) -> None:
        r, g, b = self._state[self._active]
        self._row_cyan_red.set_value(int(r), block=True)
        self._row_magenta_green.set_value(int(g), block=True)
        self._row_yellow_blue.set_value(int(b), block=True)

    def get_params(self) -> dict:
        self._sync_active_from_widgets()
        return {
            "balance_mode": self._active,
            "shadows_rgb": tuple(self._state["shadows"]),
            "midtones_rgb": tuple(self._state["midtones"]),
            "highlights_rgb": tuple(self._state["highlights"]),
        }
