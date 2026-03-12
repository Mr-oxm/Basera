"""Inner Glow layer style – glow composited inside the layer."""

import cv2
import numpy as np

from .style_base import LayerStyle


class InnerGlow(LayerStyle):
    """Blur the inverted alpha inward and composite a glow inside the layer."""

    def __init__(self) -> None:
        super().__init__("Inner Glow")
        self.params.extra = {
            "color": [1.0, 1.0, 0.5],
            "opacity": 0.75,
            "choke": 0,
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
        choke = float(p["choke"])
        size = int(p["size"])

        h, w = img.shape[:2]
        alpha = img[:, :, 3]

        # Invert alpha – the glow comes from the edges inward
        inv_alpha = 1.0 - alpha

        # Choke – erode the inverted alpha to shrink the glow
        choke_px = max(int(size * choke), 0)
        if choke_px > 0:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (choke_px * 2 + 1, choke_px * 2 + 1))
            inv_alpha = cv2.erode(inv_alpha, kernel)

        # Blur
        ksize = max(size * 2 + 1, 1)
        if ksize > 1:
            inv_alpha = cv2.GaussianBlur(inv_alpha, (ksize, ksize), 0)

        # Clip to the inside of the layer
        glow_alpha = np.clip(inv_alpha * alpha * opacity, 0, 1)

        # Blend glow colour onto the layer
        out = img.copy()
        for c in range(3):
            out[:, :, c] = img[:, :, c] * (1.0 - glow_alpha) + color[c] * glow_alpha

        return np.clip(out, 0, 1)

    def supports_region_rendering(self) -> bool:
        return True

    def region_padding(self) -> int:
        size = int(self.params.extra.get("size", 10))
        choke = float(self.params.extra.get("choke", 0))
        return max(size * 2 + 1, int(size * choke) + 1)

    def apply_region(self, layer_image: np.ndarray, offset_x: int, offset_y: int, full_width: int, full_height: int) -> np.ndarray:
        return self.apply(layer_image)
