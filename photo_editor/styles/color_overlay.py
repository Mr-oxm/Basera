"""Color Overlay layer style – fill the layer with a solid colour."""

import numpy as np

from ..blending.blend_modes import get_blend_func
from ..core.enums import BlendMode
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
        t = alpha * opacity

        # Build a flat colour layer matching the image dimensions
        h, w = img.shape[:2]
        effect = np.empty((h, w, 3), dtype=np.float32)
        effect[:, :, 0] = color[0]
        effect[:, :, 1] = color[1]
        effect[:, :, 2] = color[2]

        mode = self.params.blend_mode
        if mode == BlendMode.NORMAL:
            blended = effect
        else:
            blend_fn = get_blend_func(mode)
            blended = blend_fn(img[:, :, :3], effect)
            np.clip(blended, 0, 1, out=blended)

        out = img.copy()
        for c in range(3):
            out[:, :, c] = img[:, :, c] * (1.0 - t) + blended[:, :, c] * t

        return np.clip(out, 0, 1)

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
        return self.apply(layer_image)
