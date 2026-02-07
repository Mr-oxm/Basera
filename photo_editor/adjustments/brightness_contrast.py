"""Brightness and Contrast non-destructive adjustment."""

import numpy as np

from .adjustment_base import Adjustment


class BrightnessContrast(Adjustment):
    """Adjust image brightness and contrast.

    Brightness shifts pixel values linearly.
    Contrast scales deviation from mid-grey using a tangent-based curve
    that mimics Photoshop behaviour.
    """

    def __init__(self) -> None:
        super().__init__(
            "Brightness/Contrast",
            {"brightness": 0, "contrast": 0},
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).copy()
        alpha = self._alpha(image)

        brightness = float(params.get("brightness", 0))  # [-100, 100]
        contrast = float(params.get("contrast", 0))       # [-100, 100]

        # --- brightness (linear shift, normalised to 0-1) ---
        if brightness != 0:
            rgb += brightness / 100.0

        # --- contrast (tan-based curve) ---
        if contrast != 0:
            # Map [-100, 100] → factor via tan curve (avoid ±90° singularity)
            con = np.clip(contrast, -100, 100)
            factor = np.tan((con / 100.0) * (np.pi / 4.0) + np.pi / 4.0)
            rgb = (rgb - 0.5) * factor + 0.5

        return self._merge(rgb, alpha)
