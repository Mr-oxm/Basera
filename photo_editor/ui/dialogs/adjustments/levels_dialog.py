"""Levels adjustment — histogram, channel bundle, themed gradient sliders."""

from __future__ import annotations

from typing import Callable

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ....adjustments.levels import coerce_levels_bundle
from ...styles import render_qss
from ...theme import ThemeManager
from ...widgets.gradient_slider_row import GradientSliderRow
from .adjustment_preview_timing import PREVIEW_DEBOUNCE_MS

_CH_LABELS = ("RGB", "Red", "Green", "Blue")
_CH_TO_KEY = {
    "RGB": "levels_rgb",
    "Red": "levels_red",
    "Green": "levels_green",
    "Blue": "levels_blue",
}


def _histogram_data(rgba: np.ndarray | None, channel: str) -> dict[str, np.ndarray] | None:
    if rgba is None or rgba.size == 0:
        return None
    rgb = np.clip(rgba[..., :3] * 255.0, 0, 255).astype(np.int64)
    r = rgb[..., 0].ravel()
    g = rgb[..., 1].ravel()
    b = rgb[..., 2].ravel()
    hr = np.bincount(r, minlength=256).astype(np.float64)
    hg = np.bincount(g, minlength=256).astype(np.float64)
    hb = np.bincount(b, minlength=256).astype(np.float64)
    lum = np.clip(0.2126 * r + 0.7152 * g + 0.0722 * b, 0, 255).astype(np.int64)
    hl = np.bincount(lum, minlength=256).astype(np.float64)
    mx = max(float(hr.max()), float(hg.max()), float(hb.max()), float(hl.max()), 1.0)
    hr /= mx
    hg /= mx
    hb /= mx
    hl /= mx
    return {"R": hr, "G": hg, "B": hb, "L": hl, "mode": channel}


class LevelsHistogramWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(96)
        self.setMaximumHeight(120)
        self._data: dict[str, np.ndarray] | None = None
        ThemeManager.instance().theme_changed.connect(self._pal)
        self._pal(ThemeManager.instance().active_palette)

    def _pal(self, palette: dict) -> None:
        self._palette = palette
        self.update()

    def set_data(self, data: dict[str, np.ndarray] | None) -> None:
        self._data = data
        self.update()

    def paintEvent(self, _e) -> None:
        p = getattr(self, "_palette", ThemeManager.instance().active_palette)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)
        painter.fillRect(rect, QColor(p["bg2"]))
        painter.setPen(QPen(QColor(p["border_light"]), 1))
        painter.drawRect(rect)

        if self._data is None:
            painter.setPen(QColor(p["fg_dim"]))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No preview")
            return

        mode = self._data.get("mode", "RGB")
        w = rect.width()
        h = rect.height()
        bottom = rect.bottom()

        def polyline(norm: np.ndarray, color: QColor, width: float = 1.5) -> None:
            painter.setPen(QPen(color, width))
            path = []
            for i in range(256):
                x = rect.left() + (i / 255.0) * w
                y = bottom - norm[i] * (h - 4)
                path.append((x, y))
            for i in range(len(path) - 1):
                painter.drawLine(
                    int(path[i][0]), int(path[i][1]),
                    int(path[i + 1][0]), int(path[i + 1][1]),
                )

        if mode == "RGB":
            polyline(self._data["R"], QColor(200, 80, 80, 200), 1.25)
            polyline(self._data["G"], QColor(80, 180, 80, 200), 1.25)
            polyline(self._data["B"], QColor(80, 120, 220, 200), 1.25)
            polyline(self._data["L"], QColor(230, 230, 230, 140), 1.0)
        elif mode == "Red":
            polyline(self._data["R"], QColor(240, 120, 120), 2.0)
        elif mode == "Green":
            polyline(self._data["G"], QColor(120, 220, 140), 2.0)
        else:
            polyline(self._data["B"], QColor(130, 170, 240), 2.0)


