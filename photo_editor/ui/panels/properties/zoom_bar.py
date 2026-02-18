"""Zoom tool properties bar — Zoom In, Zoom Out, Fit, 100%."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

_ZOOM_BTN_STYLE = """
    QPushButton {
        background: transparent;
        border: none;
        border-radius: 4px;
        padding: 3px;
        min-width: 60px; min-height: 26px; max-height: 26px;
        font-size: 11px; color: #ccc;
    }
    QPushButton:hover { background-color: rgba(255, 255, 255, 0.08); }
    QPushButton:pressed { background-color: rgba(74, 111, 165, 0.5); }
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
