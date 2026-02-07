"""Color picker panel with foreground / background swatches."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog, QHBoxLayout, QPushButton, QVBoxLayout, QWidget,
)

from ...core.color import Color


class ColorPanel(QWidget):
    """Foreground / background colour selector."""

    fg_changed = Signal(Color)
    bg_changed = Signal(Color)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._fg = Color.black()
        self._bg = Color.white()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        row = QHBoxLayout()
        self._fg_btn = QPushButton()
        self._fg_btn.setFixedSize(40, 40)
        self._fg_btn.clicked.connect(self._pick_fg)
        self._bg_btn = QPushButton()
        self._bg_btn.setFixedSize(40, 40)
        self._bg_btn.clicked.connect(self._pick_bg)
        row.addWidget(self._fg_btn)
        row.addWidget(self._bg_btn)
        row.addStretch()
        layout.addWidget(_label("Foreground / Background"))
        layout.addLayout(row)

        swap = QPushButton("⇄ Swap (X)")
        swap.clicked.connect(self._swap)
        layout.addWidget(swap)

        reset = QPushButton("Reset (D)")
        reset.clicked.connect(self._reset)
        layout.addWidget(reset)
        layout.addStretch()

        self._update_buttons()

    @property
    def foreground(self) -> Color:
        return self._fg

    @property
    def background(self) -> Color:
        return self._bg

    def _pick_fg(self) -> None:
        c = self._pick(self._fg)
        if c:
            self._fg = c
            self._update_buttons()
            self.fg_changed.emit(c)

    def _pick_bg(self) -> None:
        c = self._pick(self._bg)
        if c:
            self._bg = c
            self._update_buttons()
            self.bg_changed.emit(c)

    def _swap(self) -> None:
        self._fg, self._bg = self._bg, self._fg
        self._update_buttons()
        self.fg_changed.emit(self._fg)
        self.bg_changed.emit(self._bg)

    def _reset(self) -> None:
        self._fg, self._bg = Color.black(), Color.white()
        self._update_buttons()
        self.fg_changed.emit(self._fg)
        self.bg_changed.emit(self._bg)

    def _update_buttons(self) -> None:
        self._fg_btn.setStyleSheet(f"background-color: {self._fg.to_hex()}; border: 2px solid #888;")
        self._bg_btn.setStyleSheet(f"background-color: {self._bg.to_hex()}; border: 2px solid #888;")

    @staticmethod
    def _pick(current: Color) -> Color | None:
        r, g, b, a = current.to_rgb8()
        c = QColorDialog.getColor(QColor(r, g, b, a))
        if c.isValid():
            return Color.from_rgb8(c.red(), c.green(), c.blue(), c.alpha())
        return None


def _label(text: str):
    from PySide6.QtWidgets import QLabel
    lbl = QLabel(text)
    lbl.setStyleSheet("font-weight: bold; margin-bottom: 2px;")
    return lbl
