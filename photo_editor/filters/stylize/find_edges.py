"""Find Edges filter."""

import cv2
import numpy as np

from ..filter_base import Filter


class FindEdges(Filter):
    """Detect edges using the Sobel operator and output a white-on-black edge map.

    No user-configurable parameters.
    """

    def __init__(self) -> None:
        super().__init__("Find Edges", {})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).astype(np.float32)
        alpha = self._alpha(image)

        # Convert to greyscale for edge detection.
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

        # Sobel gradients in X and Y.
        sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)

        # Magnitude.
        magnitude = np.sqrt(sobel_x ** 2 + sobel_y ** 2)

        # Normalise to [0, 1].
        mag_max = magnitude.max()
        if mag_max > 0:
            magnitude = magnitude / mag_max

        # Produce an inverted edge map (white edges on black).
        edges_3ch = np.stack([magnitude] * 3, axis=-1).astype(np.float32)

        return self._merge(edges_3ch, alpha)
