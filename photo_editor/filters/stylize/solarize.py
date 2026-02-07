"""Solarize filter."""

import numpy as np

from ..filter_base import Filter


class Solarize(Filter):
    """Invert tones above the given threshold (Sabattier effect).

    Parameters
    ----------
    threshold : int
        Brightness threshold (0-255), range [0, 255].
        Pixels brighter than this value are inverted.
    """

    def __init__(self) -> None:
        super().__init__("Solarize", {"threshold": 128})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).astype(np.float32)
        alpha = self._alpha(image)

        threshold = int(params.get("threshold", self.default_params["threshold"]))
        threshold = max(0, min(threshold, 255))

        # Convert threshold to 0-1 range.
        thresh_f = threshold / 255.0

        # Where pixel > threshold, invert it.
        mask = rgb > thresh_f
        result = np.where(mask, 1.0 - rgb, rgb)

        return self._merge(result, alpha)
