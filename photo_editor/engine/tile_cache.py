"""Tile-based caching for large image rendering (architecture-ready)."""

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Tile:
    x: int
    y: int
    width: int
    height: int
    data: np.ndarray | None = None
    dirty: bool = True


class TileCache:
    """Partitions the canvas into fixed-size tiles for incremental re-render."""

    def __init__(self, tile_size: int = 256) -> None:
        self.tile_size = tile_size
        self._tiles: dict[tuple[int, int], Tile] = {}

    def initialize(self, width: int, height: int) -> None:
        self._tiles.clear()
        for y in range(0, height, self.tile_size):
            for x in range(0, width, self.tile_size):
                tw = min(self.tile_size, width - x)
                th = min(self.tile_size, height - y)
                self._tiles[(x, y)] = Tile(x=x, y=y, width=tw, height=th)

    def get_tile(self, x: int, y: int) -> Tile | None:
        key = (x - x % self.tile_size, y - y % self.tile_size)
        return self._tiles.get(key)

    def invalidate_region(self, x: int, y: int, w: int, h: int) -> None:
        if w <= 0 or h <= 0:
            return
        start_tx = x - x % self.tile_size
        start_ty = y - y % self.tile_size
        end_x = x + w - 1
        end_y = y + h - 1
        end_tx = end_x - end_x % self.tile_size
        end_ty = end_y - end_y % self.tile_size
        for ty in range(start_ty, end_ty + 1, self.tile_size):
            for tx in range(start_tx, end_tx + 1, self.tile_size):
                key = (tx, ty)
                if key in self._tiles:
                    self._tiles[key].dirty = True

    def invalidate_all(self) -> None:
        for tile in self._tiles.values():
            tile.dirty = True

    def dirty_tiles(self) -> list[Tile]:
        return [t for t in self._tiles.values() if t.dirty]

    def update_tile(self, tile: Tile, data: np.ndarray) -> None:
        tile.data = data
        tile.dirty = False
