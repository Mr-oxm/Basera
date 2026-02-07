"""Unsharp Mask filter."""

import cv2
import numpy as np

from ..filter_base import Filter


class UnsharpMask(Filter):
    """Unsharp Mask sharpening (blur-subtract method).

    Parameters
    ----------
    amount : int
        Sharpening strength as percentage, range [1, 500].
    radius : float
        Gaussian blur radius used to create the mask, range [0.1, 250].
    threshold : int
        Minimum brightness difference to sharpen (0-255 scale),
        range [0, 255].
    """

    def __init__(self) -> None:
        super().__init__(
            "Unsharp Mask",
            {"amount": 100, "radius": 1.0, "threshold": 0},
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).astype(np.float32)
        alpha = self._alpha(image)

        amount = int(params.get("amount", self.default_params["amount"]))
        radius = float(params.get("radius", self.default_params["radius"]))
        threshold = int(params.get("threshold", self.default_params["threshold"]))

        amount = max(1, min(amount, 500))
        radius = max(0.1, min(radius, 250.0))
        threshold = max(0, min(threshold, 255))

        strength = amount / 100.0
        sigma = radius / 2.0
        ksize = int(np.ceil(sigma * 6)) | 1
        ksize = max(3, ksize)

        blurred = cv2.GaussianBlur(rgb, (ksize, ksize), sigmaX=sigma, sigmaY=sigma)

        # Unsharp mask: sharpened = original + strength * (original - blurred)
        diff = rgb - blurred

        # Apply threshold (in 0-1 space; convert threshold from 0-255).
        thresh_f = threshold / 255.0
        if thresh_f > 0:
            mask = np.abs(diff).max(axis=-1, keepdims=True) >= thresh_f
            diff = diff * mask.astype(np.float32)

        result = rgb + strength * diff
        return self._merge(result, alpha)
