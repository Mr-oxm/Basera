"""New Document dialog."""

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QSpinBox,
)


class NewDocumentDialog(QDialog):
    """Dialog for creating a new document with specified dimensions."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Document")
        self.setMinimumWidth(320)

        layout = QFormLayout(self)

        self._width = QSpinBox()
        self._width.setRange(1, 30000)
        self._width.setValue(1920)
        layout.addRow("Width:", self._width)

        self._height = QSpinBox()
        self._height.setRange(1, 30000)
        self._height.setValue(1080)
        layout.addRow("Height:", self._height)

        self._dpi = QSpinBox()
        self._dpi.setRange(1, 1200)
        self._dpi.setValue(72)
        layout.addRow("DPI:", self._dpi)

        self._preset = QComboBox()
        presets = [
            ("Custom", 0, 0),
            ("1920 × 1080 (Full HD)", 1920, 1080),
            ("3840 × 2160 (4K)", 3840, 2160),
            ("1080 × 1080 (Instagram)", 1080, 1080),
            ("2480 × 3508 (A4 @ 300 dpi)", 2480, 3508),
        ]
        for label, w, h in presets:
            self._preset.addItem(label, (w, h))
        self._preset.currentIndexChanged.connect(self._on_preset)
        layout.addRow("Preset:", self._preset)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_preset(self, idx: int) -> None:
        w, h = self._preset.itemData(idx)
        if w and h:
            self._width.setValue(w)
            self._height.setValue(h)

    def get_values(self) -> tuple[int, int, int]:
        return self._width.value(), self._height.value(), self._dpi.value()
