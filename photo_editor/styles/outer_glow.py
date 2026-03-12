"""Outer Glow layer style – coloured glow composited behind the layer."""

import cv2
import numpy as np

from .style_base import LayerStyle


class OuterGlow(LayerStyle):
    """Expand and blur the alpha channel, then composite a glow behind the layer."""

    def __init__(self) -> None:
        super().__init__("Outer Glow")
        self.params.extra = {
            "color": [1.0, 1.0, 0.5],
            "opacity": 0.75,
            "spread": 0,
            "size": 10,
        }

    # ------------------------------------------------------------------
    def apply(self, layer_image: np.ndarray) -> np.ndarray:
        img = self._f32(layer_image).copy()
        p = self.params.extra
        if not self.params.enabled:
            return img

        color = np.asarray(p["color"], dtype=np.float32)
        opacity = float(p["opacity"]) * self.params.opacity
        spread = float(p["spread"])
        size = int(p["size"])

        h, w = img.shape[:2]
        alpha = img[:, :, 3]

        # Dilate alpha to expand the glow region
        dilate_px = max(int(size * spread), 0)
        glow_alpha = alpha.copy()
        if dilate_px > 0:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_px * 2 + 1, dilate_px * 2 + 1))
            glow_alpha = cv2.dilate(glow_alpha, kernel)

        # Blur
        ksize = max(size * 2 + 1, 1)
        if ksize > 1:
            glow_alpha = cv2.GaussianBlur(glow_alpha, (ksize, ksize), 0)

        glow_alpha = np.clip(glow_alpha * opacity, 0, 1)

        # Build glow RGBA
        glow = np.zeros_like(img)
        glow[:, :, 0] = color[0]
        glow[:, :, 1] = color[1]
        glow[:, :, 2] = color[2]
        glow[:, :, 3] = glow_alpha

        # Composite glow behind layer (dst-over)
        out = img.copy()
        inv_layer_alpha = 1.0 - img[:, :, 3]
        for c in range(3):
            out[:, :, c] = img[:, :, c] * img[:, :, 3] + glow[:, :, c] * glow[:, :, 3] * inv_layer_alpha
        out[:, :, 3] = img[:, :, 3] + glow[:, :, 3] * inv_layer_alpha
        mask = out[:, :, 3] > 0
        for c in range(3):
            out[:, :, c][mask] /= out[:, :, 3][mask]

        return np.clip(out, 0, 1)

    def supports_region_rendering(self) -> bool:
        return True

    def region_padding(self) -> int:
        size = int(self.params.extra.get("size", 10))
        spread = float(self.params.extra.get("spread", 0))
        return max(size * 2 + 1, int(size * spread) + size + 1)

    def apply_region(self, layer_image: np.ndarray, offset_x: int, offset_y: int, full_width: int, full_height: int) -> np.ndarray:
        return self.apply(layer_image)
