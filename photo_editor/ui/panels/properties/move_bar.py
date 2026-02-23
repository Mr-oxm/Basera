"""Move tool properties bar — alignment and transform buttons."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPen, QColor as QC
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QWidget

from .base import _icon_from_painter, make_separator

_MOVE_BTN_STYLE = """
    QPushButton {
        background: transparent; border: 1px solid transparent; border-radius: 4px;
        padding: 3px; min-width: 26px; min-height: 26px;
        max-width: 26px; max-height: 26px;
    }
    QPushButton:hover { 
        background: rgba(255,255,255,0.05); 
        border: 1px solid rgba(255,255,255,0.1); 
    }
    QPushButton:pressed { 
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(110,180,255,0.25), stop:1 rgba(110,180,255,0.1));
        border: 1px solid rgba(110,180,255,0.4); 
    }
"""

_MOVE_SEP_STYLE = """
    QFrame {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255,255,255,0), stop:0.5 rgba(255,255,255,0.08), stop:1 rgba(255,255,255,0));
        max-width: 1px; margin: 4px 2px; border: none;
    }
"""


def _make_align_icons():
    """Return a dict of action-name → QIcon for the alignment buttons."""
    from PySide6.QtCore import QRectF, QPointF

    icons = {}
    _C_MAIN = QC(230, 230, 240)
    _C_ACCENT = QC(110, 180, 255)
    _SHADOW = QC(0, 0, 0, 80)

    def _pen(color, w=1.5):
        pen = QPen(color, w)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        return pen

    def align_left(p, s):
        p.setPen(_pen(_SHADOW, 2))
        p.drawLine(5, 4, 5, s - 2)
        p.setBrush(_SHADOW)
        p.drawRoundedRect(QRectF(7, 6, 10, 3,), 1, 1)
        p.drawRoundedRect(QRectF(7, 13, 7, 3), 1, 1)
        
        p.setPen(_pen(_C_MAIN, 1.5))
        p.drawLine(4, 3, 4, s - 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_C_ACCENT)
        p.drawRoundedRect(QRectF(6, 5, 10, 3), 1, 1)
        p.setBrush(_C_MAIN)
        p.drawRoundedRect(QRectF(6, 12, 7, 3), 1, 1)

    def align_center_h(p, s):
        cx = s / 2
        p.setPen(_pen(_SHADOW, 2))
        p.drawLine(int(cx)+1, 4, int(cx)+1, s - 2)
        p.setBrush(_SHADOW)
        p.drawRoundedRect(QRectF(cx - 4, 6, 10, 3), 1, 1)
        p.drawRoundedRect(QRectF(cx - 2.5, 13, 7, 3), 1, 1)
        
        p.setPen(_pen(_C_MAIN, 1.5))
        p.drawLine(int(cx), 3, int(cx), s - 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_C_ACCENT)
        p.drawRoundedRect(QRectF(cx - 5, 5, 10, 3), 1, 1)
        p.setBrush(_C_MAIN)
        p.drawRoundedRect(QRectF(cx - 3.5, 12, 7, 3), 1, 1)

    def align_right(p, s):
        p.setPen(_pen(_SHADOW, 2))
        p.drawLine(s - 3, 4, s - 3, s - 2)
        p.setBrush(_SHADOW)
        p.drawRoundedRect(QRectF(s - 13, 6, 10, 3), 1, 1)
        p.drawRoundedRect(QRectF(s - 10, 13, 7, 3), 1, 1)
        
        p.setPen(_pen(_C_MAIN, 1.5))
        p.drawLine(s - 4, 3, s - 4, s - 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_C_ACCENT)
        p.drawRoundedRect(QRectF(s - 14, 5, 10, 3), 1, 1)
        p.setBrush(_C_MAIN)
        p.drawRoundedRect(QRectF(s - 11, 12, 7, 3), 1, 1)

    def align_top(p, s):
        p.setPen(_pen(_SHADOW, 2))
        p.drawLine(4, 5, s - 2, 5)
        p.setBrush(_SHADOW)
        p.drawRoundedRect(QRectF(6, 7, 3, 10), 1, 1)
        p.drawRoundedRect(QRectF(13, 7, 3, 7), 1, 1)
        
        p.setPen(_pen(_C_MAIN, 1.5))
        p.drawLine(3, 4, s - 3, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_C_ACCENT)
        p.drawRoundedRect(QRectF(5, 6, 3, 10), 1, 1)
        p.setBrush(_C_MAIN)
        p.drawRoundedRect(QRectF(12, 6, 3, 7), 1, 1)

    def align_middle_v(p, s):
        cy = s / 2
        p.setPen(_pen(_SHADOW, 2))
        p.drawLine(4, int(cy)+1, s - 2, int(cy)+1)
        p.setBrush(_SHADOW)
        p.drawRoundedRect(QRectF(6, cy - 4, 3, 10), 1, 1)
        p.drawRoundedRect(QRectF(13, cy - 2.5, 3, 7), 1, 1)
        
        p.setPen(_pen(_C_MAIN, 1.5))
        p.drawLine(3, int(cy), s - 3, int(cy))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_C_ACCENT)
        p.drawRoundedRect(QRectF(5, cy - 5, 3, 10), 1, 1)
        p.setBrush(_C_MAIN)
        p.drawRoundedRect(QRectF(12, cy - 3.5, 3, 7), 1, 1)

    def align_bottom(p, s):
        p.setPen(_pen(_SHADOW, 2))
        p.drawLine(4, s - 3, s - 2, s - 3)
        p.setBrush(_SHADOW)
        p.drawRoundedRect(QRectF(6, s - 13, 3, 10), 1, 1)
        p.drawRoundedRect(QRectF(13, s - 10, 3, 7), 1, 1)
        
        p.setPen(_pen(_C_MAIN, 1.5))
        p.drawLine(3, s - 4, s - 3, s - 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_C_ACCENT)
        p.drawRoundedRect(QRectF(5, s - 14, 3, 10), 1, 1)
        p.setBrush(_C_MAIN)
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
    _C_MAIN = QC(230, 230, 240)
    _C_ACCENT = QC(110, 180, 255)
    _SHADOW = QC(0, 0, 0, 80)

    def _pen(color=_C_MAIN, w=1.4):
        pen = QPen(color, w)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def flip_h(p, s):
        mid = s / 2
        dp = QPen(_SHADOW, 1.5)
        dp.setStyle(Qt.PenStyle.DashLine)
        p.setPen(dp)
        p.drawLine(QPointF(mid+1, 4), QPointF(mid+1, s - 2))
        
        dp = QPen(QC("#b0b4b8"), 1.0)
        dp.setStyle(Qt.PenStyle.DashLine)
        p.setPen(dp)
        p.drawLine(QPointF(mid, 3), QPointF(mid, s - 3))
        
        p.setPen(_pen(_SHADOW, 2))
        p.drawLine(QPointF(mid - 2, mid+1), QPointF(4, mid+1))
        p.drawLine(QPointF(4, mid+1), QPointF(7, mid - 2))
        p.drawLine(QPointF(4, mid+1), QPointF(7, mid + 4))
        p.drawLine(QPointF(mid + 4, mid+1), QPointF(s - 2, mid+1))
        p.drawLine(QPointF(s - 2, mid+1), QPointF(s - 5, mid - 2))
        p.drawLine(QPointF(s - 2, mid+1), QPointF(s - 5, mid + 4))
        
        p.setPen(_pen(_C_MAIN))
        p.drawLine(QPointF(mid - 3, mid), QPointF(3, mid))
        p.drawLine(QPointF(3, mid), QPointF(6, mid - 3))
        p.drawLine(QPointF(3, mid), QPointF(6, mid + 3))
        p.setPen(_pen(_C_ACCENT))
        p.drawLine(QPointF(mid + 3, mid), QPointF(s - 3, mid))
        p.drawLine(QPointF(s - 3, mid), QPointF(s - 6, mid - 3))
        p.drawLine(QPointF(s - 3, mid), QPointF(s - 6, mid + 3))

    def flip_v(p, s):
        mid = s / 2
        dp = QPen(_SHADOW, 1.5)
        dp.setStyle(Qt.PenStyle.DashLine)
        p.setPen(dp)
        p.drawLine(QPointF(4, mid+1), QPointF(s - 2, mid+1))
        
        dp = QPen(QC("#b0b4b8"), 1.0)
        dp.setStyle(Qt.PenStyle.DashLine)
        p.setPen(dp)
        p.drawLine(QPointF(3, mid), QPointF(s - 3, mid))
        
        p.setPen(_pen(_SHADOW, 2))
        p.drawLine(QPointF(mid+1, mid - 2), QPointF(mid+1, 4))
        p.drawLine(QPointF(mid+1, 4), QPointF(mid - 2, 7))
        p.drawLine(QPointF(mid+1, 4), QPointF(mid + 4, 7))
        p.drawLine(QPointF(mid+1, mid + 4), QPointF(mid+1, s - 2))
        p.drawLine(QPointF(mid+1, s - 2), QPointF(mid - 2, s - 5))
        p.drawLine(QPointF(mid+1, s - 2), QPointF(mid + 4, s - 5))
        
        p.setPen(_pen(_C_MAIN))
        p.drawLine(QPointF(mid, mid - 3), QPointF(mid, 3))
        p.drawLine(QPointF(mid, 3), QPointF(mid - 3, 6))
        p.drawLine(QPointF(mid, 3), QPointF(mid + 3, 6))
        p.setPen(_pen(_C_ACCENT))
        p.drawLine(QPointF(mid, mid + 3), QPointF(mid, s - 3))
        p.drawLine(QPointF(mid, s - 3), QPointF(mid - 3, s - 6))
        p.drawLine(QPointF(mid, s - 3), QPointF(mid + 3, s - 6))

    def rotate_cw(p, s):
        arc_rect = QRectF(5, 5, s - 10, s - 10)
        
        p.setPen(_pen(_SHADOW, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(arc_rect.translated(1, 1), -90 * 16, -270 * 16)
        ex, ey = s - 5 + 1, s / 2 + 1
        p.drawLine(QPointF(ex, ey), QPointF(ex - 3, ey - 3))
        p.drawLine(QPointF(ex, ey), QPointF(ex + 3, ey - 3))
        
        p.setPen(_pen(_C_MAIN, 1.5))
        p.drawArc(arc_rect, -90 * 16, -270 * 16)
        p.setPen(_pen(_C_ACCENT, 1.5))
        ex, ey = s - 5, s / 2
        p.drawLine(QPointF(ex, ey), QPointF(ex - 3, ey - 3))
        p.drawLine(QPointF(ex, ey), QPointF(ex + 3, ey - 3))

    def rotate_ccw(p, s):
        arc_rect = QRectF(5, 5, s - 10, s - 10)
        
        p.setPen(_pen(_SHADOW, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(arc_rect.translated(1, 1), -90 * 16, 270 * 16)
        ex, ey = 5 + 1, s / 2 + 1
        p.drawLine(QPointF(ex, ey), QPointF(ex - 3, ey - 3))
        p.drawLine(QPointF(ex, ey), QPointF(ex + 3, ey - 3))
        
        p.setPen(_pen(_C_MAIN, 1.5))
        p.drawArc(arc_rect, -90 * 16, 270 * 16)
        p.setPen(_pen(_C_ACCENT, 1.5))
        ex, ey = 5, s / 2
        p.drawLine(QPointF(ex, ey), QPointF(ex - 3, ey - 3))
        p.drawLine(QPointF(ex, ey), QPointF(ex + 3, ey - 3))

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
