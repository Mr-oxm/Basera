"""Color Overlay layer style – fill the layer with a solid colour."""

import numpy as np

from .style_base import LayerStyle


class ColorOverlay(LayerStyle):
    """Replace the layer RGB with a flat colour wherever alpha > 0."""

    def __init__(self) -> None:
        super().__init__("Color Overlay")
        self.params.extra = {
            "color": [1.0, 0.0, 0.0],
            "opacity": 1.0,
        }

    # ------------------------------------------------------------------
    def apply(self, layer_image: np.ndarray) -> np.ndarray:
        img = self._f32(layer_image).copy()
        p = self.params.extra
        if not self.params.enabled:
            return img

        color = np.asarray(p["color"], dtype=np.float32)
        opacity = float(p["opacity"]) * self.params.opacity
        alpha = img[:, :, 3]

        # Blend: layer_rgb * (1 - t) + color * t, where t is opacity inside the mask
        t = alpha * opacity
        out = img.copy()
        for c in range(3):
            out[:, :, c] = img[:, :, c] * (1.0 - t) + color[c] * t

        return np.clip(out, 0, 1)
