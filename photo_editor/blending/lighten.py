"""Lighten group blend modes."""

import numpy as np


def blend_lighten(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return np.maximum(base, overlay)


def blend_screen(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return 1.0 - (1.0 - base) * (1.0 - overlay)


def blend_color_dodge(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    safe = np.where(overlay < 1.0, 1.0 - overlay, 1e-6)
    return np.clip(base / safe, 0, 1)


def blend_linear_dodge(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return np.clip(base + overlay, 0, 1)


def blend_lighter_color(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    base_l = 0.299 * base[..., 0] + 0.587 * base[..., 1] + 0.114 * base[..., 2]
    over_l = 0.299 * overlay[..., 0] + 0.587 * overlay[..., 1] + 0.114 * overlay[..., 2]
    return np.where((over_l > base_l)[..., np.newaxis], overlay, base)
