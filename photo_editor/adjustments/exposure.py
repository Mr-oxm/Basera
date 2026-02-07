"""Exposure non-destructive adjustment."""

import numpy as np

from .adjustment_base import Adjustment


class Exposure(Adjustment):
    """Adjust exposure, offset, and gamma correction.

    Follows the standard compositing pipeline:
    ``result = clamp((image * 2^exposure + offset) ^ (1/gamma))``
    """

    def __init__(self) -> None:
        super().__init__(
            "Exposure",
            {"exposure": 0.0, "offset": 0.0, "gamma": 1.0},
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).copy()
        alpha = self._alpha(image)

        exposure = float(params.get("exposure", 0.0))   # [-5, 5]
        offset = float(params.get("offset", 0.0))       # [-0.5, 0.5]
        gamma = float(params.get("gamma", 1.0))          # [0.01, 9.99]

        gamma = np.clip(gamma, 0.01, 9.99)

        # Exposure multiplier (photographic stops)
        if exposure != 0.0:
            rgb *= np.float32(2.0 ** exposure)

        # Offset (additive shift)
        if offset != 0.0:
            rgb += np.float32(offset)

        # Gamma (power curve on non-negative values)
        if abs(gamma - 1.0) > 1e-6:
            rgb = np.clip(rgb, 0.0, None)
            inv_gamma = np.float32(1.0 / gamma)
            rgb = np.power(rgb, inv_gamma)

        return self._merge(rgb, alpha)
