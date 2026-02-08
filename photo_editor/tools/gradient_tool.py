"""Gradient tool — fills the active layer with a linear or radial colour gradient."""

import numpy as np

from .tool_base import Tool
from ..core.document import Document


class GradientTool(Tool):
    """Draws a gradient between two colours on press→release drag."""

    def __init__(self) -> None:
        super().__init__("Gradient")
        self.color1: np.ndarray = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
        self.color2: np.ndarray = np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float32)
        self.gradient_type: str = "linear"  # "linear" | "radial"
        self.opacity: float = 1.0

        self._start_x: int = 0
        self._start_y: int = 0
        self._dragging: bool = False

    # ------------------------------------------------------------------
    # Gradient generators
    # ------------------------------------------------------------------

    @staticmethod
    def _linear_map(h: int, w: int, x0: int, y0: int, x1: int, y1: int) -> np.ndarray:
        """Return a [H, W] float32 array in [0, 1] representing the linear parameter."""
        dx, dy = x1 - x0, y1 - y0
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            return np.zeros((h, w), dtype=np.float32)
        yy, xx = np.mgrid[0:h, 0:w]
        t = ((xx - x0) * dx + (yy - y0) * dy) / length_sq
        return np.clip(t, 0, 1).astype(np.float32)

    @staticmethod
    def _radial_map(h: int, w: int, cx: int, cy: int, ex: int, ey: int) -> np.ndarray:
        """Return a [H, W] float32 radial parameter (0 at centre, 1 at edge)."""
        radius = max(1.0, np.hypot(ex - cx, ey - cy))
        yy, xx = np.mgrid[0:h, 0:w]
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2).astype(np.float32)
        return np.clip(dist / radius, 0, 1)

    def _render_gradient(self, h: int, w: int, x0: int, y0: int,
                         x1: int, y1: int) -> np.ndarray:
        """Return an [H, W, 4] float32 gradient image."""
        if self.gradient_type == "radial":
            t = self._radial_map(h, w, x0, y0, x1, y1)
        else:
            t = self._linear_map(h, w, x0, y0, x1, y1)
        t = t[..., np.newaxis]  # [H, W, 1]
        gradient = self.color1 * (1.0 - t) + self.color2 * t
        return gradient.astype(np.float32)

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        doc.save_snapshot("Gradient")
        self._start_x, self._start_y = x, y
        self._dragging = True

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        # Could show a live preview here; currently a no-op until release.
        pass

    def on_release(self, doc: Document, x: int, y: int) -> None:
        if not self._dragging:
            return
        self._dragging = False
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return

        # Convert document coords to layer-local pixel coords
        lx, ly = layer.position
        h, w = layer.pixels.shape[:2]
        gradient = self._render_gradient(h, w,
                                         self._start_x - lx, self._start_y - ly,
                                         x - lx, y - ly)

        if self.opacity < 1.0:
            layer.pixels[:] = layer.pixels * (1 - self.opacity) + gradient * self.opacity
        else:
            layer.pixels[:] = gradient

        np.clip(layer.pixels, 0, 1, out=layer.pixels)
