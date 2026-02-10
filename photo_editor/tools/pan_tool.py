"""Pan (Hand) tool — click-drag to pan the canvas view."""

from .tool_base import Tool
from ..core.document import Document


class PanTool(Tool):
    """Click and drag to pan the canvas."""

    def __init__(self) -> None:
        super().__init__("Pan")
        self._pan_callback = None
        self._last_x: int = 0
        self._last_y: int = 0
        self._dragging: bool = False

    def set_pan_callback(self, cb) -> None:
        """Set callback: cb(dx: int, dy: int) to apply pan delta."""
        self._pan_callback = cb

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        self._last_x, self._last_y = x, y
        self._dragging = True

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        if not self._dragging:
            return
        dx = x - self._last_x
        dy = y - self._last_y
        if self._pan_callback is not None:
            self._pan_callback(dx, dy)
        self._last_x, self._last_y = x, y

    def on_release(self, doc: Document, x: int, y: int) -> None:
        self._dragging = False
