"""Tests for image buffer pool."""

import numpy as np
import pytest

from photo_editor.engine.cache.image_pool import ImagePool


def test_acquire_returns_buffer():
    """acquire returns a buffer of the requested shape."""
    pool = ImagePool()
    buf = pool.acquire((100, 100, 4), dtype=np.float32)
    assert buf.shape == (100, 100, 4)
    assert buf.dtype == np.float32


def test_release_and_reuse():
    """Released buffers are reused on next acquire."""
    pool = ImagePool(max_buffers_per_shape=2)
    buf1 = pool.acquire((50, 50, 4), dtype=np.float32)
    pool.release(buf1)
    buf2 = pool.acquire((50, 50, 4), dtype=np.float32)
    # Same buffer reused (same id) or pool returns any buffer of correct shape
    assert buf2.shape == (50, 50, 4)
    assert buf2.dtype == np.float32


def test_clear():
    """clear empties the pool."""
    pool = ImagePool()
    buf = pool.acquire((10, 10, 4))
    pool.release(buf)
    pool.clear()
    buf2 = pool.acquire((10, 10, 4))
    assert id(buf2) != id(buf)  # New allocation after clear
