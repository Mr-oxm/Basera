"""Unit tests for adjustment layers."""

import numpy as np
import pytest

from photo_editor.adjustments.brightness_contrast import BrightnessContrast
from photo_editor.adjustments.invert import Invert
from photo_editor.adjustments.posterize import Posterize
from photo_editor.adjustments.threshold import Threshold


@pytest.fixture
def sample_image():
    """RGBA float32 gradient image."""
    img = np.zeros((10, 10, 4), dtype=np.float32)
    grad = np.linspace(0, 1, 10, dtype=np.float32)
    img[..., 0] = grad[np.newaxis, :]
    img[..., 1] = grad[np.newaxis, :]
    img[..., 2] = grad[np.newaxis, :]
    img[..., 3] = 1.0
    return img


class TestBrightnessContrast:
    def test_no_change(self, sample_image):
        adj = BrightnessContrast()
        result = adj.apply(sample_image, {"brightness": 0, "contrast": 0})
        np.testing.assert_allclose(result, sample_image, atol=1e-5)

    def test_brightness_up(self, sample_image):
        adj = BrightnessContrast()
        result = adj.apply(sample_image, {"brightness": 50, "contrast": 0})
        assert result[0, 0, 0] > sample_image[0, 0, 0]

    def test_preserves_alpha(self, sample_image):
        adj = BrightnessContrast()
        result = adj.apply(sample_image, {"brightness": 50, "contrast": 50})
        np.testing.assert_allclose(result[..., 3], sample_image[..., 3], atol=1e-5)


class TestInvert:
    def test_double_invert(self, sample_image):
        adj = Invert()
        result = adj.apply(adj.apply(sample_image, {}), {})
        np.testing.assert_allclose(result, sample_image, atol=1e-5)


class TestPosterize:
    def test_two_levels(self, sample_image):
        adj = Posterize()
        result = adj.apply(sample_image, {"levels": 2})
        uniq = np.unique(result[..., 0])
        assert len(uniq) <= 3  # 0, 1, and possibly 0.5


class TestThreshold:
    def test_binary(self, sample_image):
        adj = Threshold()
        result = adj.apply(sample_image, {"threshold": 128})
        uniq = np.unique(result[..., 0])
        assert set(uniq).issubset({0.0, 1.0})
