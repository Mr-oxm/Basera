"""Pinch / Bloat distortion filter."""

import cv2
import numpy as np

from ..filter_base import Filter


class Pinch(Filter):
    """Pinch (positive) or bloat (negative) pixels toward/away from centre.

    Parameters
    ----------
    amount : int
        Distortion amount, range [-100, 100].
        Positive = pinch inward; negative = bloat outward.
    """

    def __init__(self) -> None:
        super().__init__("Pinch", {"amount": 50})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).astype(np.float32)
        alpha = self._alpha(image)

        amount = int(params.get("amount", self.default_params["amount"]))
        amount = max(-100, min(amount, 100))

        h, w = rgb.shape[:2]
        cx, cy = w / 2.0, h / 2.0
        max_radius = min(cx, cy)

        x_coords, y_coords = np.meshgrid(
            np.arange(w, dtype=np.float32),
            np.arange(h, dtype=np.float32),
        )

        dx = x_coords - cx
        dy = y_coords - cy
        dist = np.sqrt(dx * dx + dy * dy)
        norm_dist = dist / max_radius  # [0, ~1.4]

        # Power curve: amount > 0 pinches (exponent > 1), < 0 bloats (< 1).
        strength = amount / 100.0
        # Map strength to exponent.  0 = no change (exp=1).
        if strength >= 0:
            exponent = 1.0 + strength * 2.0  # up to 3
        else:
            exponent = 1.0 / (1.0 - strength * 2.0)  # down to ~0.33

        # New normalised distance.
        safe_norm = np.clip(norm_dist, 0, 1)
        new_norm = np.power(safe_norm, exponent)

        # Scale displacement.
        scale = np.where(norm_dist > 0, new_norm / (norm_dist + 1e-10), 1.0).astype(np.float32)
        # Outside unit circle: no effect.
        scale = np.where(norm_dist > 1.0, 1.0, scale).astype(np.float32)

        map_x = (cx + dx * scale).astype(np.float32)
        map_y = (cy + dy * scale).astype(np.float32)

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
