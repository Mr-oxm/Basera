"""Adjustments panel — quick access to non-destructive adjustment layers."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..styles import render_qss
from ..theme import ThemeManager

_ADJUSTMENTS = [
    "Brightness/Contrast", "Levels", "Curves", "Exposure",
    "Vibrance", "Hue/Saturation", "White Balance", "Color Balance", "Recolor",
    "Split Toning", "Normals", "Black & White",
    "Photo Filter", "Gradient Map", "Selective Color", "Channel Mixer",
    "Invert", "Posterize", "Threshold",
]


class AdjustmentsPanel(QWidget):
    """Grid of buttons for adding adjustment layers."""

    adjustment_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("AdjustmentsPanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        title = QLabel("Adjustment layers")
        title.setObjectName("adjustmentsTitle")
        root.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)

        for i, name in enumerate(_ADJUSTMENTS):
            btn = QPushButton(name)
            btn.setObjectName("adjustmentTile")
            btn.setToolTip(f"Add {name} adjustment layer")
            btn.clicked.connect(lambda checked, n=name: self.adjustment_requested.emit(n))
            grid.addWidget(btn, i // 2, i % 2)

        root.addLayout(grid)
        root.addStretch()

        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._apply_theme(ThemeManager.instance().active_palette)

    def _apply_theme(self, palette: dict) -> None:
        self.setStyleSheet(render_qss("adjustments_panel.qss", palette))
