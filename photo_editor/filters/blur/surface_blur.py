"""Surface Blur filter (edge-preserving blur)."""

import cv2
import numpy as np

from ..filter_base import Filter


class SurfaceBlur(Filter):
    """Edge-preserving blur similar to Photoshop's Surface Blur.

    Uses bilateral filtering under the hood.

    Parameters
    ----------
    radius : int
        Spatial extent of the blur, range [1, 100].
    threshold : int
        Colour-difference threshold, range [1, 255].
        Pixels with colour differences above this are not blurred together.
    """

    def __init__(self) -> None:
        super().__init__("Surface Blur", {"radius": 5, "threshold": 15})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image)
        alpha = self._alpha(image)

        radius = int(params.get("radius", self.default_params["radius"]))
        threshold = int(params.get("threshold", self.default_params["threshold"]))
        radius = max(1, min(radius, 100))
        threshold = max(1, min(threshold, 255))

        # Convert to 0-255 for bilateral filter, which works best in uint8.
        rgb_u8 = np.clip(rgb * 255, 0, 255).astype(np.uint8)

        # Diameter: OpenCV bilateral uses d = 2*radius + 1 when d > 0.
        d = 2 * radius + 1
        if d > 300:
            d = -1  # let OpenCV choose based on sigma

        sigma_color = float(threshold)
        sigma_space = float(radius)

        blurred_u8 = cv2.bilateralFilter(rgb_u8, d, sigma_color, sigma_space)

        blurred = blurred_u8.astype(np.float32) / 255.0
        return self._merge(blurred, alpha)
