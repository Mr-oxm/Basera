"""Threshold non-destructive adjustment."""

import numpy as np

from .adjustment_base import Adjustment


class Threshold(Adjustment):
    """Convert the image to pure black and white using a luminance
    threshold.

    Pixels with luminance at or above the threshold become white;
    those below become black.

    Parameters
    ----------
    threshold : int
        Threshold value in [0, 255].
    """

    def __init__(self) -> None:
        super().__init__("Threshold", {"threshold": 128})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image)
        alpha = self._alpha(image)

        thresh = float(params.get("threshold", 128)) / 255.0

        # Rec. 709 luminance
        lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]

        bw = np.where(lum >= thresh, np.float32(1.0), np.float32(0.0))
        result = np.stack([bw, bw, bw], axis=-1)

        return self._merge(result, alpha)
