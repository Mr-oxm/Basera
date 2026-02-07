"""Adjustments panel — quick access to non-destructive adjustment layers."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QPushButton, QWidget

_ADJUSTMENTS = [
    "Brightness/Contrast", "Levels", "Curves", "Exposure",
    "Vibrance", "Hue/Saturation", "Color Balance", "Black & White",
    "Photo Filter", "Gradient Map", "Selective Color", "Channel Mixer",
    "Invert", "Posterize", "Threshold",
]


class AdjustmentsPanel(QWidget):
    """Grid of buttons for adding adjustment layers."""

    adjustment_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QGridLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        for i, name in enumerate(_ADJUSTMENTS):
            btn = QPushButton(name)
            btn.setToolTip(f"Add {name} adjustment layer")
            btn.clicked.connect(lambda checked, n=name: self.adjustment_requested.emit(n))
            layout.addWidget(btn, i // 3, i % 3)
