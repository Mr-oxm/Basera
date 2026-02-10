"""Crop tool — drag to define a crop region, release to apply."""

import numpy as np

from .tool_base import Tool
from ..core.document import Document


class CropTool(Tool):
    """Drag to define a rectangular crop region."""

    def __init__(self) -> None:
        super().__init__("Crop")
        self._start_x: int = 0
        self._start_y: int = 0
        self._dragging: bool = False
        self._crop_callback = None

    def set_crop_callback(self, cb) -> None:
        """Set callback: cb(x, y, w, h) called when the crop is applied."""
        self._crop_callback = cb

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        self._start_x, self._start_y = x, y
        self._dragging = True

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        pass  # Could show a live crop preview here

    def on_release(self, doc: Document, x: int, y: int) -> None:
        if not self._dragging:
            return
        self._dragging = False
        rx = min(self._start_x, x)
        ry = min(self._start_y, y)
        rw = abs(x - self._start_x)
        rh = abs(y - self._start_y)
        if rw < 2 or rh < 2:
            return
        if self._crop_callback is not None:
            self._crop_callback(rx, ry, rw, rh)
