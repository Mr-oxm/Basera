"""History panel showing undo / redo state list."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QListWidget, QVBoxLayout, QWidget

from ...core.history import HistoryManager


class HistoryPanel(QWidget):
    """Shows the list of history states and allows jumping to a state."""

    state_selected = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self.state_selected.emit)
        layout.addWidget(self._list)

    def refresh(self, history: HistoryManager) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for name in history.names():
            self._list.addItem(name)
        if 0 <= history.current_index < self._list.count():
            self._list.setCurrentRow(history.current_index)
        self._list.blockSignals(False)
