"""Foreground/background color from Color panel."""

from __future__ import annotations


class ColorController:
    """Handles foreground color changes from the Color panel."""

    def __init__(self) -> None:
        self._mw = None

    def wire(self, main_window) -> None:
        """Connect to main window and wire panel signals."""
        self._mw = main_window
        main_window._color_panel.fg_changed.connect(self.on_fg_color_changed)

    def on_fg_color_changed(self, color) -> None:
        """Forward foreground colour to tools and update brush preview."""
        mw = self._mw
        mw._tools.set_foreground_color(color.to_array())
        mw._tool_ctrl.update_brush_cursor()
