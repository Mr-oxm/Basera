"""Radial (Spin / Zoom) Blur filter."""

import cv2
import numpy as np

from ..filter_base import Filter


class RadialBlur(Filter):
    """Apply a radial (zoom) blur emanating from a centre point.

    Parameters
    ----------
    amount : int
        Blur strength, range [1, 100].
    center_x : float
        Normalised X centre [0, 1]. Default 0.5.
    center_y : float
        Normalised Y centre [0, 1]. Default 0.5.
    """

    def __init__(self) -> None:
        super().__init__(
            "Radial Blur",
            {"amount": 10, "center_x": 0.5, "center_y": 0.5},
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).astype(np.float32)
        alpha = self._alpha(image)

        amount = int(params.get("amount", self.default_params["amount"]))
        cx = float(params.get("center_x", self.default_params["center_x"]))
        cy = float(params.get("center_y", self.default_params["center_y"]))
        amount = max(1, min(amount, 100))
        cx = max(0.0, min(cx, 1.0))
        cy = max(0.0, min(cy, 1.0))

        h, w = rgb.shape[:2]
        center = np.array([cx * w, cy * h], dtype=np.float32)

        # Number of accumulation steps scales with amount.
        steps = max(2, amount)
        result = np.zeros_like(rgb, dtype=np.float64)

        for i in range(steps):
            factor = 1.0 + (i / steps) * (amount / 100.0)
            # Build an affine scale matrix centred on *center*.
            m = np.array(
                [
                    [factor, 0, center[0] * (1 - factor)],
                    [0, factor, center[1] * (1 - factor)],
                ],
                dtype=np.float32,
            )
            warped = cv2.warpAffine(
                rgb, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
            )
            result += warped.astype(np.float64)

        result = (result / steps).astype(np.float32)
        return self._merge(result, alpha)
