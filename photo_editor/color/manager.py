"""ColorManager singleton — global foreground/background state."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ..core.color import Color, ColorFill, SolidFill
from .conversions import hsv_to_rgb
from .swatches import SwatchPalette


class ColorManager(QObject):
    """Application-wide foreground/background colour state with history.

    Connect to the signals to react when the user picks a new colour.
    Access the singleton via ``ColorManager.instance()``.
    """

    foreground_changed = Signal(object)  # Color
    background_changed = Signal(object)  # Color
    active_fill_changed = Signal(object)  # ColorFill
    history_changed = Signal()

    _instance: ColorManager | None = None

    @classmethod
    def instance(cls) -> ColorManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._fg: Color = Color.black()
        self._bg: Color = Color.white()
        self._active_fill: ColorFill = SolidFill(color=Color.black())
        self._history: list[Color] = []
        self._max_history = 32
        self._palette = SwatchPalette.default_palette()

    @property
    def foreground(self) -> Color:
        return self._fg

    @foreground.setter
    def foreground(self, c: Color) -> None:
        if c != self._fg:
            self._fg = c
            self._push_history(c)
            self._active_fill = SolidFill(color=c)
            self.foreground_changed.emit(c)
            self.active_fill_changed.emit(self._active_fill)

    def set_foreground_preview(self, c: Color) -> None:
        """Update foreground visually without recording to history."""
        if c != self._fg:
            self._fg = c
            self._active_fill = SolidFill(color=c)
            self.foreground_changed.emit(c)
            self.active_fill_changed.emit(self._active_fill)

    def commit_foreground(self) -> None:
        """Record the current foreground to history (call after drag ends)."""
        self._push_history(self._fg)

    def set_background_preview(self, c: Color) -> None:
        """Update background visually without recording to history."""
        if c != self._bg:
            self._bg = c
            self.background_changed.emit(c)

    def commit_background(self) -> None:
        """Record the current background to history (call after drag ends)."""
        self._push_history(self._bg)

    @property
    def background(self) -> Color:
        return self._bg

    @background.setter
    def background(self, c: Color) -> None:
        if c != self._bg:
            self._bg = c
            self._push_history(c)
            self.background_changed.emit(c)

    @property
    def active_fill(self) -> ColorFill:
        return self._active_fill

    @active_fill.setter
    def active_fill(self, fill: ColorFill) -> None:
        self._active_fill = fill
        self.active_fill_changed.emit(fill)

    @property
    def history(self) -> list[Color]:
        return list(self._history)

    @property
    def palette(self) -> SwatchPalette:
        return self._palette

    @palette.setter
    def palette(self, p: SwatchPalette) -> None:
        self._palette = p

    def swap(self) -> None:
        self._fg, self._bg = self._bg, self._fg
        self.foreground_changed.emit(self._fg)
        self.background_changed.emit(self._bg)

    def reset(self) -> None:
        self._fg = Color.black()
        self._bg = Color.white()
        self.foreground_changed.emit(self._fg)
        self.background_changed.emit(self._bg)

    def set_foreground_hsv(self, h: float, s: float, v: float, a: float = 1.0) -> None:
        r, g, b = hsv_to_rgb(h, s, v)
        self.foreground = Color(r, g, b, a)

    def set_foreground_hex(self, hex_str: str) -> None:
        self.foreground = Color.from_hex(hex_str)

    def _push_history(self, c: Color) -> None:
        if self._history and self._history[0] == c:
            return
        self._history.insert(0, c)
        if len(self._history) > self._max_history:
            self._history = self._history[: self._max_history]
        self.history_changed.emit()
