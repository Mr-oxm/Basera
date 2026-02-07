"""Unit tests for the blending engine and all blend modes."""

import numpy as np
import pytest

from photo_editor.blending.blending_engine import BlendingEngine
from photo_editor.core.enums import BlendMode


@pytest.fixture
def engine():
    return BlendingEngine()


@pytest.fixture
def white():
    return np.ones((4, 4, 4), dtype=np.float32)


@pytest.fixture
def black():
    img = np.zeros((4, 4, 4), dtype=np.float32)
    img[..., 3] = 1.0
    return img


@pytest.fixture
def mid_gray():
    img = np.full((4, 4, 4), 0.5, dtype=np.float32)
    img[..., 3] = 1.0
    return img


class TestNormalBlend:
    def test_identity(self, engine, white):
        result = engine.blend(white, white, BlendMode.NORMAL)
        np.testing.assert_allclose(result, white, atol=1e-5)

    def test_opacity_zero(self, engine, white, black):
        result = engine.blend(white, black, BlendMode.NORMAL, opacity=0.0)
        np.testing.assert_allclose(result, white, atol=1e-5)

    def test_opacity_half(self, engine, white, black):
        result = engine.blend(white, black, BlendMode.NORMAL, opacity=0.5)
        assert 0.4 < result[0, 0, 0] < 0.6


class TestMultiplyBlend:
    def test_white_identity(self, engine, white):
        result = engine.blend(white, white, BlendMode.MULTIPLY)
        np.testing.assert_allclose(result[..., :3], 1.0, atol=1e-5)

    def test_black_absorbs(self, engine, white, black):
        result = engine.blend(white, black, BlendMode.MULTIPLY)
        np.testing.assert_allclose(result[..., :3], 0.0, atol=1e-5)


class TestScreenBlend:
    def test_black_identity(self, engine, black):
        overlay = black.copy()
        result = engine.blend(black, overlay, BlendMode.SCREEN)
        np.testing.assert_allclose(result[..., :3], 0.0, atol=1e-5)

    def test_white_saturates(self, engine, black, white):
        result = engine.blend(black, white, BlendMode.SCREEN)
        np.testing.assert_allclose(result[..., :3], 1.0, atol=1e-5)


class TestOverlayBlend:
    def test_mid_gray(self, engine, mid_gray):
        result = engine.blend(mid_gray, mid_gray, BlendMode.OVERLAY)
        assert result.shape == mid_gray.shape


class TestAllModes:
    @pytest.mark.parametrize("mode", list(BlendMode))
    def test_no_crash(self, engine, white, mid_gray, mode):
        result = engine.blend(white, mid_gray, mode, opacity=0.75)
        assert result.shape == white.shape
        assert result.dtype == np.float32
        assert np.all(result >= 0) and np.all(result <= 1)


class TestMaskBlend:
    def test_mask_blocks_overlay(self, engine, white, black):
        mask = np.zeros((4, 4), dtype=np.float32)
        result = engine.blend_with_mask(white, black, mask, BlendMode.NORMAL)
        np.testing.assert_allclose(result, white, atol=1e-5)

    def test_full_mask_passes(self, engine, white, black):
        mask = np.ones((4, 4), dtype=np.float32)
        result = engine.blend_with_mask(white, black, mask, BlendMode.NORMAL)
        np.testing.assert_allclose(result[..., :3], 0.0, atol=1e-5)
