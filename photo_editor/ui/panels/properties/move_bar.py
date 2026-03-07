"""Move tool properties bar — alignment and transform buttons."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QWidget

from ...icons import move_align_icons, move_transform_icons

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


class MovePropertiesBar(QWidget):
    """Horizontal bar with layer alignment buttons — clean, icon-only design."""

    align_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(1)

        icons = move_align_icons()

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

        t_icons = move_transform_icons()
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

        from ...theme import ThemeManager
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _apply_theme(self, palette: dict) -> None:
        a_icons = move_align_icons()
        t_icons = move_transform_icons()
        
        actions = (
            "align_left", "align_center_h", "align_right",
            "align_top", "align_middle_v", "align_bottom",
            "flip_horizontal", "flip_vertical", "rotate_90_cw", "rotate_90_ccw"
        )
        for i, action in enumerate(actions):
            if i < 6:
                self._btns[i].setIcon(a_icons[action])
            else:
                self._btns[i].setIcon(t_icons[action])

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
