"""Gaussian Blur filter."""

import cv2
import numpy as np

from ..filter_base import Filter


class GaussianBlur(Filter):
    """Apply a Gaussian blur to the image.

    Parameters
    ----------
    radius : float
        Blur radius in pixels, range [0.1, 250].
    """

    def __init__(self) -> None:
        super().__init__("Gaussian Blur", {"radius": 5.0})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image)
        alpha = self._alpha(image)

        radius = float(params.get("radius", self.default_params["radius"]))
        radius = max(0.1, min(radius, 250.0))

        # Convert sigma from radius; OpenCV uses sigma directly.
        sigma = radius / 2.0

        # Kernel size must be odd and large enough for the sigma.
        ksize = int(np.ceil(sigma * 6)) | 1  # ensure odd
        ksize = max(3, ksize)

        # Work in float32
        rgb_f = rgb.astype(np.float32)
        blurred = cv2.GaussianBlur(rgb_f, (ksize, ksize), sigmaX=sigma, sigmaY=sigma)

        return self._merge(blurred, alpha)