class LevelsDialog(QDialog):
    params_changed = Signal(dict)

    def __init__(
        self,
        title: str,
        params: dict,
        parent=None,
        composite_fn: Callable[[], np.ndarray | None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("LevelsDialog")
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        self._composite_fn = composite_fn
        self._bundle = coerce_levels_bundle(params)
        self._suppress = False
        self._prev_ch = str(self._bundle.get("channel", "RGB"))

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._emit_params)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        body = QFrame()
        body.setObjectName("levelsBody")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(10)

        self._hist = LevelsHistogramWidget()
        bl.addWidget(self._hist)

        row = QHBoxLayout()
        row.addWidget(QLabel("Channel"))
        self._channel = QComboBox()
        self._channel.addItems(list(_CH_LABELS))
        self._channel.setObjectName("levelsChannelCombo")
        self._channel.setCurrentText(self._bundle.get("channel", "RGB"))
        self._channel.currentTextChanged.connect(self._on_channel_changed)
        row.addWidget(self._channel, 1)
        row.addWidget(QLabel("Preset"))
        self._preset = QComboBox()
        self._preset.setObjectName("levelsPresetCombo")
        self._preset.addItems(["Master"])
        self._preset.setCurrentText(self._bundle.get("preset", "Master"))
        self._preset.currentTextChanged.connect(lambda _t: self._schedule())
        row.addWidget(self._preset, 1)
        bl.addLayout(row)

        def _sched() -> None:
            self._schedule()

        b0 = self._bundle[self._active_key()]
        self._row_ib = GradientSliderRow(
            "Input black", slider_min=0, slider_max=254, value=int(b0["input_black"]),
            groove_key="bw", on_change=_sched, parent=self,
        )
        self._row_iw = GradientSliderRow(
            "Input white", slider_min=1, slider_max=255, value=int(b0["input_white"]),
            groove_key="bw", on_change=_sched, parent=self,
        )
        self._row_g = GradientSliderRow(
            "Gamma", mode="gamma", gamma_value=float(b0["gamma"]),
            groove_key="gamma", on_change=_sched, parent=self,
        )
        self._row_ob = GradientSliderRow(
            "Output black", slider_min=0, slider_max=255, value=int(b0["output_black"]),
            groove_key="bw", on_change=_sched, parent=self,
        )
        self._row_ow = GradientSliderRow(
            "Output white", slider_min=0, slider_max=255, value=int(b0["output_white"]),
            groove_key="bw", on_change=_sched, parent=self,
        )

        for rw in (self._row_ib, self._row_iw, self._row_g, self._row_ob, self._row_ow):
            bl.addWidget(rw)
            rw.slider_widget().sliderReleased.connect(self._on_slider_released)

        outer.addWidget(body, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.setObjectName("levelsDialogButtons")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._apply_theme(ThemeManager.instance().active_palette)
        QTimer.singleShot(0, self._refresh_histogram)

    def _apply_theme(self, palette: dict) -> None:
        self.setStyleSheet(render_qss("adjustments_panel.qss", palette))

    def _active_key(self) -> str:
        return _CH_TO_KEY[self._channel.currentText()]

    def _load_block_into_widgets(self) -> None:
        b = self._bundle[self._active_key()]
        self._suppress = True
        self._row_ib.set_value(int(b["input_black"]), block=True)
        self._row_iw.set_value(int(b["input_white"]), block=True)
        self._row_g.set_value(float(b["gamma"]), block=True)
        self._row_ob.set_value(int(b["output_black"]), block=True)
        self._row_ow.set_value(int(b["output_white"]), block=True)
        self._suppress = False

    def _widgets_to_block(self) -> dict:
        ib = int(self._row_ib.logical_value())
        iw = int(self._row_iw.logical_value())
        if iw <= ib:
            iw = ib + 1
            self._suppress = True
            self._row_iw.set_value(iw, block=True)
            self._suppress = False
        return {
            "input_black": ib,
            "input_white": iw,
            "gamma": float(self._row_g.logical_value()),
            "output_black": int(self._row_ob.logical_value()),
            "output_white": int(self._row_ow.logical_value()),
        }

    def _on_channel_changed(self, text: str) -> None:
        if self._suppress:
            return
        old_key = _CH_TO_KEY.get(self._prev_ch, "levels_rgb")
        self._bundle[old_key] = self._widgets_to_block()
        self._prev_ch = text
        self._bundle["channel"] = text
        self._load_block_into_widgets()
        self._refresh_histogram()
        self._schedule()

    def _schedule(self) -> None:
        if self._suppress:
            return
        self._bundle[self._active_key()] = self._widgets_to_block()
        self._bundle["channel"] = self._channel.currentText()
        self._bundle["preset"] = self._preset.currentText()
        self._preview_timer.start()

    def _emit_params(self) -> None:
        self.params_changed.emit(self.get_params())
        QTimer.singleShot(80, self._refresh_histogram)

    def _on_slider_released(self) -> None:
        QTimer.singleShot(60, self._refresh_histogram)

    def _refresh_histogram(self) -> None:
        fn = self._composite_fn
        rgba = fn() if fn is not None else None
        self._hist.set_data(_histogram_data(rgba, self._channel.currentText()))

    def get_params(self) -> dict:
        self._bundle[_CH_TO_KEY[self._channel.currentText()]] = self._widgets_to_block()
        self._bundle["channel"] = self._channel.currentText()
        self._bundle["preset"] = self._preset.currentText()
        out = {k: dict(self._bundle[k]) for k in _CH_TO_KEY.values()}
        out["channel"] = self._bundle["channel"]
        out["preset"] = self._bundle["preset"]
        return out
