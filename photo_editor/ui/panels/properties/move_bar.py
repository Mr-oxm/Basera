"""Move tool properties bar — alignment and transform buttons."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPen, QColor as QC
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QWidget

from .base import _icon_from_painter, make_separator

_MOVE_BTN_STYLE = """
    QPushButton {
        background: transparent;
        border: none;
        border-radius: 4px;
        padding: 3px;
        min-width: 26px; min-height: 26px;
        max-width: 26px; max-height: 26px;
    }
    QPushButton:hover { background-color: rgba(255, 255, 255, 0.08); }
    QPushButton:pressed { background-color: rgba(74, 111, 165, 0.5); }
"""

_MOVE_SEP_STYLE = "color: #444; background: #444; max-width: 1px; margin: 4px 2px;"


def _make_align_icons():
    """Return a dict of action-name → QIcon for the alignment buttons."""
    from PySide6.QtCore import QRectF

    icons = {}
    line_c = QC("#888888")
    bar_c = QC("#cccccc")

    def _pen(color, w=1.5):
        pen = QPen(color, w)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        return pen

    def align_left(p, s):
        p.setPen(_pen(bar_c, 1.5))
        p.drawLine(4, 3, 4, s - 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(line_c)
        p.drawRoundedRect(QRectF(6, 5, 10, 3), 1, 1)
        p.drawRoundedRect(QRectF(6, 12, 7, 3), 1, 1)

    def align_center_h(p, s):
        cx = s / 2
        p.setPen(_pen(bar_c, 1.5))
        p.drawLine(int(cx), 3, int(cx), s - 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(line_c)
        p.drawRoundedRect(QRectF(cx - 5, 5, 10, 3), 1, 1)
        p.drawRoundedRect(QRectF(cx - 3.5, 12, 7, 3), 1, 1)

    def align_right(p, s):
        p.setPen(_pen(bar_c, 1.5))
        p.drawLine(s - 4, 3, s - 4, s - 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(line_c)
        p.drawRoundedRect(QRectF(s - 14, 5, 10, 3), 1, 1)
        p.drawRoundedRect(QRectF(s - 11, 12, 7, 3), 1, 1)

    def align_top(p, s):
        p.setPen(_pen(bar_c, 1.5))
        p.drawLine(3, 4, s - 3, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(line_c)
        p.drawRoundedRect(QRectF(5, 6, 3, 10), 1, 1)
        p.drawRoundedRect(QRectF(12, 6, 3, 7), 1, 1)

    def align_middle_v(p, s):
        cy = s / 2
        p.setPen(_pen(bar_c, 1.5))
        p.drawLine(3, int(cy), s - 3, int(cy))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(line_c)
        p.drawRoundedRect(QRectF(5, cy - 5, 3, 10), 1, 1)
        p.drawRoundedRect(QRectF(12, cy - 3.5, 3, 7), 1, 1)

    def align_bottom(p, s):
        p.setPen(_pen(bar_c, 1.5))
        p.drawLine(3, s - 4, s - 3, s - 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(line_c)
        p.drawRoundedRect(QRectF(5, s - 14, 3, 10), 1, 1)
        p.drawRoundedRect(QRectF(12, s - 11, 3, 7), 1, 1)

    for name, fn in [
        ("align_left", align_left), ("align_center_h", align_center_h),
        ("align_right", align_right), ("align_top", align_top),
        ("align_middle_v", align_middle_v), ("align_bottom", align_bottom),
    ]:
        icons[name] = _icon_from_painter(fn)
    return icons


def _make_transform_icons():
    """Return a dict of action-name → QIcon for the flip / rotate buttons."""
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QPolygonF

    icons = {}
    line_c = QC("#cccccc")

    def _pen(color=line_c, w=1.4):
        pen = QPen(color, w)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def flip_h(p, s):
        mid = s / 2
        dp = QPen(QC("#666666"), 1.0)
        dp.setStyle(Qt.PenStyle.DashLine)
        p.setPen(dp)
        p.drawLine(QPointF(mid, 3), QPointF(mid, s - 3))
        p.setPen(_pen())
        p.drawLine(QPointF(mid - 3, mid), QPointF(3, mid))
        p.drawLine(QPointF(3, mid), QPointF(6, mid - 3))
        p.drawLine(QPointF(3, mid), QPointF(6, mid + 3))
        p.drawLine(QPointF(mid + 3, mid), QPointF(s - 3, mid))
        p.drawLine(QPointF(s - 3, mid), QPointF(s - 6, mid - 3))
        p.drawLine(QPointF(s - 3, mid), QPointF(s - 6, mid + 3))

    def flip_v(p, s):
        mid = s / 2
        dp = QPen(QC("#666666"), 1.0)
        dp.setStyle(Qt.PenStyle.DashLine)
        p.setPen(dp)
        p.drawLine(QPointF(3, mid), QPointF(s - 3, mid))
        p.setPen(_pen())
        p.drawLine(QPointF(mid, mid - 3), QPointF(mid, 3))
        p.drawLine(QPointF(mid, 3), QPointF(mid - 3, 6))
        p.drawLine(QPointF(mid, 3), QPointF(mid + 3, 6))
        p.drawLine(QPointF(mid, mid + 3), QPointF(mid, s - 3))
        p.drawLine(QPointF(mid, s - 3), QPointF(mid - 3, s - 6))
        p.drawLine(QPointF(mid, s - 3), QPointF(mid + 3, s - 6))

    def rotate_cw(p, s):
        arc_rect = QRectF(4, 4, s - 8, s - 8)
        p.setPen(_pen())
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(arc_rect, 90 * 16, -270 * 16)
        ex, ey = s / 2, s - 4
        p.drawLine(QPointF(ex, ey), QPointF(ex + 3, ey - 3))
        p.drawLine(QPointF(ex, ey), QPointF(ex - 2, ey - 3))

    def rotate_ccw(p, s):
        arc_rect = QRectF(4, 4, s - 8, s - 8)
        p.setPen(_pen())
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(arc_rect, 90 * 16, 270 * 16)
        ex, ey = s / 2, s - 4
        p.drawLine(QPointF(ex, ey), QPointF(ex - 3, ey - 3))
        p.drawLine(QPointF(ex, ey), QPointF(ex + 2, ey - 3))

    for name, fn in [
        ("flip_horizontal", flip_h), ("flip_vertical", flip_v),
        ("rotate_90_cw", rotate_cw), ("rotate_90_ccw", rotate_ccw),
    ]:
        icons[name] = _icon_from_painter(fn)
    return icons


class MovePropertiesBar(QWidget):
    """Horizontal bar with layer alignment buttons — clean, icon-only design."""

    align_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(1)

        icons = _make_align_icons()

        self._btns: list[QPushButton] = []
        for action in ("align_left", "align_center_h", "align_right"):
            self._btns.append(self._make_btn(icons[action], action))
            layout.addWidget(self._btns[-1])

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(18)
        sep.setStyleSheet(_MOVE_SEP_STYLE)
        layout.addWidget(sep)

        for action in ("align_top", "align_middle_v", "align_bottom"):
            self._btns.append(self._make_btn(icons[action], action))
            layout.addWidget(self._btns[-1])

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setFixedHeight(18)
        sep2.setStyleSheet(_MOVE_SEP_STYLE)
        layout.addWidget(sep2)

        t_icons = _make_transform_icons()
        _TIPS = {
            "flip_horizontal": "Flip Horizontal",
            "flip_vertical": "Flip Vertical",
            "rotate_90_cw": "Rotate 90° CW",
            "rotate_90_ccw": "Rotate 90° CCW",
        }
        for action in ("flip_horizontal", "flip_vertical", "rotate_90_cw", "rotate_90_ccw"):
            btn = QPushButton()
            btn.setIcon(t_icons[action])
            btn.setIconSize(QSize(20, 20))
            btn.setToolTip(_TIPS[action])
            btn.setStyleSheet(_MOVE_BTN_STYLE)
            btn.clicked.connect(lambda checked=False, a=action: self.align_requested.emit(a))
            self._btns.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

    def _make_btn(self, icon: QIcon, action: str) -> QPushButton:
        btn = QPushButton()
        btn.setIcon(icon)
        btn.setIconSize(QSize(20, 20))
        tip = action.replace("_", " ").title()
        if "center" in action:
            tip = "Align Center Horizontally"
        elif "middle" in action:
            tip = "Align Center Vertically"
        btn.setToolTip(tip)
        btn.setStyleSheet(_MOVE_BTN_STYLE)
        btn.clicked.connect(lambda checked=False, a=action: self.align_requested.emit(a))
        return btn
