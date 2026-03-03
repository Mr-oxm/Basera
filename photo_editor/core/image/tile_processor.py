"""Tile-based parallel processing for image operations.

Splits an image into 256×256 tiles and processes them in parallel.
Useful for filters and adjustments that can run per-tile.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

import numpy as np

DEFAULT_TILE_SIZE = 256


def process_tiled(
    image: np.ndarray,
    func: Callable[[np.ndarray], np.ndarray],
    tile_size: int = DEFAULT_TILE_SIZE,
    max_workers: int | None = None,
) -> np.ndarray:
    """Process image in tiles in parallel.

    Parameters
    ----------
    image : (H, W, C) array
        Input image (float32 or uint8).
    func : callable
        Takes a tile array, returns processed tile. Must not modify in place.
    tile_size : int
        Tile dimension (square).
    max_workers : int | None
        Thread pool size; None = default.

    Returns
    -------
    result : same shape as image
        Processed image.
    """
    h, w = image.shape[:2]
    result = np.empty_like(image)
    tiles: list[tuple[int, int, int, int]] = []
    for y in range(0, h, tile_size):
        for x in range(0, w, tile_size):
            tw = min(tile_size, w - x)
            th = min(tile_size, h - y)
            if tw > 0 and th > 0:
                tiles.append((x, y, tw, th))

    def process_one(txywh: tuple[int, int, int, int]) -> tuple[int, int, np.ndarray]:
        tx, ty, tw, th = txywh
        tile = image[ty : ty + th, tx : tx + tw].copy()
        out = func(tile)
        return (tx, ty, out)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(process_one, t): t for t in tiles}
        for fut in as_completed(futures):
            tx, ty, out = fut.result()
            th, tw = out.shape[:2]
            result[ty : ty + th, tx : tx + tw] = out

    return result
