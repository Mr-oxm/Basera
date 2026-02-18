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
from .compositor import Compositor
from .tile_cache import TileCache


class RenderPipeline:
    """Full pipeline: layer compositing -> adjustment layers -> output."""

    def __init__(self) -> None:
        self._compositor = Compositor()
        self._tile_cache = TileCache(tile_size=256)
        self._last_width = 0
        self._last_height = 0
        # Cached final uint8 result
        self._result_uint8: np.ndarray | None = None
        self._uint8_valid: bool = False
        # Pre-allocated uint8 conversion buffer
        self._uint8_buf: np.ndarray | None = None

    def execute(self, document: Document) -> np.ndarray:
        w, h = document.width, document.height
        if w != self._last_width or h != self._last_height:
            self._tile_cache.initialize(w, h)
            self._last_width, self._last_height = w, h
        return self._compositor.composite(
            document.layers, w, h
        )

    def invalidate_region(self, x: int, y: int, width: int, height: int) -> None:
        """Mark tiles overlapping (x, y, width, height) as dirty for future tile-based render."""
        self._tile_cache.invalidate_region(x, y, width, height)
        self._uint8_valid = False

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
        self._tile_cache.invalidate_all()
