"""Pan (Hand) tool — click-drag to pan the canvas view.

Works in raw widget (screen) coordinates to avoid the feedback loop
that arises when document coordinates shift as the view pans.
"""

from .tool_base import Tool
from ..core.document import Document


class PanTool(Tool):
    """Click and drag to pan the canvas."""

    def __init__(self) -> None:
        super().__init__("Pan")
        self._pan_callback = None
        self._dragging: bool = False

    def set_pan_callback(self, cb) -> None:
        """Set callback: cb(dx_screen: float, dy_screen: float) pixel delta."""
        self._pan_callback = cb

    # --- Widget-coordinate hooks (set by MainWindow) ---
    # These bypass _canvas_to_doc so we get stable screen deltas.
    _last_widget_x: float = 0.0
    _last_widget_y: float = 0.0

    def begin_pan(self, wx: float, wy: float) -> None:
        """Called with widget coords on press."""
        self._last_widget_x = wx
        self._last_widget_y = wy
        self._dragging = True

    def update_pan(self, wx: float, wy: float) -> None:
        """Called with widget coords on move."""
        if not self._dragging:
            return
        dx = wx - self._last_widget_x
        dy = wy - self._last_widget_y
        self._last_widget_x = wx
        self._last_widget_y = wy
        if self._pan_callback is not None:
            self._pan_callback(dx, dy)

    def end_pan(self) -> None:
        """Called on release."""
        self._dragging = False

    # --- Tool interface (doc-coord events — unused but required) ---

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        pass  # handled by begin_pan

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        pass  # handled by update_pan

    def on_release(self, doc: Document, x: int, y: int) -> None:
        pass  # handled by end_pan
