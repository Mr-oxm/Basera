"""Hue/Saturation — color targets, hue range wheel, gradient sliders, HSV toggle."""

from __future__ import annotations

import copy
import math
from typing import Any, Callable

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QColor, QConicalGradient, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ....adjustments.hue_saturation import coerce_hue_saturation_params, target_id_for_hue_degrees
from ....utils.color_utils import rgb_to_hsv
from ...styles import render_qss
from ...theme import ThemeManager
from ...widgets.gradient_slider_row import GradientSliderRow
from .adjustment_preview_timing import PREVIEW_DEBOUNCE_MS

_TARGET_ROWS = (
    ("master", "Master", None),
    ("reds", "Red", "#e57373"),
    ("yellows", "Yellow", "#fff176"),
    ("greens", "Green", "#81c784"),
    ("cyans", "Cyan", "#4dd0e1"),
    ("blues", "Blue", "#64b5f6"),
    ("magentas", "Magenta", "#f06292"),
)


def _pt_on_ring(cx: float, cy: float, r: float, deg: float) -> QPointF:
    rad = math.radians(90.0 - deg)
    return QPointF(cx + r * math.cos(rad), cy - r * math.sin(rad))


class HueRangeWheel(QWidget):
    """Rainbow ring with draggable lo/hi handles (hidden for Master)."""

    rangeChanged = Signal(float, float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(220, 220)
        self._lo = 0.0
        self._hi = 360.0
        self._master = True
        self._drag: str | None = None
        self._r_outer = 102.0
        self._r_inner = 74.0
        self._r_handle = 82.0
        ThemeManager.instance().theme_changed.connect(self._pal)
        self._pal(ThemeManager.instance().active_palette)

    def _pal(self, palette: dict) -> None:
        self._palette = palette
        self.update()

    def set_state(self, lo: float, hi: float, master: bool) -> None:
        self._lo = float(lo)
        self._hi = float(hi)
        self._master = master
        self.update()

    def get_range(self) -> tuple[float, float]:
        return self._lo, self._hi

    def _hue_deg(self, pos: QPointF) -> float:
        cx, cy = self.width() / 2, self.height() / 2
        dx = pos.x() - cx
        dy = -(pos.y() - cy)
        deg = math.degrees(math.atan2(dy, dx))
        return (90.0 - deg) % 360.0

    def _handle_hit(self, pos: QPointF) -> str | None:
        if self._master:
            return None
        cx, cy = self.width() / 2, self.height() / 2
        thr = 14.0
        p_lo = _pt_on_ring(cx, cy, self._r_handle, self._lo)
        p_hi = _pt_on_ring(cx, cy, self._r_handle, self._hi)

        def _near(a: QPointF, b: QPointF) -> bool:
            return math.hypot(a.x() - b.x(), a.y() - b.y()) < thr

        if _near(QPointF(pos), p_lo):
            return "lo"
        if _near(QPointF(pos), p_hi):
            return "hi"
        return None

    def paintEvent(self, _e) -> None:
        pal = getattr(self, "_palette", ThemeManager.instance().active_palette)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width() / 2
        cy = self.height() / 2

        grad = QConicalGradient(QPointF(cx, cy), 0)
        stops = [
            (0.0, QColor(255, 0, 0)),
            (60.0 / 360.0, QColor(255, 255, 0)),
            (120.0 / 360.0, QColor(0, 255, 0)),
            (180.0 / 360.0, QColor(0, 255, 255)),
            (240.0 / 360.0, QColor(0, 0, 255)),
            (300.0 / 360.0, QColor(255, 0, 255)),
            (1.0, QColor(255, 0, 0)),
        ]
        for pos, c in stops:
            grad.setColorAt(pos, c)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(pal["bg1"]))
        painter.drawEllipse(QRectF(cx - self._r_outer, cy - self._r_outer, 2 * self._r_outer, 2 * self._r_outer))
        painter.setBrush(grad)
        painter.drawEllipse(QRectF(cx - self._r_outer, cy - self._r_outer, 2 * self._r_outer, 2 * self._r_outer))
        painter.setBrush(QColor(pal["surface_panel"]))
        painter.drawEllipse(QRectF(cx - self._r_inner, cy - self._r_inner, 2 * self._r_inner, 2 * self._r_inner))

        if not self._master:

            def sector_path(a0: float, a1: float) -> QPainterPath:
                path = QPainterPath()
                steps = max(8, int(abs(a1 - a0) / 6))
                pts_o = [_pt_on_ring(cx, cy, self._r_outer - 2, a0 + (a1 - a0) * i / steps) for i in range(steps + 1)]
                pts_i = [_pt_on_ring(cx, cy, self._r_inner + 2, a0 + (a1 - a0) * i / steps) for i in range(steps, -1, -1)]
                path.moveTo(pts_o[0])
                for p in pts_o[1:]:
                    path.lineTo(p)
                for p in pts_i:
                    path.lineTo(p)
                path.closeSubpath()
                return path

            hl = QColor(pal["accent"])
            hl.setAlpha(100)
            painter.setBrush(hl)
            if self._lo <= self._hi:
                painter.drawPath(sector_path(self._lo, self._hi))
            else:
                painter.drawPath(sector_path(self._lo, 360))
                painter.drawPath(sector_path(0, self._hi))

        painter.setPen(QPen(QColor(pal["border_light"]), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(cx - self._r_outer, cy - self._r_outer, 2 * self._r_outer, 2 * self._r_outer))

        if not self._master:
            for deg, tag in ((self._lo, "lo"), (self._hi, "hi")):
                p = _pt_on_ring(cx, cy, self._r_handle, deg)
                painter.setBrush(QColor(pal["surface_card"]))
                painter.setPen(QPen(QColor(pal["accent_border"]), 2))
                painter.drawEllipse(p, 7, 7)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._master or event.button() != Qt.MouseButton.LeftButton:
            return
        hit = self._handle_hit(event.position())
        if hit:
            self._drag = hit
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag is None:
            return
        d = self._hue_deg(event.position())
        if self._drag == "lo":
            self._lo = d
        else:
            self._hi = d
        self.rangeChanged.emit(self._lo, self._hi)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = None
        super().mouseReleaseEvent(event)


class HueSaturationDialog(QDialog):
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
        self.setObjectName("HueSatDialog")
        self._base_title = title
        self.setWindowTitle(title)
        self.setMinimumWidth(460)

        self._composite_fn = composite_fn
        self._canvas_pick_connect = canvas_pick_connect
        self._pick_cancel: Callable[[], None] | None = None

        coerced = coerce_hue_saturation_params(params)
        self._targets: dict = {k: dict(v) for k, v in coerced["targets"].items()}
        self._active = coerced["active_target"]

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._emit_params)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        body = QFrame()
        body.setObjectName("hueSatBody")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(12)

        self._chk_hsv = QCheckBox("Use HSV (Value) instead of HSL lightness")
        self._chk_hsv.setObjectName("hueSatHsvCheck")
        self._chk_hsv.setChecked(coerced["use_hsv"])
        self._chk_hsv.toggled.connect(self._on_hsv_toggled)
        bl.addWidget(self._chk_hsv)

        row_wheel = QHBoxLayout()
        row_wheel.addStretch(1)
        self._wheel = HueRangeWheel(self)
        t = self._targets[self._active]
        self._wheel.set_state(t["range_lo"], t["range_hi"], self._active == "master")
        self._wheel.rangeChanged.connect(self._on_wheel_range)
        row_wheel.addWidget(self._wheel, 0, Qt.AlignmentFlag.AlignHCenter)
        row_wheel.addStretch(1)
        bl.addLayout(row_wheel)

        tgt_row = QHBoxLayout()
        tgt_row.setSpacing(6)
        tgt_row.addStretch(1)
        reset_btn = QPushButton("Reset")
        reset_btn.setObjectName("hueSatResetButton")
        reset_btn.setToolTip("Restore default hue ranges and zero all shifts")
        reset_btn.clicked.connect(self._on_reset)
        tgt_row.addWidget(reset_btn)
        self._tgt_group = QButtonGroup(self)
        self._tgt_group.setExclusive(True)
        self._tgt_group.buttonClicked.connect(self._on_target_button_clicked)
        for tid, label, color in _TARGET_ROWS:
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setText(label)
            btn.setToolTip(f"Edit {label} range")
            btn.setMinimumSize(40, 30)
            btn.setObjectName("hueSatTargetButton")
            if color:
                btn.setStyleSheet(f"background-color: {color}; color: #111; font-weight: 600; border-radius: 8px;")
            self._tgt_group.addButton(btn)
            btn.setProperty("tid", tid)
            tgt_row.addWidget(btn)
        self._pick_btn = QToolButton()
        self._pick_btn.setText("Picker")
        self._pick_btn.setObjectName("hueSatPickerButton")
        can_pick = bool(self._canvas_pick_connect and self._composite_fn)
        self._pick_btn.setEnabled(can_pick)
        self._pick_btn.setToolTip(
            "Click, then click the image to select the hue range at that color"
            if can_pick
            else "Composite preview unavailable for sampling",
        )
        self._pick_btn.clicked.connect(self._on_picker_clicked)
        tgt_row.addWidget(self._pick_btn)
        tgt_row.addStretch(1)
        bl.addLayout(tgt_row)

        lab = QLabel(
            "Master affects the whole image. Other targets use the highlighted arc on the wheel; "
            "drag the two dots to change the hue range. Picker chooses the range from a canvas color.",
        )
        lab.setWordWrap(True)
        lab.setObjectName("hueSatHint")
        bl.addWidget(lab)

        def _schedule_preview() -> None:
            self._save_sliders()
            self._preview_timer.start()

        self._row_h = GradientSliderRow(
            "Hue shift",
            slider_min=-180,
            slider_max=180,
            value=int(round(self._targets[self._active]["hue"])),
            groove_key="hue_rainbow",
            label_width=120,
            on_change=_schedule_preview,
        )
        bl.addWidget(self._row_h)
        self._row_s = GradientSliderRow(
            "Saturation",
            slider_min=-100,
            slider_max=100,
            value=int(round(self._targets[self._active]["saturation"])),
            groove_key="sat",
            label_width=120,
            on_change=_schedule_preview,
        )
        bl.addWidget(self._row_s)
        self._row_l = GradientSliderRow(
            "Lightness",
            slider_min=-100,
            slider_max=100,
            value=int(round(self._targets[self._active]["lightness"])),
            groove_key="lightness",
            label_width=120,
            on_change=_schedule_preview,
        )
        bl.addWidget(self._row_l)

        outer.addWidget(body, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.setObjectName("hueSatDialogButtons")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._sync_target_buttons()
        self._load_sliders()
        self._update_light_label(self._chk_hsv.isChecked())

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
            self._apply_hue_sample(x, y)

        self._cancel_pending_pick()
        self._pick_cancel = self._canvas_pick_connect(on_doc_pick)
        self.setWindowTitle(f"{self._base_title} — click canvas to sample")

    def _apply_hue_sample(self, x: int, y: int) -> None:
        fn = self._composite_fn
        if fn is None:
            return
        rgba = fn()
        if rgba is None or rgba.size == 0:
            return
        h, w = rgba.shape[:2]
        if not (0 <= x < w and 0 <= y < h):
            return
        rgb = np.clip(rgba[y, x, :3], 0.0, 1.0).astype(np.float32)
        hsv = rgb_to_hsv(rgb.reshape(1, 1, 3))[0, 0]
        sat = float(hsv[1])
        if sat < 0.05:
            self._select_target("master")
            self._preview_timer.start()
            return
        h_deg = float(hsv[0]) * 360.0
        tid = target_id_for_hue_degrees(h_deg)
        if tid == "master":
            self._select_target("master")
            self._preview_timer.start()
            return
        span = 28.0
        lo = (h_deg - span) % 360.0
        hi = (h_deg + span) % 360.0
        self._targets[tid]["range_lo"] = lo
        self._targets[tid]["range_hi"] = hi
        self._select_target(tid)
        self._preview_timer.start()

    def _on_reset(self) -> None:
        d = coerce_hue_saturation_params({})
        self._targets = {k: dict(v) for k, v in d["targets"].items()}
        self._active = d["active_target"]
        self._chk_hsv.setChecked(d["use_hsv"])
        self._sync_target_buttons()
        t = self._targets[self._active]
        self._wheel.set_state(t["range_lo"], t["range_hi"], self._active == "master")
        self._load_sliders()
        self._update_light_label(self._chk_hsv.isChecked())
        self._preview_timer.start()

    def _emit_params(self) -> None:
        self.params_changed.emit(self.get_params())

    def _on_hsv_toggled(self, checked: bool) -> None:
        self._update_light_label(checked)
        self._preview_timer.start()

    def _on_target_button_clicked(self, btn: QWidget) -> None:
        tid = btn.property("tid")
        if isinstance(tid, str):
            self._select_target(tid)

    def _apply_theme(self, palette: dict) -> None:
        self.setStyleSheet(render_qss("adjustments_panel.qss", palette))
        h = self.findChild(QLabel, "hueSatHint")
        if h:
            h.setStyleSheet(f"color: {palette['fg_dim']}; font-size: 11px;")
        self._chk_hsv.setStyleSheet(
            f"background: transparent; background-color: transparent; color: {palette['fg']}; font-size: 11px;",
        )

    def _update_light_label(self, hsv: bool) -> None:
        self._row_l.set_label("Value" if hsv else "Lightness")

    def _select_target(self, tid: str) -> None:
        self._save_sliders()
        self._save_wheel_to_target()
        self._active = tid
        self._sync_target_buttons()
        t = self._targets[self._active]
        self._wheel.set_state(t["range_lo"], t["range_hi"], self._active == "master")
        self._load_sliders()
        self._preview_timer.start()

    def _sync_target_buttons(self) -> None:
        self._tgt_group.blockSignals(True)
        for btn in self._tgt_group.buttons():
            btn.setChecked(btn.property("tid") == self._active)
        self._tgt_group.blockSignals(False)

    def _save_sliders(self) -> None:
        t = self._targets[self._active]
        t["hue"] = float(self._row_h.logical_value())
        t["saturation"] = float(self._row_s.logical_value())
        t["lightness"] = float(self._row_l.logical_value())

    def _save_wheel_to_target(self) -> None:
        if self._active == "master":
            return
        lo, hi = self._wheel.get_range()
        self._targets[self._active]["range_lo"] = lo
        self._targets[self._active]["range_hi"] = hi

    def _load_sliders(self) -> None:
        t = self._targets[self._active]
        self._row_h.set_value(int(round(t["hue"])), block=True)
        self._row_s.set_value(int(round(t["saturation"])), block=True)
        self._row_l.set_value(int(round(t["lightness"])), block=True)

    def _on_wheel_range(self, lo: float, hi: float) -> None:
        if self._active != "master":
            self._targets[self._active]["range_lo"] = lo
            self._targets[self._active]["range_hi"] = hi
            self._preview_timer.start()

    def get_params(self) -> dict:
        self._save_sliders()
        self._save_wheel_to_target()
        return {
            "use_hsv": self._chk_hsv.isChecked(),
            "active_target": self._active,
            "targets": copy.deepcopy(self._targets),
        }
