"""Blend mode combo with hover preview."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QComboBox


class BlendModeCombo(QComboBox):
    hover_preview = Signal(object)
    hover_ended = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._orig_idx: int = -1
        self._popup_open = False
        self.highlighted.connect(self._on_highlighted)

    def showPopup(self) -> None:
        self._orig_idx = self.currentIndex()
        self._popup_open = True
        super().showPopup()

    def hidePopup(self) -> None:
        self._popup_open = False
        super().hidePopup()
        QTimer.singleShot(0, self._on_popup_closed)

    def _on_highlighted(self, index: int) -> None:
        if self._popup_open:
            mode = self.itemData(index)
            if mode is not None:
                self.hover_preview.emit(mode)

    def _on_popup_closed(self) -> None:
        if self.currentIndex() == self._orig_idx:
            self.hover_ended.emit()
