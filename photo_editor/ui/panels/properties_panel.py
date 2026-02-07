"""Properties panel — shows editable parameters for the active layer / tool."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox, QFormLayout, QLabel, QSlider, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt


class PropertiesPanel(QWidget):
    """Dynamic property editor for the current context."""

    value_changed = Signal(str, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._title = QLabel("Properties")
        self._title.setStyleSheet("font-weight: bold;")
        self._layout.addWidget(self._title)
        self._form = QFormLayout()
        self._layout.addLayout(self._form)
        self._layout.addStretch()
        self._widgets: dict[str, QWidget] = {}

    def clear(self) -> None:
        while self._form.rowCount() > 0:
            self._form.removeRow(0)
        self._widgets.clear()
        self._title.setText("Properties")

    def set_title(self, title: str) -> None:
        self._title.setText(title)

    def add_slider(
        self, key: str, label: str, value: int = 0,
        min_val: int = 0, max_val: int = 100,
    ) -> None:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(value)
        slider.valueChanged.connect(lambda v, k=key: self.value_changed.emit(k, v))
        self._form.addRow(label, slider)
        self._widgets[key] = slider

    def add_spinbox(
        self, key: str, label: str, value: float = 0.0,
        min_val: float = -999.0, max_val: float = 999.0, step: float = 0.1,
    ) -> None:
        spin = QDoubleSpinBox()
        spin.setRange(min_val, max_val)
        spin.setSingleStep(step)
        spin.setValue(value)
        spin.valueChanged.connect(lambda v, k=key: self.value_changed.emit(k, v))
        self._form.addRow(label, spin)
        self._widgets[key] = spin

    def set_value(self, key: str, value: object) -> None:
        w = self._widgets.get(key)
        if w and hasattr(w, "setValue"):
            w.blockSignals(True)
            w.setValue(value)
            w.blockSignals(False)
