"""Gradient Overlay layer style – linear gradient masked by layer alpha."""

import cv2
import numpy as np

from ..blending.blend_modes import get_blend_func
from ..core.enums import BlendMode
from .style_base import LayerStyle


class GradientOverlay(LayerStyle):
    """Apply a linear gradient across the layer, masked by its alpha."""

    def __init__(self) -> None:
        super().__init__("Gradient Overlay")
        self.params.extra = {
            "color1": [0.0, 0.0, 0.0],
            "color2": [1.0, 1.0, 1.0],
            "angle": 0,
            "opacity": 1.0,
        }

    # ------------------------------------------------------------------
    def apply(self, layer_image: np.ndarray) -> np.ndarray:
        return self.apply_region(layer_image, 0, 0, layer_image.shape[1], layer_image.shape[0])

    def supports_region_rendering(self) -> bool:
        return True

    def apply_region(
        self,
        layer_image: np.ndarray,
        offset_x: int,
        offset_y: int,
        full_width: int,
        full_height: int,
    ) -> np.ndarray:
        img = self._f32(layer_image).copy()
        p = self.params.extra
        if not self.params.enabled:
            return img

        c1 = np.asarray(p["color1"], dtype=np.float32)
        c2 = np.asarray(p["color2"], dtype=np.float32)
        angle_rad = np.deg2rad(float(p["angle"]))
        opacity = float(p["opacity"]) * self.params.opacity

        h, w = img.shape[:2]
        alpha = img[:, :, 3]

        # Build a 0-1 ramp along the gradient direction
        # Centre at the middle of the image
        cx, cy = full_width / 2.0, full_height / 2.0
        xs = np.arange(offset_x, offset_x + w, dtype=np.float32) - cx
        ys = np.arange(offset_y, offset_y + h, dtype=np.float32) - cy
        gx, gy = np.meshgrid(xs, ys)

        cos_a = float(np.cos(angle_rad))
        sin_a = float(np.sin(angle_rad))

        # Project onto the gradient axis
        proj = gx * cos_a + gy * sin_a

        # Normalise to [0, 1] using the full layer extent, not just the ROI.
        x0 = -cx
        x1 = (full_width - 1) - cx
        y0 = -cy
        y1 = (full_height - 1) - cy
        corners = np.array([
            x0 * cos_a + y0 * sin_a,
            x1 * cos_a + y0 * sin_a,
            x0 * cos_a + y1 * sin_a,
            x1 * cos_a + y1 * sin_a,
        ], dtype=np.float32)
        pmin = float(corners.min())
        pmax = float(corners.max())
        if pmax - pmin > 0:
            t = (proj - pmin) / (pmax - pmin)
        else:
            t = np.zeros_like(proj)

        # Interpolate colours
        grad = np.zeros((h, w, 3), dtype=np.float32)
        for c in range(3):
            grad[:, :, c] = c1[c] * (1.0 - t) + c2[c] * t

        # Apply blend mode
        mode = self.params.blend_mode
        if mode != BlendMode.NORMAL:
            blend_fn = get_blend_func(mode)
            grad = blend_fn(img[:, :, :3], grad)
            np.clip(grad, 0, 1, out=grad)

        # Blend onto the layer, masked by alpha
        blend_t = alpha * opacity
        out = img.copy()
        for c in range(3):
            out[:, :, c] = img[:, :, c] * (1.0 - blend_t) + grad[:, :, c] * blend_t

        return np.clip(out, 0, 1)
