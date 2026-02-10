"""Inner Shadow layer style – shadow composited inside the layer."""

import cv2
import numpy as np

from ..blending.blend_modes import get_blend_func
from ..core.enums import BlendMode
from .style_base import LayerStyle


class InnerShadow(LayerStyle):
    """Like Drop Shadow but the shadow is clipped to the interior of the layer."""

    def __init__(self) -> None:
        super().__init__("Inner Shadow")
        self.params.extra = {
            "color": [0.0, 0.0, 0.0],
            "opacity": 0.75,
            "angle": 120,
            "distance": 5,
            "choke": 0,
            "size": 5,
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
        choke = float(p["choke"])
        size = int(p["size"])

        h, w = img.shape[:2]
        alpha = img[:, :, 3]

        # Invert alpha to get the "hole"
        inv_alpha = 1.0 - alpha

        # Offset the inverted alpha
        dx = int(round(np.cos(angle_rad) * distance))
        dy = -int(round(np.sin(angle_rad) * distance))
        m_trans = np.float32([[1, 0, dx], [0, 1, dy]])
        shadow_alpha = cv2.warpAffine(inv_alpha, m_trans, (w, h), borderValue=1)

        # Choke – shrink the soft area
        if choke > 0:
            thresh = choke * shadow_alpha.max() if shadow_alpha.max() > 0 else 0
            shadow_alpha = np.where(shadow_alpha >= thresh, shadow_alpha, 0.0).astype(np.float32)

        # Blur
        ksize = max(size * 2 + 1, 1)
        if ksize > 1:
            shadow_alpha = cv2.GaussianBlur(shadow_alpha, (ksize, ksize), 0)

        # Clip to the inside of the layer
        shadow_alpha = np.clip(shadow_alpha * alpha * opacity, 0, 1)

        # Apply blend mode to shadow colour before compositing
        mode = self.params.blend_mode
        shadow_rgb = np.empty_like(img[:, :, :3])
        shadow_rgb[:, :, 0] = color[0]
        shadow_rgb[:, :, 1] = color[1]
        shadow_rgb[:, :, 2] = color[2]
        if mode != BlendMode.NORMAL:
            blend_fn = get_blend_func(mode)
            shadow_rgb = blend_fn(img[:, :, :3], shadow_rgb)
            np.clip(shadow_rgb, 0, 1, out=shadow_rgb)

        # Blend shadow colour onto the layer
        out = img.copy()
        for c in range(3):
            out[:, :, c] = img[:, :, c] * (1.0 - shadow_alpha) + shadow_rgb[:, :, c] * shadow_alpha

        return np.clip(out, 0, 1)
