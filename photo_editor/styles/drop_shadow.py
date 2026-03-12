"""Drop Shadow layer style – casts a shadow behind the layer."""

import cv2
import numpy as np

from ..blending.blend_modes import get_blend_func
from ..core.enums import BlendMode
from .style_base import LayerStyle


class DropShadow(LayerStyle):
    """Offset the layer alpha, blur it, and composite a coloured shadow behind."""

    def __init__(self) -> None:
        super().__init__("Drop Shadow")
        self.params.extra = {
            "color": [0.0, 0.0, 0.0],
            "opacity": 0.75,
            "angle": 120,
            "distance": 5,
            "spread": 0,
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
        spread = float(p["spread"])
        size = int(p["size"])

        h, w = img.shape[:2]
        alpha = img[:, :, 3]

        # Offset direction
        dx = int(round(np.cos(angle_rad) * distance))
        dy = -int(round(np.sin(angle_rad) * distance))

        # Translate alpha
        m_trans = np.float32([[1, 0, dx], [0, 1, dy]])
        shadow_alpha = cv2.warpAffine(alpha, m_trans, (w, h), borderValue=0)

        # Spread – threshold to harden the shadow before blur
        if spread > 0:
            thresh = spread * shadow_alpha.max() if shadow_alpha.max() > 0 else 0
            shadow_alpha = np.where(shadow_alpha >= thresh, shadow_alpha, 0.0).astype(np.float32)

        # Blur (size)
        ksize = max(size * 2 + 1, 1)
        if ksize > 1:
            shadow_alpha = cv2.GaussianBlur(shadow_alpha, (ksize, ksize), 0)

        shadow_alpha = np.clip(shadow_alpha * opacity, 0, 1)

        # Build shadow RGBA
        shadow = np.zeros_like(img)
        shadow[:, :, 0] = color[0]
        shadow[:, :, 1] = color[1]
        shadow[:, :, 2] = color[2]
        shadow[:, :, 3] = shadow_alpha

        # Apply blend mode to shadow colour before compositing
        mode = self.params.blend_mode
        if mode != BlendMode.NORMAL:
            blend_fn = get_blend_func(mode)
            blended_rgb = blend_fn(img[:, :, :3], shadow[:, :, :3])
            np.clip(blended_rgb, 0, 1, out=blended_rgb)
            shadow[:, :, :3] = blended_rgb

        # Composite: shadow behind layer  (dst-over equivalent)
        out = img.copy()
        inv_layer_alpha = 1.0 - img[:, :, 3]
        for c in range(3):
            out[:, :, c] = img[:, :, c] * img[:, :, 3] + shadow[:, :, c] * shadow[:, :, 3] * inv_layer_alpha
        out[:, :, 3] = img[:, :, 3] + shadow[:, :, 3] * inv_layer_alpha
        # Avoid division by zero
        mask = out[:, :, 3] > 0
        for c in range(3):
            out[:, :, c][mask] /= out[:, :, 3][mask]

        return np.clip(out, 0, 1)

    def supports_region_rendering(self) -> bool:
        return True

    def region_padding(self) -> int:
        distance = int(self.params.extra.get("distance", 5))
        size = int(self.params.extra.get("size", 5))
        spread = float(self.params.extra.get("spread", 0))
        return max(distance + size * 2 + 1, int(size * spread) + size + 1)

    def apply_region(self, layer_image: np.ndarray, offset_x: int, offset_y: int, full_width: int, full_height: int) -> np.ndarray:
        return self.apply(layer_image)
