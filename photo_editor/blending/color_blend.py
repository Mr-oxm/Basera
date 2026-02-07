"""Color group blend modes (Hue, Saturation, Color, Luminosity)."""

import numpy as np

from ..utils.color_utils import rgb_to_hsl, hsl_to_rgb


def blend_hue(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    b_hsl = rgb_to_hsl(base)
    o_hsl = rgb_to_hsl(overlay)
    out = np.stack([o_hsl[..., 0], b_hsl[..., 1], b_hsl[..., 2]], axis=-1)
    return hsl_to_rgb(out)


def blend_saturation(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    b_hsl = rgb_to_hsl(base)
    o_hsl = rgb_to_hsl(overlay)
    out = np.stack([b_hsl[..., 0], o_hsl[..., 1], b_hsl[..., 2]], axis=-1)
    return hsl_to_rgb(out)


def blend_color(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    b_hsl = rgb_to_hsl(base)
    o_hsl = rgb_to_hsl(overlay)
    out = np.stack([o_hsl[..., 0], o_hsl[..., 1], b_hsl[..., 2]], axis=-1)
    return hsl_to_rgb(out)


def blend_luminosity(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    b_hsl = rgb_to_hsl(base)
    o_hsl = rgb_to_hsl(overlay)
    out = np.stack([b_hsl[..., 0], b_hsl[..., 1], o_hsl[..., 2]], axis=-1)
    return hsl_to_rgb(out)
