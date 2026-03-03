"""Image buffer pool — reuse allocations instead of per-frame allocation.

Reduces GC pressure and allocation churn during interactive rendering.
"""

from __future__ import annotations

from collections import deque
from threading import Lock

import numpy as np


class ImagePool:
    """Pool of pre-allocated RGBA float32 or uint8 buffers.

    acquire(shape, dtype) returns a buffer; release(buf) returns it to the pool.
    Buffers are reused by shape, so common sizes (e.g. 1920x1080) stay warm.
    """

    def __init__(self, max_buffers_per_shape: int = 4) -> None:
        self._max_per_shape = max_buffers_per_shape
        self._pools: dict[tuple[int, ...], deque[np.ndarray]] = {}
        self._lock = Lock()

    def acquire(self, shape: tuple[int, ...], dtype: np.dtype | type = np.float32) -> np.ndarray:
        """Get a buffer of the given shape. Creates new if pool is empty."""
        dt = np.dtype(dtype) if not isinstance(dtype, np.dtype) else dtype
        key = (shape, dt)
        with self._lock:
            pool = self._pools.get(key)
            if pool and pool:
                return pool.popleft()
        return np.empty(shape, dtype=dt)

    def release(self, buf: np.ndarray) -> None:
        """Return a buffer to the pool for reuse."""
        if buf is None:
            return
        key = (buf.shape, buf.dtype)
        with self._lock:
            pool = self._pools.setdefault(key, deque())
            if len(pool) < self._max_per_shape:
                pool.append(buf)

    def clear(self) -> None:
        """Release all pooled buffers."""
        with self._lock:
            self._pools.clear()
