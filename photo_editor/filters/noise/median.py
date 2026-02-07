"""Median filter."""

import cv2
import numpy as np

from ..filter_base import Filter


class MedianFilter(Filter):
    """Apply a median filter to smooth noise while preserving edges.

    Parameters
    ----------
    radius : int
        Filter radius, range [1, 50].  Kernel size is ``2 * radius + 1``.
    """

    def __init__(self) -> None:
        super().__init__("Median", {"radius": 1})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image)
        alpha = self._alpha(image)

        radius = int(params.get("radius", self.default_params["radius"]))
        radius = max(1, min(radius, 50))

        ksize = 2 * radius + 1

        # cv2.medianBlur works on uint8.
        rgb_u8 = np.clip(rgb * 255, 0, 255).astype(np.uint8)
        filtered_u8 = cv2.medianBlur(rgb_u8, ksize)

        filtered = filtered_u8.astype(np.float32) / 255.0
        return self._merge(filtered, alpha)
