"""Normals — strength and invert Z for luminance-derived normal map."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QVBoxLayout,
)

from ...styles import render_qss
from ...theme import ThemeManager
from ...widgets.gradient_slider_row import GradientSliderRow
from .adjustment_preview_timing import PREVIEW_DEBOUNCE_MS


class NormalsDialog(QDialog):
    params_changed = Signal(dict)

    def __init__(self, title: str, params: dict, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NormalsDialog")
        self.setWindowTitle(title)
        self.setMinimumWidth(400)

        st = int(round(max(0.0, min(200.0, float(params.get("strength", 80))))))
        rot = int(round(max(-180.0, min(180.0, float(params.get("rotation", 0))))))

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._emit_params)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        body = QFrame()
        body.setObjectName("normalsBody")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(12)

        def _schedule() -> None:
            self._preview_timer.start()

        self._row_strength = GradientSliderRow(
            "Strength",
            slider_min=0,
            slider_max=200,
            value=st,
            groove_key="lightness",
            label_width=120,
            on_change=_schedule,
        )
        bl.addWidget(self._row_strength)

        self._row_rotation = GradientSliderRow(
            "Rotation",
            slider_min=-180,
            slider_max=180,
            value=rot,
            groove_key="lightness",
            label_width=120,
            on_change=_schedule,
        )
        bl.addWidget(self._row_rotation)

        self._chk_inv = QCheckBox("Invert Z (flip blue channel)")
        self._chk_inv.setObjectName("normalsInvertCheck")
        self._chk_inv.setChecked(bool(params.get("invert_z", False)))
        self._chk_inv.toggled.connect(_schedule)
        bl.addWidget(self._chk_inv)

        outer.addWidget(body, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.setObjectName("normalsDialogButtons")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._apply_theme(ThemeManager.instance().active_palette)

    def _apply_theme(self, palette: dict) -> None:
        self.setStyleSheet(render_qss("adjustments_panel.qss", palette))
        self._chk_inv.setStyleSheet(
            f"background: transparent; background-color: transparent; color: {palette['fg']}; font-size: 11px;",
        )

    def _emit_params(self) -> None:
        self.params_changed.emit(self.get_params())

    def get_params(self) -> dict:
        return {
            "strength": float(self._row_strength.logical_value()),
            "rotation": float(self._row_rotation.logical_value()),
            "invert_z": self._chk_inv.isChecked(),
        }
