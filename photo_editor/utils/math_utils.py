"""Math and geometry helpers."""

import numpy as np


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def remap(value: float, in_lo: float, in_hi: float, out_lo: float, out_hi: float) -> float:
    t = (value - in_lo) / max(in_hi - in_lo, 1e-10)
    return lerp(out_lo, out_hi, t)


def gaussian_kernel(size: int, sigma: float) -> np.ndarray:
    """1-D Gaussian kernel, normalised."""
    x = np.arange(size) - size // 2
    k = np.exp(-0.5 * (x / max(sigma, 1e-6)) ** 2)
    return (k / k.sum()).astype(np.float32)


def distance_field(w: int, h: int, cx: float, cy: float) -> np.ndarray:
    """Euclidean distance from (cx, cy) for every pixel."""
    yy, xx = np.mgrid[:h, :w]
    return np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2).astype(np.float32)


def normalize_array(arr: np.ndarray) -> np.ndarray:
    lo, hi = arr.min(), arr.max()
    if hi - lo < 1e-10:
        return np.zeros_like(arr)
    return ((arr - lo) / (hi - lo)).astype(np.float32)


def rotation_matrix(angle_deg: float) -> np.ndarray:
    r = np.radians(angle_deg)
    c, s = np.cos(r), np.sin(r)
    return np.array([[c, -s], [s, c]], dtype=np.float32)
