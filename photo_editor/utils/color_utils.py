"""Color-space conversion utilities (vectorised NumPy)."""

import numpy as np


def rgb_to_hsl(rgb: np.ndarray) -> np.ndarray:
    """Convert RGB [0,1] → HSL [0,1].  Last axis = 3."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    l = (mx + mn) * 0.5
    d = mx - mn
    s = np.where(d > 0, np.where(l > 0.5, d / (2 - mx - mn + 1e-10), d / (mx + mn + 1e-10)), 0)
    h = np.zeros_like(l)
    safe = np.where(d > 0, d, 1)
    h = np.where((mx == r) & (d > 0), ((g - b) / safe) % 6, h)
    h = np.where((mx == g) & (d > 0), (b - r) / safe + 2, h)
    h = np.where((mx == b) & (d > 0), (r - g) / safe + 4, h)
    h /= 6.0
    return np.stack([h, s, l], axis=-1).astype(np.float32)


def hsl_to_rgb(hsl: np.ndarray) -> np.ndarray:
    """Convert HSL [0,1] → RGB [0,1]."""
    h, s, l = hsl[..., 0], hsl[..., 1], hsl[..., 2]
    c = (1 - np.abs(2 * l - 1)) * s
    x = c * (1 - np.abs((h * 6) % 2 - 1))
    m = l - c * 0.5
    h6 = (h * 6).astype(np.int32) % 6
    z = np.zeros_like(c)
    r = np.select([h6 == 0, h6 == 1, h6 == 2, h6 == 3, h6 == 4, h6 == 5], [c, x, z, z, x, c])
    g = np.select([h6 == 0, h6 == 1, h6 == 2, h6 == 3, h6 == 4, h6 == 5], [x, c, c, x, z, z])
    b = np.select([h6 == 0, h6 == 1, h6 == 2, h6 == 3, h6 == 4, h6 == 5], [z, z, x, c, c, x])
    return np.clip(np.stack([r + m, g + m, b + m], axis=-1), 0, 1).astype(np.float32)


def rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
    """Convert RGB [0,1] → HSV [0,1]."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    d = mx - mn
    v = mx
    s = np.where(mx > 0, d / (mx + 1e-10), 0)
    safe = np.where(d > 0, d, 1)
    h = np.zeros_like(v)
    h = np.where((mx == r) & (d > 0), ((g - b) / safe) % 6, h)
    h = np.where((mx == g) & (d > 0), (b - r) / safe + 2, h)
    h = np.where((mx == b) & (d > 0), (r - g) / safe + 4, h)
    h /= 6.0
    return np.stack([h, s, v], axis=-1).astype(np.float32)


def luminance(rgb: np.ndarray) -> np.ndarray:
    """Rec.709 luminance."""
    return (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]).astype(np.float32)
