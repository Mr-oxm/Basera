"""Mip-level cache — pre-downsampled layer pyramids for zoom-out rendering.

At zoom <= 50% the compositor can use a 1:2 mip instead of the full-res
pixels, reducing float32 work by 4x.  At 25% the 1:4 mip gives 16x.

Mips are computed lazily on first access and invalidated when the layer's
pixels change.  The cache is keyed by ``id(pixel_array)`` so a new pixel
buffer (from a brush stroke, transform, etc.) automatically triggers
recomputation.

Mip levels:
  0  =  1:1  (original, never stored — use ``layer.pixels`` directly)
  1  =  1:2
  2  =  1:4
  3  =  1:8
"""

from __future__ import annotations

import numpy as np

try:
    import cv2 as _cv2
except ImportError:  # pragma: no cover
    _cv2 = None

MAX_MIP_LEVEL = 3


def mip_level_for_scale(scale: float) -> int:
    """Return the mip level appropriate for the given viewport scale.

    scale >= 1.0 → 0  (full res)
    scale >= 0.5 → 1  (half res)
    scale >= 0.25 → 2 (quarter res)
    else          → 3 (eighth res)
    """
    if scale >= 1.0:
        return 0
    if scale >= 0.5:
        return 1
    if scale >= 0.25:
        return 2
    return min(3, MAX_MIP_LEVEL)


class MipCache:
    """Per-layer mip pyramid cache.

    Usage::

        cache = MipCache()
        mip_pixels, mip_pos = cache.get(layer_id, pixels, position, level)
    """

    def __init__(self) -> None:
        # layer_id -> (source_id, {level: (pixels, position)})
        self._store: dict[str, tuple[int, dict[int, tuple[np.ndarray, tuple[int, int]]]]] = {}

    def clear(self) -> None:
        self._store.clear()

    def invalidate(self, layer_id: str) -> None:
        self._store.pop(layer_id, None)

    def get(
        self,
        layer_id: str,
        pixels: np.ndarray,
        position: tuple[int, int],
        level: int,
    ) -> tuple[np.ndarray, tuple[int, int]]:
        """Return downsampled pixels and adjusted position for *level*.

        Level 0 returns the original pixels and position unchanged.
        """
        if level <= 0 or _cv2 is None:
            return pixels, position

        level = min(level, MAX_MIP_LEVEL)
        pix_id = id(pixels)
        entry = self._store.get(layer_id)

        if entry is not None and entry[0] == pix_id:
            cached = entry[1].get(level)
            if cached is not None:
                return cached

        if entry is None or entry[0] != pix_id:
            entry = (pix_id, {})
            self._store[layer_id] = entry

        divisor = 1 << level  # 2, 4, or 8
        h, w = pixels.shape[:2]
        new_w = max(1, w // divisor)
        new_h = max(1, h // divisor)

        mip_pixels = _cv2.resize(
            pixels, (new_w, new_h), interpolation=_cv2.INTER_AREA,
        )
        mip_position = (position[0] // divisor, position[1] // divisor)
        entry[1][level] = (mip_pixels, mip_position)
        return mip_pixels, mip_position

    def get_mask(
        self,
        layer_id: str,
        mask: np.ndarray,
        level: int,
    ) -> np.ndarray:
        """Downsample a mask to the given mip level."""
        if level <= 0 or _cv2 is None:
            return mask
        level = min(level, MAX_MIP_LEVEL)
        divisor = 1 << level
        h, w = mask.shape[:2]
        new_w = max(1, w // divisor)
        new_h = max(1, h // divisor)
        return _cv2.resize(mask, (new_w, new_h), interpolation=_cv2.INTER_AREA)
