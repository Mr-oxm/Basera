"""Status bar showing document info, zoom level, cursor position."""

from PySide6.QtWidgets import QStatusBar, QLabel


class EditorStatusBar(QStatusBar):
    """Bottom status bar with contextual information."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._doc_label = QLabel("No document")
        self._zoom_label = QLabel("100%")
        self._pos_label = QLabel("x: 0  y: 0")
        self._size_label = QLabel("")
        self._tool_label = QLabel("")

        for lbl in (self._doc_label, self._size_label, self._tool_label):
            self.addWidget(lbl)
        self.addPermanentWidget(self._pos_label)
        self.addPermanentWidget(self._zoom_label)

    def set_document_info(self, name: str, width: int, height: int) -> None:
        self._doc_label.setText(name)
        self._size_label.setText(f"{width} × {height} px")

    def set_zoom(self, zoom: float) -> None:
        self._zoom_label.setText(f"{zoom * 100:.0f}%")

    def set_cursor_pos(self, x: int, y: int) -> None:
        self._pos_label.setText(f"x: {x}  y: {y}")

    def set_tool(self, name: str) -> None:
        self._tool_label.setText(name)
