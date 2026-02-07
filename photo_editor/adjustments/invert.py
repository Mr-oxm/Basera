"""Invert non-destructive adjustment."""

import numpy as np

from .adjustment_base import Adjustment


class Invert(Adjustment):
    """Invert (negate) the RGB channels of the image.

    Alpha is preserved.  No parameters needed.
    """

    def __init__(self) -> None:
        super().__init__("Invert", {})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image)
        alpha = self._alpha(image)

        result = 1.0 - rgb

        return self._merge(result, alpha)
