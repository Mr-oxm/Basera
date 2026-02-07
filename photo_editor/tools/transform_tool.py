"""Transform tool — interactive drag-based scaling and rotation via TransformEngine."""

import math

import cv2
import numpy as np

from .tool_base import Tool
from ..core.document import Document
from ..transforms.transform_engine import TransformEngine


class TransformTool(Tool):
    """Drag to scale; Shift-drag (far from centre) to rotate the active layer."""

    def __init__(self) -> None:
        super().__init__("Transform")
        self.mode: str = "scale"  # "scale" | "rotate" | "free"
        self._engine = TransformEngine()

        self._start_x: int = 0
        self._start_y: int = 0
        self._dragging: bool = False
        self._orig_pixels: np.ndarray | None = None
        self._center_x: float = 0
        self._center_y: float = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _apply_transform(self, layer_pixels: np.ndarray, x: int, y: int) -> np.ndarray:
        """Compute and return transformed pixels based on current mode and drag delta."""
        if self._orig_pixels is None:
            return layer_pixels

        if self.mode == "rotate":
            # Angle from start drag to current drag relative to centre
            a0 = math.atan2(self._start_y - self._center_y,
                            self._start_x - self._center_x)
            a1 = math.atan2(y - self._center_y, x - self._center_x)
            angle_deg = math.degrees(a1 - a0)
            return TransformEngine.rotate(self._orig_pixels, angle_deg, expand=False)

        elif self.mode == "free":
            dx = x - self._start_x
            dy = y - self._start_y
            a0 = math.atan2(self._start_y - self._center_y,
                            self._start_x - self._center_x)
            a1 = math.atan2(y - self._center_y, x - self._center_x)
            angle_deg = math.degrees(a1 - a0)
            d0 = max(1.0, math.hypot(self._start_x - self._center_x,
                                     self._start_y - self._center_y))
            d1 = max(1.0, math.hypot(x - self._center_x, y - self._center_y))
            s = d1 / d0
            return TransformEngine.free_transform(
                self._orig_pixels, angle=angle_deg, sx=s, sy=s,
            )

        else:  # scale
            dx = x - self._start_x
            dy = y - self._start_y
            h, w = self._orig_pixels.shape[:2]
            sx = max(0.05, 1.0 + dx / max(w, 1))
            sy = max(0.05, 1.0 + dy / max(h, 1))
            scaled = TransformEngine.scale(self._orig_pixels, sx, sy)
            # Paste scaled result back into original-size canvas
            result = np.zeros_like(self._orig_pixels)
            sh, sw = scaled.shape[:2]
            ch, cw = min(sh, h), min(sw, w)
            result[:ch, :cw] = scaled[:ch, :cw]
            return result

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return
        doc.save_snapshot("Transform")
        self._start_x, self._start_y = x, y
        self._orig_pixels = layer.pixels.copy()
        h, w = layer.pixels.shape[:2]
        self._center_x = w / 2.0
        self._center_y = h / 2.0
        self._dragging = True

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        if not self._dragging:
            return
        layer = doc.layers.active_layer
        if layer is None:
            return
        transformed = self._apply_transform(layer.pixels, x, y)
        # Write back — ensure shape matches
        h, w = layer.pixels.shape[:2]
        th, tw = transformed.shape[:2]
        ch, cw = min(h, th), min(w, tw)
        layer.pixels[:] = 0
        layer.pixels[:ch, :cw] = transformed[:ch, :cw]
        np.clip(layer.pixels, 0, 1, out=layer.pixels)

    def on_release(self, doc: Document, x: int, y: int) -> None:
        if self._dragging:
            # Final application already happened in on_move
            self._dragging = False
            self._orig_pixels = None
