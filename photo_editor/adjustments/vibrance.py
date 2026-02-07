"""Vibrance non-destructive adjustment."""

import numpy as np

from .adjustment_base import Adjustment


class Vibrance(Adjustment):
    """Vibrance intelligently boosts saturation of muted colours more
    than already-saturated ones, protecting skin tones.

    The algorithm computes per-pixel saturation and applies a variable
    boost that is inversely proportional to the existing saturation,
    producing a more natural look than uniform saturation changes.
    """

    def __init__(self) -> None:
        super().__init__("Vibrance", {"vibrance": 0})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).copy()
        alpha = self._alpha(image)

        vibrance = float(params.get("vibrance", 0))  # [-100, 100]
        if vibrance == 0:
            return image.copy()

        amount = vibrance / 100.0  # normalise to [-1, 1]

        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]

        # Per-pixel max and min
        mx = np.maximum(np.maximum(r, g), b)
        mn = np.minimum(np.minimum(r, g), b)

        # Saturation proxy (0 = grey, 1 = fully saturated)
        sat = np.where(mx > 1e-6, (mx - mn) / mx, 0.0)

        # Variable boost: less-saturated pixels receive more adjustment
        # (1 - sat) maps fully-saturated → 0 boost, grey → full boost
        boost = amount * (1.0 - sat) * 2.0

        # Luminance (Rec. 709)
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        lum = lum[..., np.newaxis]

        # Interpolate between luminance (desaturated) and colour
        # boost > 0 → move away from lum, boost < 0 → move toward lum
        rgb = rgb + (rgb - lum) * boost[..., np.newaxis]

        return self._merge(rgb, alpha)
