"""Satin layer style – offset alpha two ways, difference, blur, composite."""

import cv2
import numpy as np

from .style_base import LayerStyle


class Satin(LayerStyle):
    """Create a satin-like interior shading by offset-difference of the alpha."""

    def __init__(self) -> None:
        super().__init__("Satin")
        self.params.extra = {
            "color": [0.0, 0.0, 0.0],
            "opacity": 0.5,
            "angle": 19,
            "distance": 11,
            "size": 14,
        }

    # ------------------------------------------------------------------
    def apply(self, layer_image: np.ndarray) -> np.ndarray:
        img = self._f32(layer_image).copy()
        p = self.params.extra
        if not self.params.enabled:
            return img

        color = np.asarray(p["color"], dtype=np.float32)
        opacity = float(p["opacity"]) * self.params.opacity
        angle_rad = np.deg2rad(float(p["angle"]))
        distance = int(p["distance"])
        size = int(p["size"])

        h, w = img.shape[:2]
        alpha = img[:, :, 3]

        dx = int(round(np.cos(angle_rad) * distance))
        dy = -int(round(np.sin(angle_rad) * distance))

        # Two offsets in opposite directions
        m1 = np.float32([[1, 0, dx], [0, 1, dy]])
        m2 = np.float32([[1, 0, -dx], [0, 1, -dy]])
        a1 = cv2.warpAffine(alpha, m1, (w, h), borderValue=0)
        a2 = cv2.warpAffine(alpha, m2, (w, h), borderValue=0)

        # Absolute difference
        satin = np.abs(a1 - a2)

        # Blur
        ksize = max(size * 2 + 1, 1)
        if ksize > 1:
            satin = cv2.GaussianBlur(satin, (ksize, ksize), 0)

        # Clip inside layer and apply opacity
        satin = np.clip(satin * alpha * opacity, 0, 1)

        # Blend satin colour onto the layer
        out = img.copy()
        for c in range(3):
            out[:, :, c] = img[:, :, c] * (1.0 - satin) + color[c] * satin

        return np.clip(out, 0, 1)
