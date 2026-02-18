"""Gradient tool properties bar — type, opacity, reverse."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QSpinBox, QWidget

from ...widgets.color_dropdown import ColorDropdown
from .base import ACCENT, COMBO, FLAT_BTN, LABEL, SPIN, make_separator


class GradientPropertiesBar(QWidget):
    """Horizontal bar with gradient-specific controls."""

    from PySide6.QtCore import Signal
    property_changed = Signal(str, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        self._color_dropdown = ColorDropdown(
            label="Gradient:",
            show_gradient=True,
            show_wheel=True,
            default_tab=2,
        )
        self._color_dropdown.gradient_changed.connect(self._on_gradient_pick)
        layout.addWidget(self._color_dropdown)

        layout.addWidget(make_separator())

        lbl = QLabel("Type")
        lbl.setStyleSheet(LABEL)
        layout.addWidget(lbl)

        self._type_combo = QComboBox()
        self._type_combo.addItems(["Linear", "Radial", "Conical", "Diamond"])
        self._type_combo.setMaximumHeight(24)
        self._type_combo.setFixedWidth(90)
        self._type_combo.setStyleSheet(COMBO.format(widget="QComboBox", accent=ACCENT))
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        layout.addWidget(self._type_combo)

        layout.addWidget(make_separator())

        lbl2 = QLabel("Opacity")
        lbl2.setStyleSheet(LABEL)
        layout.addWidget(lbl2)

        self._opacity_spin = QSpinBox()
        self._opacity_spin.setRange(0, 100)
        self._opacity_spin.setValue(100)
        self._opacity_spin.setSuffix("%")
        self._opacity_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._opacity_spin.setMaximumWidth(60)
        self._opacity_spin.setMaximumHeight(22)
        self._opacity_spin.setStyleSheet(SPIN.format(max_w=60, accent=ACCENT))
        self._opacity_spin.valueChanged.connect(self._on_opacity_changed)
        layout.addWidget(self._opacity_spin)

        layout.addWidget(make_separator())

        self._rev_btn = QPushButton("\u27F3 Reverse")
        self._rev_btn.setFixedHeight(24)
        self._rev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rev_btn.setStyleSheet(FLAT_BTN.format())
        self._rev_btn.clicked.connect(self._on_reverse)
        layout.addWidget(self._rev_btn)

        layout.addStretch()

    def _on_gradient_pick(self, fill) -> None:
        self.property_changed.emit("gradient_fill", fill)

    def _on_type_changed(self, text: str) -> None:
        self.property_changed.emit("gradient_type", text.lower())

    def _on_opacity_changed(self, val: int) -> None:
        self.property_changed.emit("opacity", val / 100.0)

    def _on_reverse(self) -> None:
        self.property_changed.emit("reverse", True)

    def sync_from_tool(self, tool) -> None:
        self.blockSignals(True)
        try:
            if hasattr(tool, "gradient_type"):
                idx = {"linear": 0, "radial": 1, "conical": 2, "diamond": 3}.get(
                    tool.gradient_type, 0
                )
                self._type_combo.setCurrentIndex(idx)
            if hasattr(tool, "opacity"):
                self._opacity_spin.setValue(int(tool.opacity * 100))
        finally:
            self.blockSignals(False)
