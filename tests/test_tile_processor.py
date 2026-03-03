"""Tests for tile-based image processing."""

import numpy as np
import pytest

from photo_editor.core.image import process_tiled


def test_process_tiled_identity():
    """process_tiled with identity returns same image."""
    img = np.random.rand(128, 128, 4).astype(np.float32)
    result = process_tiled(img, lambda t: t, tile_size=64)
    np.testing.assert_array_almost_equal(result, img)


def test_process_tiled_brightness():
    """process_tiled applies per-tile transform."""
    img = np.ones((64, 64, 4), dtype=np.float32) * 0.5
    result = process_tiled(img, lambda t: np.clip(t + 0.2, 0, 1))
    np.testing.assert_array_almost_equal(result, 0.7)

