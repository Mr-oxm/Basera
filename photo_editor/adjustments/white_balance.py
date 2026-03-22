"""White balance — temperature (blue↔amber) and tint (green↔magenta)."""

from __future__ import annotations

import numpy as np

from .adjustment_base import Adjustment


def estimate_wb_from_sample(r: float, g: float, b: float) -> tuple[int, int]:
    """Infer temperature / tint from a pixel that should read as neutral gray."""
    eps = 1e-4
    avg = (r + g + b) / 3.0
    if avg < eps:
        return 0, 0
    dr = r / avg
    dg = g / avg
    db = b / avg
    temperature = int(np.clip((dr - db) * 55.0, -100, 100))
    tint = int(np.clip((dg - (dr + db) * 0.5) * 70.0, -100, 100))
    return temperature, tint


class WhiteBalance(Adjustment):
    """Temperature and tint in [-100, 100] (UI percent style)."""

    def __init__(self) -> None:
        super().__init__(
            "White Balance",
            {"temperature": 0, "tint": 0},
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).copy()
        alpha = self._alpha(image)

        t = float(np.clip(params.get("temperature", 0), -100, 100)) / 100.0
        ti = float(np.clip(params.get("tint", 0), -100, 100)) / 100.0

        if abs(t) < 1e-6 and abs(ti) < 1e-6:
            return image.copy()

        # Temperature: warm (+t) boosts R, cuts B.
        rgb[..., 0] *= np.float32(1.0 + 0.14 * t)
        rgb[..., 2] *= np.float32(1.0 - 0.14 * t)
        # Tint: green (+ti) boosts G slightly, pulls R/B; magenta does the opposite.
        rgb[..., 1] *= np.float32(1.0 + 0.10 * ti)
        rgb[..., 0] *= np.float32(1.0 - 0.04 * ti)
        rgb[..., 2] *= np.float32(1.0 - 0.04 * ti)

        return self._merge(rgb, alpha)
