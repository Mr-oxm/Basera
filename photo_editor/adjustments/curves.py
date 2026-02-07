"""Curves non-destructive adjustment (simplified 3-slider interface)."""

import numpy as np

from .adjustment_base import Adjustment


def _monotonic_cubic_spline(xs: np.ndarray, ys: np.ndarray, x_eval: np.ndarray) -> np.ndarray:
    """Fritsch-Carlson monotonic cubic Hermite interpolation."""
    n = len(xs)
    if n < 2:
        return np.full_like(x_eval, ys[0] if n == 1 else 0.0)
    if n == 2:
        slope = (ys[1] - ys[0]) / max(xs[1] - xs[0], 1e-10)
        return ys[0] + slope * (x_eval - xs[0])

    h = np.diff(xs).astype(np.float64)
    h[h < 1e-10] = 1e-10
    delta = np.diff(ys) / h

    m = np.zeros(n, dtype=np.float64)
    m[0] = delta[0]
    m[-1] = delta[-1]
    for k in range(1, n - 1):
        if delta[k - 1] * delta[k] <= 0:
            m[k] = 0.0
        else:
            m[k] = (delta[k - 1] + delta[k]) * 0.5

    for k in range(n - 1):
        if abs(delta[k]) < 1e-10:
            m[k] = 0.0
            m[k + 1] = 0.0
        else:
            alpha = m[k] / delta[k]
            beta = m[k + 1] / delta[k]
            mag = alpha ** 2 + beta ** 2
            if mag > 9.0:
                tau = 3.0 / np.sqrt(mag)
                m[k] = tau * alpha * delta[k]
                m[k + 1] = tau * beta * delta[k]

    result = np.empty_like(x_eval, dtype=np.float64)
    indices = np.searchsorted(xs, x_eval, side="right") - 1
    indices = np.clip(indices, 0, n - 2)
    for k in range(n - 1):
        mask = indices == k
        if not np.any(mask):
            continue
        t = (x_eval[mask] - xs[k]) / h[k]
        t2 = t * t
        t3 = t2 * t
        h00 = 2 * t3 - 3 * t2 + 1
        h10 = t3 - 2 * t2 + t
        h01 = -2 * t3 + 3 * t2
        h11 = t3 - t2
        result[mask] = (h00 * ys[k] + h10 * h[k] * m[k]
                        + h01 * ys[k + 1] + h11 * h[k] * m[k + 1])
    return result


class Curves(Adjustment):
    """Curves adjustment with intuitive shadow/midtone/highlight sliders.

    Sliders range from -100 to +100.  Internally they are converted to
    five control-point spline positions to match the classic Photoshop
    behaviour.
    """

    def __init__(self) -> None:
        super().__init__(
            "Curves",
            {"shadows": 0, "midtones": 0, "highlights": 0},
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image)
        alpha = self._alpha(image)

        shd = params.get("shadows", 0)
        mid = params.get("midtones", 0)
        hlt = params.get("highlights", 0)

        # Build 5-point curve from sliders
        pts_x = np.array([0, 64, 128, 192, 255], dtype=np.float64)
        pts_y = np.array([
            max(0, min(255, 0 + shd)),
            max(0, min(255, 64 + int(shd * 0.5))),
            max(0, min(255, 128 + mid)),
            max(0, min(255, 192 + int(hlt * 0.5))),
            max(0, min(255, 255 + hlt)),
        ], dtype=np.float64)

        lut_x = np.arange(256, dtype=np.float64)
        lut_y = _monotonic_cubic_spline(pts_x, pts_y, lut_x)
        lut_y = np.clip(lut_y, 0, 255) / 255.0

        idx = np.clip((rgb * 255).astype(np.int32), 0, 255)
        result = lut_y[idx].astype(np.float32)
        return self._merge(result, alpha)
