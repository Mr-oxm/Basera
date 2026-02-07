"""Comparative group blend modes."""

import numpy as np


def blend_difference(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return np.abs(base - overlay)


def blend_exclusion(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return base + overlay - 2 * base * overlay


def blend_subtract(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return np.clip(base - overlay, 0, 1)


def blend_divide(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    safe = np.where(overlay > 0, overlay, 1e-6)
    return np.clip(base / safe, 0, 1)
