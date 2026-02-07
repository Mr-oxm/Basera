"""Gradient Map non-destructive adjustment — slider-friendly interface."""

import numpy as np

from .adjustment_base import Adjustment


class GradientMap(Adjustment):
    """Map image luminance to a two-colour gradient.

    Shadow and highlight colours are specified as individual R/G/B
    sliders (0-255 range), making the dialog fully interactive.
    """

    def __init__(self) -> None:
        super().__init__(
            "Gradient Map",
            {
                "shadow_r": 0, "shadow_g": 0, "shadow_b": 0,
                "highlight_r": 255, "highlight_g": 255, "highlight_b": 255,
            },
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image)
        alpha = self._alpha(image)

        sr = params.get("shadow_r", 0) / 255.0
        sg = params.get("shadow_g", 0) / 255.0
        sb = params.get("shadow_b", 0) / 255.0
        hr = params.get("highlight_r", 255) / 255.0
        hg = params.get("highlight_g", 255) / 255.0
        hb = params.get("highlight_b", 255) / 255.0

        # Luminance (Rec. 709)
        lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
        lum = np.clip(lum, 0, 1)

        result = np.empty_like(rgb)
        result[..., 0] = sr + lum * (hr - sr)
        result[..., 1] = sg + lum * (hg - sg)
        result[..., 2] = sb + lum * (hb - sb)

        return self._merge(result, alpha)
