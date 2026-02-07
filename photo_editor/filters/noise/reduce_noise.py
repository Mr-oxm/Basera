"""Reduce Noise filter."""

import cv2
import numpy as np

from ..filter_base import Filter


class ReduceNoise(Filter):
    """Reduce image noise using Non-Local Means denoising.

    Parameters
    ----------
    strength : float
        Filter strength, range [0, 10].  Higher values remove more
        noise but may also remove detail.
    """

    def __init__(self) -> None:
        super().__init__("Reduce Noise", {"strength": 3.0})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image)
        alpha = self._alpha(image)

        strength = float(params.get("strength", self.default_params["strength"]))
        strength = max(0.0, min(strength, 10.0))

        # Convert to uint8 for cv2.fastNlMeansDenoisingColored.
        rgb_u8 = np.clip(rgb * 255, 0, 255).astype(np.uint8)

        # h parameter controls filter strength (luminance).
        h = strength * 3.0  # scale to a useful range for the API
        h_color = h

        # Template and search window sizes (must be odd).
        template_window = 7
        search_window = 21

        denoised_u8 = cv2.fastNlMeansDenoisingColored(
            rgb_u8,
            None,
            h,
            h_color,
            template_window,
            search_window,
        )

        denoised = denoised_u8.astype(np.float32) / 255.0
        return self._merge(denoised, alpha)
