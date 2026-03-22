"""Curves non-destructive adjustment — RGB composite plus per-channel curves."""

from __future__ import annotations

import numpy as np

from .adjustment_base import Adjustment

_CHANNEL_SET = frozenset({"RGB", "Red", "Green", "Blue"})
_IDENTITY_POINTS: list[list[int]] = [[0, 0], [255, 255]]


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


def _legacy_sliders_to_points(shadows: int, midtones: int, highlights: int) -> list[list[int]]:
    shd = int(shadows)
    mid = int(midtones)
    hlt = int(highlights)
    pts_x = [0, 64, 128, 192, 255]
    pts_y = [
        max(0, min(255, 0 + shd)),
        max(0, min(255, 64 + int(shd * 0.5))),
        max(0, min(255, 128 + mid)),
        max(0, min(255, 192 + int(hlt * 0.5))),
        max(0, min(255, 255 + hlt)),
    ]
    return [[pts_x[i], pts_y[i]] for i in range(5)]


def sanitize_curve_points(raw: list | None) -> list[list[int]]:
    """Return sorted control points with pinned ends at x=0 and x=255."""
    if not raw:
        return list(map(list, _IDENTITY_POINTS))
    pts: list[list[int]] = []
    for p in raw:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            continue
        x = int(np.clip(float(p[0]), 0, 255))
        y = int(np.clip(float(p[1]), 0, 255))
        pts.append([x, y])
    if len(pts) < 2:
        return list(map(list, _IDENTITY_POINTS))
    pts.sort(key=lambda t: t[0])
    pts[0] = [0, pts[0][1]]
    pts[-1] = [255, pts[-1][1]]
    out: list[list[int]] = [list(pts[0])]
    for p in pts[1:]:
        if p[0] == out[-1][0]:
            out[-1][1] = p[1]
        else:
            out.append(list(p))
    return out


def build_lut_y(points: list[list[int]]) -> np.ndarray:
    """256-element float array mapping input 0–255 → output 0–1."""
    pts = sanitize_curve_points(points)
    xs = np.array([p[0] for p in pts], dtype=np.float64)
    ys = np.array([p[1] for p in pts], dtype=np.float64)
    lut_x = np.arange(256, dtype=np.float64)
    lut_y = _monotonic_cubic_spline(xs, ys, lut_x)
    return np.clip(lut_y, 0, 255) / 255.0


def eval_curve_y(points: list[list[int]], x: float) -> float:
    """Evaluate curve at scalar x in [0, 255]."""
    pts = sanitize_curve_points(points)
    xs = np.array([p[0] for p in pts], dtype=np.float64)
    ys = np.array([p[1] for p in pts], dtype=np.float64)
    xv = np.array([float(x)], dtype=np.float64)
    y = _monotonic_cubic_spline(xs, ys, xv)[0]
    return float(np.clip(y, 0, 255))


def coerce_curve_bundle(params: dict | None) -> dict:
    """Normalize to channel (UI) + four curves: RGB composite then R / G / B.

    Order of application: RGB curve on each channel value, then Red / Green / Blue
    curves on the respective outputs (Photoshop-style stacking).
    """
    if params is None:
        params = {}
    identity = sanitize_curve_points(_IDENTITY_POINTS)
    keys = ("points_rgb", "points_red", "points_green", "points_blue")

    def _ch() -> str:
        ch = params.get("channel", "RGB")
        return ch if ch in _CHANNEL_SET else "RGB"

    if all(isinstance(params.get(k), list) and len(params.get(k) or []) >= 2 for k in keys):
        return {
            "channel": _ch(),
            "points_rgb": sanitize_curve_points(params["points_rgb"]),
            "points_red": sanitize_curve_points(params["points_red"]),
            "points_green": sanitize_curve_points(params["points_green"]),
            "points_blue": sanitize_curve_points(params["points_blue"]),
        }

    if isinstance(params.get("points"), list) and len(params["points"]) >= 2:
        ch = _ch()
        pts = sanitize_curve_points(params["points"])
        out = {k: list(map(list, identity)) for k in keys}
        if ch == "RGB":
            out["points_rgb"] = pts
        elif ch == "Red":
            out["points_red"] = pts
        elif ch == "Green":
            out["points_green"] = pts
        else:
            out["points_blue"] = pts
        return {"channel": ch, **out}

    shd = int(params.get("shadows", 0))
    mid = int(params.get("midtones", 0))
    hlt = int(params.get("highlights", 0))
    return {
        "channel": _ch(),
        "points_rgb": _legacy_sliders_to_points(shd, mid, hlt),
        "points_red": list(map(list, identity)),
        "points_green": list(map(list, identity)),
        "points_blue": list(map(list, identity)),
    }


class Curves(Adjustment):
    """Tone curves: RGB composite plus independent R / G / B curves."""

    def __init__(self) -> None:
        super().__init__(
            "Curves",
            {
                "channel": "RGB",
                "points_rgb": list(map(list, _IDENTITY_POINTS)),
                "points_red": list(map(list, _IDENTITY_POINTS)),
                "points_green": list(map(list, _IDENTITY_POINTS)),
                "points_blue": list(map(list, _IDENTITY_POINTS)),
            },
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).copy()
        alpha = self._alpha(image)
        b = coerce_curve_bundle(params)

        idx0 = np.clip((rgb * 255.0).astype(np.int32), 0, 255)
        lut_rgb = build_lut_y(b["points_rgb"])
        lut_r = build_lut_y(b["points_red"])
        lut_g = build_lut_y(b["points_green"])
        lut_b = build_lut_y(b["points_blue"])

        r1 = lut_rgb[idx0[..., 0]]
        g1 = lut_rgb[idx0[..., 1]]
        b1 = lut_rgb[idx0[..., 2]]

        idx_r = np.clip((r1 * 255.0).astype(np.int32), 0, 255)
        idx_g = np.clip((g1 * 255.0).astype(np.int32), 0, 255)
        idx_b = np.clip((b1 * 255.0).astype(np.int32), 0, 255)

        rgb[..., 0] = lut_r[idx_r].astype(np.float32)
        rgb[..., 1] = lut_g[idx_g].astype(np.float32)
        rgb[..., 2] = lut_b[idx_b].astype(np.float32)

        return self._merge(rgb, alpha)
