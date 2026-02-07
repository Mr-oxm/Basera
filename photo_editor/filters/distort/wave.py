"""Wave distortion filter."""

import cv2
import numpy as np

from ..filter_base import Filter


class Wave(Filter):
    """Distort the image using a wave function.

    Parameters
    ----------
    amplitude : int
        Wave amplitude in pixels, range [1, 999].
    wavelength : int
        Wavelength in pixels, range [1, 999].
    type : str
        Wave type: ``"sine"``, ``"triangle"``, or ``"square"``.
    """

    def __init__(self) -> None:
        super().__init__(
            "Wave",
            {"amplitude": 20, "wavelength": 120, "type": "sine"},
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _wave_func(t: np.ndarray, wave_type: str) -> np.ndarray:
        """Return values in [-1, 1] for a given wave type."""
        if wave_type == "triangle":
            return 2.0 * np.abs(2.0 * (t / (2 * np.pi) - np.floor(t / (2 * np.pi) + 0.5))) - 1.0
        elif wave_type == "square":
            return np.sign(np.sin(t)).astype(np.float32)
        else:  # sine (default)
            return np.sin(t).astype(np.float32)

    # ------------------------------------------------------------------
    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).astype(np.float32)
        alpha = self._alpha(image)

        amplitude = int(params.get("amplitude", self.default_params["amplitude"]))
        wavelength = int(params.get("wavelength", self.default_params["wavelength"]))
        wave_type = str(params.get("type", self.default_params["type"])).lower()
        amplitude = max(1, min(amplitude, 999))
        wavelength = max(1, min(wavelength, 999))
        if wave_type not in ("sine", "triangle", "square"):
            wave_type = "sine"

        h, w = rgb.shape[:2]
        x_coords, y_coords = np.meshgrid(np.arange(w), np.arange(h))
        x_coords = x_coords.astype(np.float32)
        y_coords = y_coords.astype(np.float32)

        freq = 2.0 * np.pi / wavelength
        # Horizontal displacement driven by vertical position.
        dx = amplitude * self._wave_func(freq * y_coords, wave_type)

        map_x = x_coords + dx
        map_y = y_coords

        distorted = cv2.remap(
            rgb, map_x, map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        )

        alpha_f = alpha.astype(np.float32)
        alpha_out = cv2.remap(
            alpha_f, map_x, map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        )
        if alpha_out.ndim == 2:
            alpha_out = alpha_out[..., np.newaxis]

        return self._merge(distorted, alpha_out)
