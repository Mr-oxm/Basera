"""Sharpen filter."""

import cv2
import numpy as np

from ..filter_base import Filter


class Sharpen(Filter):
    """Basic sharpening using a convolution kernel.

    Parameters
    ----------
    amount : int
        Sharpening strength as a percentage, range [1, 500].
        100 = standard sharpen kernel; higher values intensify the effect.
    """

    def __init__(self) -> None:
        super().__init__("Sharpen", {"amount": 100})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).astype(np.float32)
        alpha = self._alpha(image)

        amount = int(params.get("amount", self.default_params["amount"]))
        amount = max(1, min(amount, 500))
        strength = amount / 100.0

        # Classic 3x3 sharpen kernel (identity + laplacian-style edges).
        kernel = np.array(
            [[0, -1, 0],
             [-1, 5, -1],
             [0, -1, 0]],
            dtype=np.float32,
        )

        sharpened = cv2.filter2D(rgb, -1, kernel)

        # Blend original with sharpened based on strength.
        result = cv2.addWeighted(rgb, 1.0 - strength, sharpened, strength, 0)

        return self._merge(result, alpha)
