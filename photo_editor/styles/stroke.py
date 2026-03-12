"""Stroke layer style – outline the layer via alpha dilation."""

import cv2
import numpy as np

from ..blending.blend_modes import get_blend_func
from ..core.enums import BlendMode
from .style_base import LayerStyle


class Stroke(LayerStyle):
    """Dilate (or erode) the alpha to create an outline stroke around the layer."""

    def __init__(self) -> None:
        super().__init__("Stroke")
        self.params.extra = {
            "color": [0.0, 0.0, 0.0],
            "size": 3,
            "position": "outside",  # outside | inside | center
            "opacity": 1.0,
        }

    # ------------------------------------------------------------------
    def apply(self, layer_image: np.ndarray) -> np.ndarray:
        img = self._f32(layer_image).copy()
        p = self.params.extra
        if not self.params.enabled:
            return img

        color = np.asarray(p["color"], dtype=np.float32)
        size = max(int(p["size"]), 1)
        position = str(p["position"]).lower()
        opacity = float(p["opacity"]) * self.params.opacity

        h, w = img.shape[:2]
        alpha = img[:, :, 3]

        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (size * 2 + 1, size * 2 + 1)
        )

        if position == "outside":
            expanded = cv2.dilate(alpha, kernel)
            stroke_mask = np.clip(expanded - alpha, 0, 1)
        elif position == "inside":
            eroded = cv2.erode(alpha, kernel)
            stroke_mask = np.clip(alpha - eroded, 0, 1)
        else:  # center
            half = max(size // 2, 1)
            k_half = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (half * 2 + 1, half * 2 + 1)
            )
            expanded = cv2.dilate(alpha, k_half)
            eroded = cv2.erode(alpha, k_half)
            stroke_mask = np.clip(expanded - eroded, 0, 1)

        stroke_mask = stroke_mask * opacity

        # Build stroke RGBA
        stroke = np.zeros_like(img)
        stroke[:, :, 0] = color[0]
        stroke[:, :, 1] = color[1]
        stroke[:, :, 2] = color[2]
        stroke[:, :, 3] = stroke_mask

        # Apply blend mode
        mode = self.params.blend_mode
        if mode != BlendMode.NORMAL:
            blend_fn = get_blend_func(mode)
            blended_rgb = blend_fn(img[:, :, :3], stroke[:, :, :3])
            np.clip(blended_rgb, 0, 1, out=blended_rgb)
            stroke[:, :, :3] = blended_rgb

        if position == "inside":
            # Blend stroke colour inside the layer
            out = img.copy()
            for c in range(3):
                out[:, :, c] = img[:, :, c] * (1.0 - stroke_mask) + stroke[:, :, c] * stroke_mask
            return np.clip(out, 0, 1)

        # Outside / center – composite stroke behind layer
        out = img.copy()
        inv_layer_alpha = 1.0 - img[:, :, 3]
        for c in range(3):
            out[:, :, c] = (
                img[:, :, c] * img[:, :, 3]
                + stroke[:, :, c] * stroke[:, :, 3] * inv_layer_alpha
            )
        out[:, :, 3] = img[:, :, 3] + stroke[:, :, 3] * inv_layer_alpha
        mask = out[:, :, 3] > 0
        for c in range(3):
            out[:, :, c][mask] /= out[:, :, 3][mask]

        return np.clip(out, 0, 1)

    def supports_region_rendering(self) -> bool:
        return True

    def region_padding(self) -> int:
        size = max(int(self.params.extra.get("size", 3)), 1)
        position = str(self.params.extra.get("position", "outside")).lower()
        if position == "inside":
            return size
        if position == "center":
            return max(size // 2, 1)
        return size

    def apply_region(self, layer_image: np.ndarray, offset_x: int, offset_y: int, full_width: int, full_height: int) -> np.ndarray:
        return self.apply(layer_image)
