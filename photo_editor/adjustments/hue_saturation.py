"""Hue / Saturation / Lightness non-destructive adjustment."""

import numpy as np

from .adjustment_base import Adjustment
from ..utils.color_utils import rgb_to_hsl, hsl_to_rgb


class HueSaturation(Adjustment):
    """Shift hue, saturation, and lightness globally.

    Operates in HSL colour space to provide perceptually meaningful
    adjustments.
    """

    def __init__(self) -> None:
        super().__init__(
            "Hue/Saturation",
            {"hue": 0, "saturation": 0, "lightness": 0},
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image)
        alpha = self._alpha(image)

        hue = float(params.get("hue", 0))             # [-180, 180] degrees
        saturation = float(params.get("saturation", 0))  # [-100, 100]
        lightness = float(params.get("lightness", 0))    # [-100, 100]

        if hue == 0 and saturation == 0 and lightness == 0:
            return image.copy()

        hsl = rgb_to_hsl(rgb)
        h, s, l = hsl[..., 0], hsl[..., 1], hsl[..., 2]

        # Hue rotation (normalised 0-1, where 1 = 360°)
        if hue != 0:
            h = (h + hue / 360.0) % 1.0

        # Saturation shift
        if saturation != 0:
            factor = saturation / 100.0
            if factor > 0:
                s = s + (1.0 - s) * factor  # boost toward 1
            else:
                s = s * (1.0 + factor)       # reduce toward 0

        # Lightness shift
        if lightness != 0:
            shift = lightness / 100.0
            if shift > 0:
                l = l + (1.0 - l) * shift
            else:
                l = l * (1.0 + shift)

        s = np.clip(s, 0.0, 1.0)
        l = np.clip(l, 0.0, 1.0)

        result = hsl_to_rgb(np.stack([h, s, l], axis=-1))
        return self._merge(result, alpha)
