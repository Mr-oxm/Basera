"""White Balance — temperature / tint gradient sliders and neutral picker."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QToolButton,
    QVBoxLayout,
)

from ....adjustments.white_balance import estimate_wb_from_sample
from ...styles import render_qss
from ...theme import ThemeManager
from ...widgets.gradient_slider_row import GradientSliderRow
from .adjustment_preview_timing import PREVIEW_DEBOUNCE_MS


class WhiteBalanceDialog(QDialog):
    params_changed = Signal(dict)

    def __init__(
        self,
        title: str,
        params: dict,
        parent=None,
        *,
        composite_fn: Callable[[], Any] | None = None,
        canvas_pick_connect: Callable[[Callable[[int, int], None]], Callable[[], None]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("WhiteBalanceDialog")
        self._base_title = title
        self.setWindowTitle(title)
        self.setMinimumWidth(400)

        self._composite_fn = composite_fn
        self._canvas_pick_connect = canvas_pick_connect
        self._pick_cancel: Callable[[], None] | None = None

        t = int(round(float(np.clip(params.get("temperature", 0), -100, 100))))
        ti = int(round(float(np.clip(params.get("tint", 0), -100, 100))))

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._emit_params)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        body = QFrame()
        body.setObjectName("whiteBalanceBody")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(12)

        def _schedule() -> None:
            self._preview_timer.start()

        self._row_temp = GradientSliderRow(
            "Temperature",
            slider_min=-100,
            slider_max=100,
            value=t,
            groove_key="wb_temperature",
            label_width=120,
            on_change=_schedule,
        )
        bl.addWidget(self._row_temp)
        self._row_tint = GradientSliderRow(
            "Tint",
            slider_min=-100,
            slider_max=100,
            value=ti,
            groove_key="wb_tint",
            label_width=120,
            on_change=_schedule,
        )
        bl.addWidget(self._row_tint)

        pick_row = QHBoxLayout()
        pick_row.addStretch(1)
        self._pick_btn = QToolButton()
        self._pick_btn.setText("Picker")
        self._pick_btn.setObjectName("whiteBalancePickerButton")
        can_pick = bool(self._canvas_pick_connect and self._composite_fn)
        self._pick_btn.setEnabled(can_pick)
        self._pick_btn.setToolTip(
            "Click, then click a neutral gray area on the canvas"
            if can_pick
            else "Composite preview unavailable for sampling",
        )
        self._pick_btn.clicked.connect(self._on_picker_clicked)
        pick_row.addWidget(self._pick_btn)
        pick_row.addStretch(1)
        bl.addLayout(pick_row)

        outer.addWidget(body, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.setObjectName("whiteBalanceDialogButtons")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._apply_theme(ThemeManager.instance().active_palette)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._cancel_pending_pick()
        super().closeEvent(event)

    def _cancel_pending_pick(self) -> None:
        if self._pick_cancel is not None:
            self._pick_cancel()
            self._pick_cancel = None
        self.setWindowTitle(self._base_title)

    def _on_picker_clicked(self) -> None:
        if not self._canvas_pick_connect:
            return

        def on_doc_pick(x: int, y: int) -> None:
            self._pick_cancel = None
            self.setWindowTitle(self._base_title)
            self._apply_neutral_sample(x, y)

        self._cancel_pending_pick()
        self._pick_cancel = self._canvas_pick_connect(on_doc_pick)
        self.setWindowTitle(f"{self._base_title} — click neutral area on canvas")

    def _apply_neutral_sample(self, x: int, y: int) -> None:
        fn = self._composite_fn
        if fn is None:
            return
        rgba = fn()
        if rgba is None or rgba.size == 0:
            return
        h, w = rgba.shape[:2]
        if not (0 <= x < w and 0 <= y < h):
            return
        r, g, b = (float(rgba[y, x, i]) for i in range(3))
        temp, tint = estimate_wb_from_sample(r, g, b)
        self._row_temp.set_value(temp, block=True)
        self._row_tint.set_value(tint, block=True)
        self._preview_timer.start()

    def _apply_theme(self, palette: dict) -> None:
        self.setStyleSheet(render_qss("adjustments_panel.qss", palette))

    def _emit_params(self) -> None:
        self.params_changed.emit(self.get_params())

    def get_params(self) -> dict:
        return {
            "temperature": int(self._row_temp.logical_value()),
            "tint": int(self._row_tint.logical_value()),
        }
