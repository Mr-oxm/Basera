"""Render pipeline — orchestrates compositor (with adjustment/filter layers).

Caches the uint8 output so repeated calls without invalidation
(e.g. panel refreshes, selection overlay updates) are essentially free.
Pre-allocates the uint8 buffer to avoid repeated allocation + conversion.

TileCache is wired for incremental re-render: tools can call invalidate_region()
on brush strokes; when tile-based execute is fully implemented, only dirty
tiles will be re-composited.
"""

import numpy as np

from ..core.document import Document
from .cache.image_pool import ImagePool
from .compositor import Compositor
from .tile_cache import TileCache


class RenderPipeline:
    """Full pipeline: layer compositing -> adjustment layers -> output."""

    def __init__(self, quality_mode: str = "final") -> None:
        self._pool = ImagePool(max_buffers_per_shape=4)
        self._quality_mode = quality_mode
        self._compositor = Compositor(image_pool=self._pool, quality_mode=quality_mode)
        self._tile_cache = TileCache(tile_size=256)
        self._last_width = 0
        self._last_height = 0
        self._result_float: np.ndarray | None = None
        self._full_invalidated: bool = True
        self._dirty_layer_ids: set[str] = set()
        self._last_layer_bounds: dict[str, tuple[int, int, int, int]] = {}
        # Cached final uint8 result
        self._result_uint8: np.ndarray | None = None
        self._uint8_valid: bool = False
        # Pre-allocated uint8 conversion buffer
        self._uint8_buf: np.ndarray | None = None

    @staticmethod
    def _merge_rects(
        first: tuple[int, int, int, int] | None,
        second: tuple[int, int, int, int] | None,
    ) -> tuple[int, int, int, int] | None:
        if first is None:
            return second
        if second is None:
            return first
        x0 = min(first[0], second[0])
        y0 = min(first[1], second[1])
        x1 = max(first[0] + first[2], second[0] + second[2])
        y1 = max(first[1] + first[3], second[1] + second[3])
        return (x0, y0, x1 - x0, y1 - y0)

    def _current_layer_bounds(self, document: Document) -> dict[str, tuple[int, int, int, int]]:
        bounds: dict[str, tuple[int, int, int, int]] = {}
        for layer in document.layers:
            try:
                lx, ly = layer.position
                lw = int(layer.width)
                lh = int(layer.height)
            except (AttributeError, IndexError, TypeError, ValueError):
                continue
            bounds[layer.id] = (lx, ly, lw, lh)
        return bounds

    def execute(self, document: Document) -> np.ndarray:
        w, h = document.width, document.height
        if w != self._last_width or h != self._last_height:
            self._tile_cache.initialize(w, h)
            self._last_width, self._last_height = w, h
            self._full_invalidated = True

        can_incremental = self._compositor.can_render_region_incrementally(document.layers)
        dirty_tiles = self._tile_cache.dirty_tiles()

        if self._result_float is None or self._full_invalidated or not can_incremental:
            self._result_float = self._compositor.composite(document.layers, w, h)
            for tile in dirty_tiles:
                tile.data = self._result_float[
                    tile.y:tile.y + tile.height,
                    tile.x:tile.x + tile.width,
                ].copy()
                tile.dirty = False
            self._last_layer_bounds = self._current_layer_bounds(document)
            self._dirty_layer_ids.clear()
            self._full_invalidated = False
            return self._result_float

        if not dirty_tiles:
            return self._result_float

        for tile in dirty_tiles:
            region = self._compositor.composite_region(
                document.layers,
                w,
                h,
                tile.x,
                tile.y,
                tile.width,
                tile.height,
            )
            self._result_float[
                tile.y:tile.y + tile.height,
                tile.x:tile.x + tile.width,
            ] = region
            tile.data = region.copy()
            tile.dirty = False

        self._last_layer_bounds = self._current_layer_bounds(document)
        self._dirty_layer_ids.clear()
        return self._result_float

    def invalidate_region(self, x: int, y: int, width: int, height: int) -> None:
        """Mark tiles overlapping (x, y, width, height) as dirty."""
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self._last_width, x + width)
        y1 = min(self._last_height, y + height)
        if x1 <= x0 or y1 <= y0:
            return
        self._tile_cache.invalidate_region(x0, y0, x1 - x0, y1 - y0)
        self._uint8_valid = False

    def sync_cached_output_from_uint8(self, rgba: np.ndarray) -> None:
        """Rebase cached output to an already displayed uint8 frame.

        This keeps future incremental tile recomposition aligned with the
        displayed image after layer storage compaction quantizes inactive
        display rasters to uint8-at-rest.
        """
        if rgba.dtype != np.uint8:
            raise ValueError("Expected uint8 RGBA frame")

        self._result_uint8 = rgba.copy()
        self._uint8_valid = True

        if self._result_float is None or self._result_float.shape != rgba.shape:
            self._result_float = np.empty(rgba.shape, dtype=np.float32)
        np.multiply(rgba, 1.0 / 255.0, out=self._result_float, casting="unsafe")

    def rebase_cached_output_to_uint8(self) -> None:
        if self._result_uint8 is None:
            return
        self.sync_cached_output_from_uint8(self._result_uint8)

    def execute_to_uint8(self, document: Document) -> np.ndarray:
        """Return the composited image as uint8 RGBA.

        Returns a cached copy when nothing has been invalidated since
        the last call, avoiding both the composite and the float->uint8
        conversion.
        """
        if self._uint8_valid and self._result_uint8 is not None:
            return self._result_uint8
        result = self.execute(document)
        # Fast float32→uint8 using pre-allocated buffer
        shape = result.shape
        if self._uint8_buf is None or self._uint8_buf.shape != shape:
            self._uint8_buf = np.empty(shape, dtype=np.uint8)
        # render() already clips to [0,1], so this is safe
        np.multiply(result, 255, out=self._uint8_buf, casting="unsafe")
        self._result_uint8 = self._uint8_buf
        self._uint8_valid = True
        return self._result_uint8

    def invalidate(self, layer_id: str | None = None) -> None:
        self._uint8_valid = False
        if layer_id is None:
            self._full_invalidated = True
            self._dirty_layer_ids.clear()
            self._tile_cache.invalidate_all()
            return

        self._dirty_layer_ids.add(layer_id)
        self._full_invalidated = True
        self._tile_cache.invalidate_all()
