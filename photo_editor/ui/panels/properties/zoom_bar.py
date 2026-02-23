"""Zoom tool properties bar — Zoom In, Zoom Out, Fit, 100%."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

_ZOOM_BTN_STYLE = """
    QPushButton {
        background: transparent; border: 1px solid transparent; border-radius: 4px;
        padding: 3px; font-weight: 500; min-width: 60px; min-height: 26px; max-height: 26px;
        font-size: 11px; color: #b0b4b8;
    }
    QPushButton:hover { 
        background: rgba(255,255,255,0.05); color: #e0e4e8; 
        border: 1px solid rgba(255,255,255,0.1); 
    }
    QPushButton:pressed { 
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(110,180,255,0.25), stop:1 rgba(110,180,255,0.1));
        border: 1px solid rgba(110,180,255,0.4); 
        color: #ffffff; 
    }
"""


class ZoomPropertiesBar(QWidget):
    """Horizontal bar with zoom controls: Zoom In, Zoom Out, Fit, 100%."""

    from PySide6.QtCore import Signal
    zoom_action = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(4)

        _items = [
            ("zoom_in", "Zoom In", "+"),
            ("zoom_out", "Zoom Out", "\u2212"),
            ("fit", "Fit to Screen", "Fit"),
            ("reset", "100%", "100%"),
        ]
        for action, tip, label in _items:
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.setStyleSheet(_ZOOM_BTN_STYLE)
            btn.clicked.connect(lambda _=False, a=action: self.zoom_action.emit(a))
            layout.addWidget(btn)

        layout.addStretch()
