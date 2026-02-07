"""Darken group blend modes."""

import numpy as np


def blend_darken(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return np.minimum(base, overlay)


def blend_multiply(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return base * overlay


def blend_color_burn(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    safe = np.where(overlay > 0, overlay, 1e-6)
    return np.clip(1.0 - (1.0 - base) / safe, 0, 1)


def blend_linear_burn(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return np.clip(base + overlay - 1.0, 0, 1)


def blend_darker_color(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    base_l = 0.299 * base[..., 0] + 0.587 * base[..., 1] + 0.114 * base[..., 2]
    over_l = 0.299 * overlay[..., 0] + 0.587 * overlay[..., 1] + 0.114 * overlay[..., 2]
    return np.where((over_l < base_l)[..., np.newaxis], overlay, base)
