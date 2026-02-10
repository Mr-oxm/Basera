"""Eyedropper tool — samples a colour from the canvas."""

import numpy as np

from .tool_base import Tool
from ..core.document import Document


class EyedropperTool(Tool):
    """Click on the canvas to sample a colour."""

    def __init__(self) -> None:
        super().__init__("Eyedropper")
        self._color_callback = None

    def set_color_callback(self, cb) -> None:
        """Set callback: cb(rgba: np.ndarray) called when a colour is sampled."""
        self._color_callback = cb

    def _sample(self, doc: Document, x: int, y: int) -> None:
        if doc is None:
            return
        layer = doc.layers.active_layer
        if layer is None:
            return
        lx, ly = layer.position
        px, py = x - lx, y - ly
        h, w = layer.pixels.shape[:2]
        if 0 <= px < w and 0 <= py < h:
            color = layer.pixels[py, px].copy()
            if self._color_callback is not None:
                self._color_callback(color)

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        self._sample(doc, x, y)

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        self._sample(doc, x, y)

    def on_release(self, doc: Document, x: int, y: int) -> None:
        pass
