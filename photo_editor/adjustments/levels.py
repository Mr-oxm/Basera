"""Levels non-destructive adjustment."""

import numpy as np

from .adjustment_base import Adjustment


class Levels(Adjustment):
    """Photoshop-style Levels adjustment.

    Remaps the tonal range of an image through input levels, gamma
    correction, and output levels.
    """

    def __init__(self) -> None:
        super().__init__(
            "Levels",
            {
                "input_black": 0,
                "input_white": 255,
                "gamma": 1.0,
                "output_black": 0,
                "output_white": 255,
            },
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).copy()
        alpha = self._alpha(image)

        # Read and normalise parameters from [0,255] → [0,1]
        in_black = float(params.get("input_black", 0)) / 255.0
        in_white = float(params.get("input_white", 255)) / 255.0
        gamma = float(params.get("gamma", 1.0))
        out_black = float(params.get("output_black", 0)) / 255.0
        out_white = float(params.get("output_white", 255)) / 255.0

        gamma = np.clip(gamma, 0.1, 10.0)
        in_range = max(in_white - in_black, 1e-6)

        # Step 1 – input remap
        rgb = (rgb - in_black) / in_range
        rgb = np.clip(rgb, 0.0, 1.0)

        # Step 2 – gamma correction
        if abs(gamma - 1.0) > 1e-6:
            rgb = np.power(rgb, 1.0 / gamma)

        # Step 3 – output remap
        rgb = rgb * (out_white - out_black) + out_black

        return self._merge(rgb, alpha)
