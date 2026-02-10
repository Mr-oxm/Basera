"""Zoom tool — click to zoom in, Alt+click / right-click to zoom out."""

from .tool_base import Tool
from ..core.document import Document


class ZoomTool(Tool):
    """Click to zoom in, Alt+click to zoom out."""

    def __init__(self) -> None:
        super().__init__("Zoom")
        self._zoom_callback = None

    def set_zoom_callback(self, cb) -> None:
        """Set callback: cb(factor: float) to apply zoom."""
        self._zoom_callback = cb

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        if self._zoom_callback is not None:
            self._zoom_callback(1.5)

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        pass

    def on_release(self, doc: Document, x: int, y: int) -> None:
        pass

    def zoom_out(self) -> None:
        """Programmatic zoom-out (e.g. Alt+click)."""
        if self._zoom_callback is not None:
            self._zoom_callback(1.0 / 1.5)
