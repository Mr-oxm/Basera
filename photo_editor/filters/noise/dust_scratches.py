"""Dust & Scratches filter."""

import cv2
import numpy as np

from ..filter_base import Filter


class DustScratches(Filter):
    """Remove dust and scratches by selectively blurring outlier pixels.

    Applies a median filter and then composites the blurred result back
    only where the difference from the original exceeds *threshold*.

    Parameters
    ----------
    radius : int
        Median filter radius, range [1, 20].
    threshold : int
        Brightness-difference threshold (0-255), range [0, 255].
        Only pixels deviating more than this from the median are replaced.
    """

    def __init__(self) -> None:
        super().__init__("Dust & Scratches", {"radius": 3, "threshold": 10})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image)
        alpha = self._alpha(image)

        radius = int(params.get("radius", self.default_params["radius"]))
        threshold = int(params.get("threshold", self.default_params["threshold"]))
        radius = max(1, min(radius, 20))
        threshold = max(0, min(threshold, 255))

        rgb_u8 = np.clip(rgb * 255, 0, 255).astype(np.uint8)

        # Median filter with kernel size = 2*radius + 1 (must be odd).
        ksize = 2 * radius + 1
        median = cv2.medianBlur(rgb_u8, ksize)

        # Compute per-pixel max-channel absolute difference.
        diff = np.abs(rgb_u8.astype(np.int16) - median.astype(np.int16))
        max_diff = diff.max(axis=-1)

        # Build a mask: replace only pixels above the threshold.
        mask = (max_diff > threshold).astype(np.float32)[..., np.newaxis]

        # Blend: use median where mask is 1, original where 0.
        result_u8 = (median.astype(np.float32) * mask +
                     rgb_u8.astype(np.float32) * (1.0 - mask)).astype(np.uint8)

        result = result_u8.astype(np.float32) / 255.0
        return self._merge(result, alpha)
