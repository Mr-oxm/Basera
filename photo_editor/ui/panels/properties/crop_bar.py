"""Crop tool properties bar — mode, dimensions, Apply / Cancel."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QSpinBox, QWidget

from .base import ACCENT, COMBO, FLAT_BTN, LABEL, SPIN, make_separator


class CropPropertiesBar(QWidget):
    """Horizontal bar with crop-specific controls."""

    from PySide6.QtCore import Signal
    property_changed = Signal(str, object)
    apply_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        _spin_css = SPIN.format(max_w=70, accent=ACCENT)

        lbl = QLabel("Mode")
        lbl.setStyleSheet(LABEL)
        layout.addWidget(lbl)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Canvas Crop", "Layer Crop"])
        self._mode_combo.setMaximumHeight(24)
        self._mode_combo.setFixedWidth(110)
        self._mode_combo.setStyleSheet(COMBO.format(widget="QComboBox", accent=ACCENT))
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        layout.addWidget(self._mode_combo)

        layout.addWidget(make_separator())

        lbl_x = QLabel("X")
        lbl_x.setStyleSheet(LABEL)
        layout.addWidget(lbl_x)
        self._x_spin = QSpinBox()
        self._x_spin.setRange(0, 99999)
        self._x_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._x_spin.setReadOnly(True)
        self._x_spin.setMaximumWidth(55)
        self._x_spin.setMaximumHeight(22)
        self._x_spin.setStyleSheet(_spin_css)
        layout.addWidget(self._x_spin)

        lbl_y = QLabel("Y")
        lbl_y.setStyleSheet(LABEL)
        layout.addWidget(lbl_y)
        self._y_spin = QSpinBox()
        self._y_spin.setRange(0, 99999)
        self._y_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._y_spin.setReadOnly(True)
        self._y_spin.setMaximumWidth(55)
        self._y_spin.setMaximumHeight(22)
        self._y_spin.setStyleSheet(_spin_css)
        layout.addWidget(self._y_spin)

        lbl_w = QLabel("W")
        lbl_w.setStyleSheet(LABEL)
        layout.addWidget(lbl_w)
        self._w_spin = QSpinBox()
        self._w_spin.setRange(0, 99999)
        self._w_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._w_spin.setReadOnly(True)
        self._w_spin.setMaximumWidth(55)
        self._w_spin.setMaximumHeight(22)
        self._w_spin.setStyleSheet(_spin_css)
        layout.addWidget(self._w_spin)

        lbl_h = QLabel("H")
        lbl_h.setStyleSheet(LABEL)
        layout.addWidget(lbl_h)
        self._h_spin = QSpinBox()
        self._h_spin.setRange(0, 99999)
        self._h_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._h_spin.setReadOnly(True)
        self._h_spin.setMaximumWidth(55)
        self._h_spin.setMaximumHeight(22)
        self._h_spin.setStyleSheet(_spin_css)
        layout.addWidget(self._h_spin)

        layout.addWidget(make_separator())

        self._apply_btn = QPushButton("✓ Apply")
        self._apply_btn.setFixedHeight(24)
        self._apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_btn.setStyleSheet(
            FLAT_BTN.format() + """
            QPushButton { color: #88cc88; font-weight: bold; }
            QPushButton:hover { color: #aaffaa; }
        """)
        self._apply_btn.clicked.connect(self.apply_requested.emit)
        layout.addWidget(self._apply_btn)

        self._cancel_btn = QPushButton("✗ Cancel")
        self._cancel_btn.setFixedHeight(24)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setStyleSheet(
            FLAT_BTN.format() + """
            QPushButton { color: #cc8888; }
            QPushButton:hover { color: #ffaaaa; }
        """)
        self._cancel_btn.clicked.connect(self.cancel_requested.emit)
        layout.addWidget(self._cancel_btn)

        layout.addStretch()

    def _on_mode_changed(self, index: int) -> None:
        mode_name = "canvas" if index == 0 else "layer"
        self.property_changed.emit("crop_mode", mode_name)

    def set_dimensions(self, x: int, y: int, w: int, h: int) -> None:
        self._x_spin.setValue(x)
        self._y_spin.setValue(y)
        self._w_spin.setValue(w)
        self._h_spin.setValue(h)

    def clear_dimensions(self) -> None:
        for sp in (self._x_spin, self._y_spin, self._w_spin, self._h_spin):
            sp.setValue(0)

    def sync_from_tool(self, tool) -> None:
        self.blockSignals(True)
        try:
            from ....tools.crop_tool import CropMode
            idx = 0 if tool.mode == CropMode.CANVAS else 1
            self._mode_combo.setCurrentIndex(idx)
            if tool.box is not None:
                self.set_dimensions(*tool.box)
            else:
                self.clear_dimensions()
        finally:
            self.blockSignals(False)
