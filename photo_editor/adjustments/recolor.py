"""Recolor — rotate hues in a band around *from_hue* toward *to_hue*."""

from __future__ import annotations

import numpy as np

from ..utils.color_utils import hsv_to_rgb, rgb_to_hsv
from .adjustment_base import Adjustment


def _smoothstep01(t: np.ndarray) -> np.ndarray:
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class Recolor(Adjustment):
    def __init__(self) -> None:
        super().__init__(
            "Recolor",
            {
                "from_hue": 0.0,
                "to_hue": 60.0,
                "width": 45.0,
                "amount": 100.0,
            },
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image)
        alpha = self._alpha(image)

        from_h = float(params.get("from_hue", 0)) % 360.0
        to_h = float(params.get("to_hue", 0)) % 360.0
        width = max(float(params.get("width", 45)), 4.0)
        amount = float(np.clip(params.get("amount", 100), 0, 100)) / 100.0

        if amount < 1e-6:
            return image.copy()

        hsv = rgb_to_hsv(np.ascontiguousarray(rgb))
        h_deg = hsv[..., 0] * 360.0
        d = np.abs(h_deg - from_h)
        d = np.minimum(d, 360.0 - d)
        w = _smoothstep01(1.0 - np.minimum(d / width, 1.0))

        dh = ((to_h - from_h + 180.0) % 360.0) - 180.0
        h_new = (h_deg + w * amount * dh) % 360.0
        hsv[..., 0] = (h_new / 360.0).astype(np.float32)

        out = hsv_to_rgb(hsv)
        return self._merge(out, alpha)
