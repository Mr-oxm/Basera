"""Interactive Curves adjustment — four independent curves (RGB + R/G/B), themed UI."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....adjustments.curves import coerce_curve_bundle, eval_curve_y, sanitize_curve_points
from ...styles import render_qss
from ...theme import ThemeManager
from .adjustment_preview_timing import PREVIEW_DEBOUNCE_MS

_CURVE_LABELS = ("RGB", "Red", "Green", "Blue")
_IDENTITY = [[0, 0], [255, 255]]


def _curve_pen_color(label: str, palette: dict, *, active: bool) -> QColor:
    if label == "RGB":
        c = QColor(palette["accent"])
    elif label == "Red":
        c = QColor("#e57373")
    elif label == "Green":
        c = QColor("#81c784")
    else:
        c = QColor("#64b5f6")
    c.setAlpha(255 if active else 96)
    return c


class CurvesPlotWidget(QWidget):
    """Shows all four curves; only the active channel has handles and receives edits."""

    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(300, 280)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._bundle: dict[str, list[list[int]]] = {
            k: list(map(list, _IDENTITY)) for k in _CURVE_LABELS
        }
        self._active = "RGB"
        self._points: list[list[int]] = list(map(list, _IDENTITY))
        self._drag_idx: int | None = None
        self._selected_idx: int | None = None
        self._hit_px = 11
        self._margin = 26
        ThemeManager.instance().theme_changed.connect(self._apply_palette)
        self._apply_palette(ThemeManager.instance().active_palette)

    def _apply_palette(self, palette: dict) -> None:
        self._palette = palette
        self.update()

    def set_bundle_from_coerce(self, c: dict) -> None:
        bundle = {
            "RGB": c["points_rgb"],
            "Red": c["points_red"],
            "Green": c["points_green"],
            "Blue": c["points_blue"],
        }
        self.set_bundle(bundle, c.get("channel", "RGB"))

    def set_bundle(self, bundle: dict[str, list], active: str) -> None:
        self._bundle = {k: sanitize_curve_points(bundle.get(k)) for k in _CURVE_LABELS}
        if active not in self._bundle:
            active = "RGB"
        self._active = active
        self._points = [list(p) for p in self._bundle[self._active]]
        self._drag_idx = None
        self._selected_idx = None
        self.update()

    def commit_active(self) -> None:
        self._bundle[self._active] = sanitize_curve_points([list(p) for p in self._points])

    def set_active(self, label: str) -> None:
        if label not in self._bundle:
            label = "RGB"
        if label == self._active:
            return
        self.commit_active()
        self._active = label
        self._points = [list(p) for p in self._bundle[self._active]]
        self._drag_idx = None
        self._selected_idx = None
        self.update()

    def reset_active_to_identity(self) -> None:
        self._points = list(map(list, _IDENTITY))
        self.commit_active()
        self._selected_idx = None
        self._drag_idx = None
        self.update()
        self.changed.emit()

    def get_processor_params(self) -> dict:
        self.commit_active()
        return {
            "points_rgb": [list(p) for p in self._bundle["RGB"]],
            "points_red": [list(p) for p in self._bundle["Red"]],
            "points_green": [list(p) for p in self._bundle["Green"]],
            "points_blue": [list(p) for p in self._bundle["Blue"]],
        }

    def _plot_rect(self) -> QRect:
        m = self._margin
        return QRect(m, m, max(1, self.width() - 2 * m), max(1, self.height() - 2 * m))

    def _x_to_px(self, x: float) -> float:
        r = self._plot_rect()
        return r.left() + (x / 255.0) * r.width()

    def _y_to_px(self, y: float) -> float:
        r = self._plot_rect()
        return r.bottom() - (y / 255.0) * r.height()

    def _px_to_xy(self, pos: QPointF) -> tuple[float, float]:
        r = self._plot_rect()
        x = (pos.x() - r.left()) / max(r.width(), 1e-6) * 255.0
        y = (r.bottom() - pos.y()) / max(r.height(), 1e-6) * 255.0
        return x, y

    def _nearest_handle(self, pos: QPointF) -> int | None:
        best_i: int | None = None
        best_d = float(self._hit_px)
        for i, p in enumerate(self._points):
            cx = self._x_to_px(p[0])
            cy = self._y_to_px(p[1])
            d = ((pos.x() - cx) ** 2 + (pos.y() - cy) ** 2) ** 0.5
            if d < best_d:
                best_d = d
                best_i = i
        return best_i

    def _draw_curve_polyline(self, painter: QPainter, points: list[list[int]], color: QColor, width: float) -> None:
        if len(points) < 2:
            return
        painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        path_x = list(range(0, 256, 2)) + [255]
        prev: QPointF | None = None
        for xv in path_x:
            yv = eval_curve_y(points, float(xv))
            q = QPointF(self._x_to_px(xv), self._y_to_px(yv))
            if prev is not None:
                painter.drawLine(prev, q)
            prev = q

    def paintEvent(self, _event) -> None:
        pal = getattr(self, "_palette", ThemeManager.instance().active_palette)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.fillRect(self.rect(), QColor(pal["bg2"]))

        plot = self._plot_rect()
        painter.setPen(QPen(QColor(pal["border_light"]), 1))
        painter.drawRect(plot)

        grid_c = QColor(pal["outline_soft"])
        painter.setPen(QPen(grid_c, 1, Qt.PenStyle.DotLine))
        for g in (64, 128, 192):
            gx = self._x_to_px(g)
            painter.drawLine(int(gx), plot.top(), int(gx), plot.bottom())
            gy = self._y_to_px(g)
            painter.drawLine(plot.left(), int(gy), plot.right(), int(gy))

        fg_dim = QColor(pal["fg_dim"])
        painter.setPen(QPen(fg_dim, 1, Qt.PenStyle.DashLine))
        painter.drawLine(
            int(self._x_to_px(0)), int(self._y_to_px(0)),
            int(self._x_to_px(255)), int(self._y_to_px(255)),
        )

        for label in _CURVE_LABELS:
            if label == self._active:
                continue
            pts = self._bundle[label]
            col = _curve_pen_color(label, pal, active=False)
            self._draw_curve_polyline(painter, pts, col, 1.5)

        act_col = _curve_pen_color(self._active, pal, active=True)
        self._draw_curve_polyline(painter, self._points, act_col, 2.75)

        handle_fill = QColor(pal["surface_panel"])
        handle_border = QColor(pal["accent_border"])
        for i, pt in enumerate(self._points):
            cx, cy = self._x_to_px(pt[0]), self._y_to_px(pt[1])
            r = 5.5 if i == self._selected_idx else 4.5
            painter.setPen(QPen(handle_border if i == self._selected_idx else act_col, 2))
            painter.setBrush(handle_fill)
            painter.drawEllipse(QPointF(cx, cy), r, r)

        painter.setPen(QPen(QColor(pal["fg_dim"])))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawText(4, self.height() - 6, "0")
        painter.drawText(self.width() - 22, self.height() - 6, "255")
        painter.drawText(4, self._margin - 6, "255")
        painter.drawText(4, self.height() - self._margin + 14, "Input")
        painter.drawText(self.width() - 52, self._margin + 4, "Output")

    def _after_edit(self) -> None:
        self.commit_active()
        self.changed.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        idx = self._nearest_handle(pos)
        if idx is not None:
            self._drag_idx = idx
            self._selected_idx = idx
            self.setFocus(Qt.FocusReason.MouseFocusReason)
        else:
            self._drag_idx = None
            self._selected_idx = None
        self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_idx is None:
            return
        i = self._drag_idx
        x, y = self._px_to_xy(event.position())
        y = max(0.0, min(255.0, y))
        if i == 0:
            self._points[0] = [0, int(round(y))]
        elif i == len(self._points) - 1:
            self._points[-1] = [255, int(round(y))]
        else:
            lo = self._points[i - 1][0] + 1
            hi = self._points[i + 1][0] - 1
            xi = int(round(max(lo, min(hi, x))))
            self._points[i] = [xi, int(round(y))]
        self._after_edit()
        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_idx = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        if not self._plot_rect().contains(pos.toPoint()):
            return
        x, _y = self._px_to_xy(pos)
        xi = int(round(max(1.0, min(254.0, x))))
        for pt in self._points:
            if abs(pt[0] - xi) < 6:
                return
        yi = int(round(eval_curve_y(self._points, float(xi))))
        self._points.append([xi, yi])
        self._points.sort(key=lambda t: t[0])
        self._points[0] = [0, self._points[0][1]]
        self._points[-1] = [255, self._points[-1][1]]
        self._selected_idx = next(j for j, pt in enumerate(self._points) if pt[0] == xi)
        self._after_edit()
        self.update()
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            i = self._selected_idx
            if i is not None and 0 < i < len(self._points) - 1:
                del self._points[i]
                self._selected_idx = min(i, len(self._points) - 1)
                self._after_edit()
                self.update()
                event.accept()
                return
        super().keyPressEvent(event)


class CurvesDialog(QDialog):
    """Modal dialog matching FilterDialog preview contract (params_changed, get_params)."""

    params_changed = Signal(dict)

    def __init__(self, title: str, params: dict, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("CurvesDialog")
        self.setWindowTitle(title)
        self.setMinimumWidth(460)

        coerced = coerce_curve_bundle(params)

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._emit_params)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        body = QFrame()
        body.setObjectName("curvesBody")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(10)

        hint = QLabel(
            "All four curves are stored separately. Choose a channel to edit it; "
            "other curves stay visible in the background. "
            "Double-click to add a point, Delete removes a selected interior point.",
        )
        hint.setWordWrap(True)
        hint.setObjectName("curvesHint")
        bl.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(8)
        ch_lbl = QLabel("Edit channel")
        ch_lbl.setObjectName("curvesFieldLabel")
        row.addWidget(ch_lbl)
        self._channel = QComboBox()
        self._channel.setObjectName("curvesChannelCombo")
        self._channel.addItems(list(_CURVE_LABELS))
        self._channel.blockSignals(True)
        self._channel.setCurrentText(coerced["channel"])
        self._channel.blockSignals(False)
        self._channel.currentTextChanged.connect(self._on_channel_changed)
        row.addWidget(self._channel, 1)
        bl.addLayout(row)

        plot_frame = QFrame()
        plot_frame.setObjectName("curvesPlotSurface")
        pfl = QVBoxLayout(plot_frame)
        pfl.setContentsMargins(10, 10, 10, 10)
        self._plot = CurvesPlotWidget(self)
        self._plot.set_bundle_from_coerce(coerced)
        self._plot.changed.connect(self._schedule_preview)
        pfl.addWidget(self._plot)
        bl.addWidget(plot_frame)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        reset_btn = QPushButton("Reset active curve")
        reset_btn.setObjectName("curvesSecondaryButton")
        reset_btn.setToolTip("Set the selected channel to a straight diagonal (no change)")
        reset_btn.clicked.connect(self._reset_curve)
        tools.addWidget(reset_btn)
        reset_all = QPushButton("Reset all curves")
        reset_all.setObjectName("curvesSecondaryButton")
        reset_all.setToolTip("Diagonal for RGB, Red, Green, and Blue")
        reset_all.clicked.connect(self._reset_all_curves)
        tools.addWidget(reset_all)
        tools.addStretch()
        bl.addLayout(tools)

        outer.addWidget(body, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.setObjectName("curvesDialogButtons")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._apply_theme(ThemeManager.instance().active_palette)

    def _apply_theme(self, palette: dict) -> None:
        self.setStyleSheet(render_qss("adjustments_panel.qss", palette))
        hint = self.findChild(QLabel, "curvesHint")
        if hint is not None:
            hint.setStyleSheet(
                f"color: {palette['fg_dim']}; background: transparent; font-size: 11px; line-height: 1.35;"
            )

    def _on_channel_changed(self, text: str) -> None:
        self._plot.set_active(text)
        self._schedule_preview()

    def _reset_curve(self) -> None:
        self._plot.reset_active_to_identity()
        self._schedule_preview()

    def _reset_all_curves(self) -> None:
        ident = list(map(list, _IDENTITY))
        self._plot.set_bundle(
            {k: list(map(list, ident)) for k in _CURVE_LABELS},
            self._channel.currentText(),
        )
        self._schedule_preview()

    def _schedule_preview(self) -> None:
        self._preview_timer.start()

    def _emit_params(self) -> None:
        self.params_changed.emit(self.get_params())

    def get_params(self) -> dict:
        p = self._plot.get_processor_params()
        p["channel"] = self._channel.currentText()
        return p
