"""New Document / Canvas Size dialog — compact dimension editor with unit conversion."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QDoubleSpinBox,
)

from .new_project_dialog import UNITS, px_per_unit, _spinbox_config


class NewDocumentDialog(QDialog):
    """Compact dialog for specifying a canvas size with unit conversion.

    Public attributes kept for backward compatibility with ``layer_ctrl.py``:
        ``_width``, ``_height`` — QDoubleSpinBox displaying values in the
        currently selected unit.  ``get_values()`` always returns pixels.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Document")
        self.setMinimumWidth(340)

        self._current_unit = "px"
        self._current_dpi = 72

        layout = QFormLayout(self)

        # Width / height — named _width/_height for backward compatibility
        self._width = QDoubleSpinBox()
        self._width.setDecimals(0)
        self._width.setRange(1, 30000)
        self._width.setValue(1920)
        self._width.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
        layout.addRow("Width:", self._width)

        self._height = QDoubleSpinBox()
        self._height.setDecimals(0)
        self._height.setRange(1, 30000)
        self._height.setValue(1080)
        self._height.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
        layout.addRow("Height:", self._height)

        self._dpi = QDoubleSpinBox()
        self._dpi.setDecimals(0)
        self._dpi.setRange(1, 1200)
        self._dpi.setValue(72)
        self._dpi.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
        self._dpi.valueChanged.connect(self._on_dpi_changed)
        layout.addRow("DPI:", self._dpi)

        self._units_combo = QComboBox()
        self._units_combo.addItems(UNITS)
        self._units_combo.currentIndexChanged.connect(self._on_unit_changed)
        layout.addRow("Units:", self._units_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self._suppress = False

    # ---- Unit / DPI handling ------------------------------------------------

    def _on_unit_changed(self, idx: int) -> None:
        new_unit = UNITS[idx]
        if new_unit == self._current_unit:
            return
        dpi = int(self._dpi.value())
        old_ppu = px_per_unit(self._current_unit, dpi)
        new_ppu = px_per_unit(new_unit, dpi)
        w_px = self._width.value() * old_ppu
        h_px = self._height.value() * old_ppu

        self._current_unit = new_unit
        mn, mx, dec, step = _spinbox_config(new_unit)
        self._suppress = True
        for spin in (self._width, self._height):
            spin.setDecimals(dec)
            spin.setSingleStep(step)
            spin.setRange(mn, mx)
        self._width.setValue(w_px / new_ppu)
        self._height.setValue(h_px / new_ppu)
        self._suppress = False

    def _on_dpi_changed(self, _val: float) -> None:
        if self._suppress or self._current_unit == "px":
            return
        new_dpi = max(1, int(self._dpi.value()))
        if new_dpi == self._current_dpi:
            return
        # Physical size is preserved; pixel count changes automatically via get_values()
        self._current_dpi = new_dpi

    # ---- Public API ---------------------------------------------------------

    def get_values(self) -> tuple[int, int, int]:
        """Return (width_px, height_px, dpi)."""
        dpi = max(1, int(self._dpi.value()))
        ppu = px_per_unit(self._current_unit, dpi)
        w = max(1, round(self._width.value() * ppu))
        h = max(1, round(self._height.value() * ppu))
        return w, h, dpi
