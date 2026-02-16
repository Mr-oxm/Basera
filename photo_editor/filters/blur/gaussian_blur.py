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
    preserve_alpha : bool
        If True the original alpha channel is kept unchanged;
        if False the alpha is blurred together with the colour,
        letting the blur extend beyond the layer boundary.
    """

    def __init__(self) -> None:
        super().__init__(
            "Gaussian Blur",
            {"radius": 5.0, "preserve_alpha": False},
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        radius = float(params.get("radius", self.default_params["radius"]))
        radius = max(0.1, min(radius, 250.0))
        preserve = bool(params.get("preserve_alpha",
                                   self.default_params["preserve_alpha"]))

        # Convert sigma from radius; OpenCV uses sigma directly.
        sigma = radius / 2.0

        # Kernel size must be odd and large enough for the sigma.
        ksize = int(np.ceil(sigma * 6)) | 1  # ensure odd
        ksize = max(3, ksize)

        # Work in premultiplied-alpha space to avoid dark fringe
        pm, orig_alpha = self._premultiply(image)
        blurred = cv2.GaussianBlur(
            pm, (ksize, ksize), sigmaX=sigma, sigmaY=sigma,
        )

        return self._unpremultiply(blurred, orig_alpha, preserve)
