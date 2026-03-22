"""Normals — encode luminance derivatives as an RGB normal map (preview / texture workflow)."""

from __future__ import annotations

import numpy as np

from ..utils.color_utils import luminance
from .adjustment_base import Adjustment


def _sobel_grad(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Central differences with edge replication; returns gx, gy same shape as *gray*."""
    g = np.pad(gray.astype(np.float32), 1, mode="edge")
    gx = (g[1:-1, 2:] - g[1:-1, :-2]) * 0.5
    gy = (g[2:, 1:-1] - g[:-2, 1:-1]) * 0.5
    return gx.astype(np.float32), gy.astype(np.float32)


class Normals(Adjustment):
    def __init__(self) -> None:
        super().__init__(
            "Normals",
            {"strength": 80.0, "rotation": 0.0, "invert_z": False},
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        alpha = self._alpha(image)
        rgb = self._rgb(image)
        strength = float(np.clip(params.get("strength", 80), 0, 200)) / 100.0
        rotation_deg = float(np.clip(params.get("rotation", 0), -180, 180))
        invert_z = bool(params.get("invert_z", False))

        if strength < 1e-6:
            return image.copy()

        L = luminance(rgb)
        gx, gy = _sobel_grad(L)
        sx = -gx * strength
        sy = -gy * strength
        sz = np.ones_like(L, dtype=np.float32)

        n = np.stack([sx, sy, sz], axis=-1)
        mag = np.linalg.norm(n, axis=-1, keepdims=True) + 1e-8
        n = n / mag

        if abs(rotation_deg) > 1e-6:
            rad = np.float32(rotation_deg * (np.pi / 180.0))
            c = float(np.cos(rad))
            s = float(np.sin(rad))
            nx = n[..., 0]
            ny = n[..., 1]
            n[..., 0] = nx * c - ny * s
            n[..., 1] = nx * s + ny * c
            mag = np.linalg.norm(n, axis=-1, keepdims=True) + 1e-8
            n = n / mag

        if invert_z:
            n[..., 2] *= -1.0
            n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-8

        out_rgb = n * 0.5 + 0.5
        return self._merge(out_rgb.astype(np.float32), alpha)
