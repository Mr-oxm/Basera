"""Pattern Overlay layer style – tile a built-in pattern masked by alpha."""

import numpy as np

from .style_base import LayerStyle


class PatternOverlay(LayerStyle):
    """Tile a procedural checkerboard pattern onto the layer."""

    def __init__(self) -> None:
        super().__init__("Pattern Overlay")
        self.params.extra = {
            "scale": 1.0,
            "opacity": 1.0,
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _checkerboard(h: int, w: int, cell: int) -> np.ndarray:
        """Return a float32 [H, W] checkerboard in {0, 1}."""
        rows = np.arange(h) // cell
        cols = np.arange(w) // cell
        return ((rows[:, None] + cols[None, :]) % 2).astype(np.float32)

    # ------------------------------------------------------------------
    def apply(self, layer_image: np.ndarray) -> np.ndarray:
        img = self._f32(layer_image).copy()
        p = self.params.extra
        if not self.params.enabled:
            return img

        scale = max(float(p["scale"]), 0.1)
        opacity = float(p["opacity"]) * self.params.opacity

        h, w = img.shape[:2]
        alpha = img[:, :, 3]

        cell = max(int(8 * scale), 1)
        pattern = self._checkerboard(h, w, cell)

        # Convert pattern to RGB (white / mid-grey)
        pat_rgb = np.empty((h, w, 3), dtype=np.float32)
        pat_rgb[:, :, 0] = pattern * 0.5 + 0.5  # light square 1.0, dark 0.5
        pat_rgb[:, :, 1] = pattern * 0.5 + 0.5
        pat_rgb[:, :, 2] = pattern * 0.5 + 0.5

        # Blend onto the layer, masked by alpha
        blend_t = alpha * opacity
        out = img.copy()
        for c in range(3):
            out[:, :, c] = img[:, :, c] * (1.0 - blend_t) + pat_rgb[:, :, c] * blend_t

        return np.clip(out, 0, 1)
