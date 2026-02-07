"""Contrast group blend modes."""

import numpy as np


def blend_overlay(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    lo = 2 * base * overlay
    hi = 1 - 2 * (1 - base) * (1 - overlay)
    return np.where(base <= 0.5, lo, hi)


def blend_soft_light(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    lo = base - (1 - 2 * overlay) * base * (1 - base)
    hi = base + (2 * overlay - 1) * (np.sqrt(np.clip(base, 0, None)) - base)
    return np.where(overlay <= 0.5, lo, hi)


def blend_hard_light(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    lo = 2 * base * overlay
    hi = 1 - 2 * (1 - base) * (1 - overlay)
    return np.where(overlay <= 0.5, lo, hi)


def blend_vivid_light(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    burn_d = np.where(overlay > 0, 2 * overlay, 1e-6)
    dodge_d = np.where(overlay < 1, 2 * (1 - overlay), 1e-6)
    burn = 1.0 - (1.0 - base) / burn_d
    dodge = base / dodge_d
    return np.clip(np.where(overlay <= 0.5, burn, dodge), 0, 1)


def blend_linear_light(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return np.clip(base + 2 * overlay - 1.0, 0, 1)


def blend_pin_light(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    lo = np.minimum(base, 2 * overlay)
    hi = np.maximum(base, 2 * overlay - 1)
    return np.where(overlay < 0.5, lo, hi)


def blend_hard_mix(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return np.where(base + overlay >= 1.0, 1.0, 0.0)
