"""Posterize non-destructive adjustment."""

import numpy as np

from .adjustment_base import Adjustment


class Posterize(Adjustment):
    """Reduce the number of tonal levels per channel.

    Quantises each channel into *levels* discrete steps, producing a
    flat, poster-like appearance.

    Parameters
    ----------
    levels : int
        Number of tonal levels per channel, in [2, 255].
    """

    def __init__(self) -> None:
        super().__init__("Posterize", {"levels": 4})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image)
        alpha = self._alpha(image)

        levels = int(params.get("levels", 4))
        levels = max(2, min(levels, 255))

        # Quantise: floor(value * (levels - 1)) / (levels - 1)
        n = np.float32(levels - 1)
        result = np.floor(rgb * n + 0.5) / n

        return self._merge(result, alpha)
