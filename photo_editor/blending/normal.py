"""Normal and Dissolve blend modes."""

import numpy as np


def blend_normal(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return overlay


def blend_dissolve(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    noise = np.random.random(overlay.shape[:2]).astype(np.float32)
    avg = overlay.mean(axis=-1)
    mask = (noise < avg)[..., np.newaxis]
    return np.where(mask, overlay, base)
