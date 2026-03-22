"""Unit tests for adjustment layers."""

import numpy as np
import pytest

from photo_editor.adjustments.brightness_contrast import BrightnessContrast
from photo_editor.adjustments.invert import Invert
from photo_editor.adjustments.normals import Normals
from photo_editor.adjustments.posterize import Posterize
from photo_editor.adjustments.recolor import Recolor
from photo_editor.adjustments.split_toning import SplitToning
from photo_editor.adjustments.threshold import Threshold
from photo_editor.adjustments.white_balance import WhiteBalance, estimate_wb_from_sample


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


class TestWhiteBalance:
    def test_identity(self, sample_image):
        adj = WhiteBalance()
        result = adj.apply(sample_image, {"temperature": 0, "tint": 0})
        np.testing.assert_allclose(result, sample_image, atol=1e-5)

    def test_estimate_wb_gray(self):
        t, i = estimate_wb_from_sample(0.5, 0.5, 0.5)
        assert t == 0 and i == 0


class TestRecolor:
    def test_apply_runs(self, sample_image):
        adj = Recolor()
        out = adj.apply(
            sample_image,
            {"from_hue": 0.0, "to_hue": 120.0, "width": 60.0, "amount": 50.0},
        )
        assert out.shape == sample_image.shape


class TestSplitToning:
    def test_apply_runs(self, sample_image):
        adj = SplitToning()
        out = adj.apply(
            sample_image,
            {
                "highlights_hue": 40.0,
                "highlights_saturation": 20.0,
                "shadows_hue": 240.0,
                "shadows_saturation": 15.0,
                "balance": 50.0,
            },
        )
        assert out.shape == sample_image.shape


class TestNormals:
    def test_apply_shape(self, sample_image):
        adj = Normals()
        out = adj.apply(sample_image, {"strength": 40.0, "rotation": 0.0, "invert_z": False})
        assert out.shape == sample_image.shape
        np.testing.assert_allclose(out[..., 3], sample_image[..., 3], atol=1e-5)

    def test_rotation_changes_output(self, sample_image):
        adj = Normals()
        a = adj.apply(sample_image, {"strength": 60.0, "rotation": 0.0, "invert_z": False})
        b = adj.apply(sample_image, {"strength": 60.0, "rotation": 90.0, "invert_z": False})
        assert not np.allclose(a[..., :3], b[..., :3], atol=1e-3)
