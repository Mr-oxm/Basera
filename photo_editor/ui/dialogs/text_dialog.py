"""Text entry dialog for the text tool."""

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QLineEdit, QSpinBox, QTextEdit,
)


class TextDialog(QDialog):
    """Dialog for entering and configuring text layer content."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Text")
        self.setMinimumWidth(360)
        layout = QFormLayout(self)

        self._text = QTextEdit()
        self._text.setPlaceholderText("Enter text here…")
        self._text.setMaximumHeight(120)
        layout.addRow("Text:", self._text)

        self._font = QComboBox()
        self._font.setEditable(True)
        self._font.addItems(["Arial", "Helvetica", "Times New Roman", "Courier New", "Verdana"])
        layout.addRow("Font:", self._font)

        self._size = QSpinBox()
        self._size.setRange(6, 500)
        self._size.setValue(48)
        layout.addRow("Size:", self._size)

        self._align = QComboBox()
        self._align.addItems(["Left", "Center", "Right"])
        layout.addRow("Alignment:", self._align)

        self._spacing = QSpinBox()
        self._spacing.setRange(-50, 200)
        self._spacing.setValue(0)
        layout.addRow("Letter Spacing:", self._spacing)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_values(self) -> dict:
        return {
            "text": self._text.toPlainText(),
            "font_family": self._font.currentText(),
            "font_size": self._size.value(),
            "alignment": self._align.currentText().lower(),
            "spacing": self._spacing.value(),
        }
