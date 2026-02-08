"""Paint Bucket tool — flood-fills a contiguous region with a solid colour."""

import numpy as np

from .tool_base import Tool
from ..core.document import Document


class PaintBucketTool(Tool):
    """Fills connected pixels that match the target colour within a tolerance."""

    def __init__(self) -> None:
        super().__init__("Paint Bucket")
        self.color: np.ndarray = np.array([1.0, 0.0, 0.0, 1.0], dtype=np.float32)
        self.tolerance: int = 32  # 0–255 scale
        self.opacity: float = 1.0
        self.contiguous: bool = True

    # ------------------------------------------------------------------
    # Flood-fill
    # ------------------------------------------------------------------

    @staticmethod
    def _flood_fill_mask(pixels: np.ndarray, sx: int, sy: int,
                         tolerance: float) -> np.ndarray:
        """Return a boolean mask of connected pixels similar to the seed colour."""
        h, w = pixels.shape[:2]
        seed_color = pixels[sy, sx].copy()
        visited = np.zeros((h, w), dtype=np.bool_)
        mask = np.zeros((h, w), dtype=np.bool_)
        stack = [(sx, sy)]
        tol = tolerance / 255.0  # normalise to [0, 1] colour space

        while stack:
            cx, cy = stack.pop()
            if cx < 0 or cx >= w or cy < 0 or cy >= h:
                continue
            if visited[cy, cx]:
                continue
            visited[cy, cx] = True
            diff = np.abs(pixels[cy, cx] - seed_color).max()
            if diff > tol:
                continue
            mask[cy, cx] = True
            stack.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])
        return mask

    @staticmethod
    def _global_tolerance_mask(pixels: np.ndarray, sx: int, sy: int,
                               tolerance: float) -> np.ndarray:
        """Return a boolean mask of ALL pixels similar to the seed colour (non-contiguous)."""
        seed_color = pixels[sy, sx]
        diff = np.abs(pixels - seed_color).max(axis=-1)
        return diff <= (tolerance / 255.0)

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return
        # Convert document coords to layer-local pixel coords
        lx, ly = layer.position
        px, py = x - lx, y - ly
        h, w = layer.pixels.shape[:2]
        if px < 0 or px >= w or py < 0 or py >= h:
            return

        doc.save_snapshot("Paint Bucket Fill")

        if self.contiguous:
            fill_mask = self._flood_fill_mask(layer.pixels, px, py, self.tolerance)
        else:
            fill_mask = self._global_tolerance_mask(layer.pixels, px, py, self.tolerance)

        mask = fill_mask.astype(np.float32)[..., np.newaxis] * self.opacity
        layer.pixels[:] = layer.pixels * (1 - mask) + self.color * mask
        np.clip(layer.pixels, 0, 1, out=layer.pixels)

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        pass  # No drag behaviour

    def on_release(self, doc: Document, x: int, y: int) -> None:
        pass
