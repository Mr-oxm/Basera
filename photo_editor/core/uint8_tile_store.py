from __future__ import annotations

import numpy as np


class Uint8TileStore:
    """Compact uint8 RGBA storage backed by fixed-size tiles."""

    def __init__(self, width: int, height: int, tile_size: int = 256) -> None:
        self.width = int(width)
        self.height = int(height)
        self.tile_size = max(1, int(tile_size))
        self._tiles: dict[tuple[int, int], np.ndarray] = {}

    @classmethod
    def from_array(cls, rgba_u8: np.ndarray, tile_size: int = 256) -> "Uint8TileStore":
        height, width = rgba_u8.shape[:2]
        store = cls(width, height, tile_size=tile_size)
        tile = store.tile_size
        for top in range(0, height, tile):
            for left in range(0, width, tile):
                chunk = rgba_u8[top:top + tile, left:left + tile]
                store._tiles[(left // tile, top // tile)] = chunk.copy()
        return store

    def copy(self) -> "Uint8TileStore":
        new = Uint8TileStore(self.width, self.height, tile_size=self.tile_size)
        new._tiles = {key: tile.copy() for key, tile in self._tiles.items()}
        return new

    def to_array(self) -> np.ndarray:
        rgba = np.zeros((self.height, self.width, 4), dtype=np.uint8)
        tile = self.tile_size
        for (tile_x, tile_y), value in self._tiles.items():
            left = tile_x * tile
            top = tile_y * tile
            rgba[top:top + value.shape[0], left:left + value.shape[1]] = value
        return rgba

    def decode_roi(self, x: int, y: int, width: int, height: int) -> np.ndarray | None:
        if width <= 0 or height <= 0:
            return None
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(self.width, x0 + int(width))
        y1 = min(self.height, y0 + int(height))
        if x1 <= x0 or y1 <= y0:
            return None

        roi = np.zeros((y1 - y0, x1 - x0, 4), dtype=np.uint8)
        tile = self.tile_size
        start_tile_x = x0 // tile
        end_tile_x = (x1 - 1) // tile
        start_tile_y = y0 // tile
        end_tile_y = (y1 - 1) // tile

        for tile_y in range(start_tile_y, end_tile_y + 1):
            for tile_x in range(start_tile_x, end_tile_x + 1):
                chunk = self._tiles.get((tile_x, tile_y))
                if chunk is None:
                    continue
                tile_left = tile_x * tile
                tile_top = tile_y * tile
                src_x0 = max(x0, tile_left)
                src_y0 = max(y0, tile_top)
                src_x1 = min(x1, tile_left + chunk.shape[1])
                src_y1 = min(y1, tile_top + chunk.shape[0])
                if src_x1 <= src_x0 or src_y1 <= src_y0:
                    continue
                roi_y0 = src_y0 - y0
                roi_x0 = src_x0 - x0
                tile_y0 = src_y0 - tile_top
                tile_x0 = src_x0 - tile_left
                roi[roi_y0:roi_y0 + (src_y1 - src_y0), roi_x0:roi_x0 + (src_x1 - src_x0)] = (
                    chunk[tile_y0:tile_y0 + (src_y1 - src_y0), tile_x0:tile_x0 + (src_x1 - src_x0)]
                )
        return roi

    def write_roi(self, x: int, y: int, rgba_u8: np.ndarray) -> None:
        height, width = rgba_u8.shape[:2]
        if width <= 0 or height <= 0:
            return
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(self.width, x0 + int(width))
        y1 = min(self.height, y0 + int(height))
        if x1 <= x0 or y1 <= y0:
            return

        tile = self.tile_size
        start_tile_x = x0 // tile
        end_tile_x = (x1 - 1) // tile
        start_tile_y = y0 // tile
        end_tile_y = (y1 - 1) // tile

        for tile_y in range(start_tile_y, end_tile_y + 1):
            for tile_x in range(start_tile_x, end_tile_x + 1):
                tile_left = tile_x * tile
                tile_top = tile_y * tile
                tile_w = min(tile, self.width - tile_left)
                tile_h = min(tile, self.height - tile_top)
                chunk = self._tiles.get((tile_x, tile_y))
                if chunk is None or chunk.shape[:2] != (tile_h, tile_w):
                    chunk = np.zeros((tile_h, tile_w, 4), dtype=np.uint8)
                    self._tiles[(tile_x, tile_y)] = chunk

                src_x0 = max(x0, tile_left)
                src_y0 = max(y0, tile_top)
                src_x1 = min(x1, tile_left + tile_w)
                src_y1 = min(y1, tile_top + tile_h)
                if src_x1 <= src_x0 or src_y1 <= src_y0:
                    continue

                roi_x0 = src_x0 - x0
                roi_y0 = src_y0 - y0
                tile_x0 = src_x0 - tile_left
                tile_y0 = src_y0 - tile_top
                chunk[tile_y0:tile_y0 + (src_y1 - src_y0), tile_x0:tile_x0 + (src_x1 - src_x0)] = (
                    rgba_u8[roi_y0:roi_y0 + (src_y1 - src_y0), roi_x0:roi_x0 + (src_x1 - src_x0)]
                )