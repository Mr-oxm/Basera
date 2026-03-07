"""Foreground/background color from Color panel."""

from __future__ import annotations

from .base import ControllerBase


class ColorController(ControllerBase):
    """Handles foreground color changes from the Color panel."""

    def __init__(self) -> None:
        super().__init__()

    def wire(self, main_window) -> None:
        """Connect to main window and wire panel signals."""
        super().wire(main_window)
        main_window._color_panel.fg_changed.connect(self.on_fg_color_changed)

    def on_fg_color_changed(self, color) -> None:
        """Forward foreground colour to tools and update brush preview."""
        mw = self.mw
        mw._tools.set_foreground_color(color.to_array())
        self.signals.brush_cursor_requested.emit()
