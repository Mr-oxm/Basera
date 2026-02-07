"""Ripple distortion filter."""

import cv2
import numpy as np

from ..filter_base import Filter


class Ripple(Filter):
    """Distort the image with a ripple / wave pattern.

    Displaces pixels using a sinusoidal function along both axes.

    Parameters
    ----------
    amount : int
        Displacement amplitude in pixels, range [1, 999].
    wavelength : int
        Ripple wavelength in pixels, range [1, 999].
    """

    def __init__(self) -> None:
        super().__init__("Ripple", {"amount": 10, "wavelength": 100})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).astype(np.float32)
        alpha = self._alpha(image)

        amount = int(params.get("amount", self.default_params["amount"]))
        wavelength = int(params.get("wavelength", self.default_params["wavelength"]))
        amount = max(1, min(amount, 999))
        wavelength = max(1, min(wavelength, 999))

        h, w = rgb.shape[:2]

        # Create coordinate grids.
        x_coords, y_coords = np.meshgrid(np.arange(w), np.arange(h))
        x_coords = x_coords.astype(np.float32)
        y_coords = y_coords.astype(np.float32)

        # Sinusoidal displacement.
        freq = 2.0 * np.pi / wavelength
        dx = amount * np.sin(freq * y_coords)
        dy = amount * np.sin(freq * x_coords)

        map_x = x_coords + dx.astype(np.float32)
        map_y = y_coords + dy.astype(np.float32)

        distorted = cv2.remap(
            rgb, map_x, map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        )

        # Also remap alpha.
        alpha_f = alpha.astype(np.float32)
        alpha_distorted = cv2.remap(
            alpha_f, map_x, map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        )
        if alpha_distorted.ndim == 2:
            alpha_distorted = alpha_distorted[..., np.newaxis]

        return self._merge(distorted, alpha_distorted)
