"""Levels bundle coercion and Hue/Saturation multi-target apply."""

import numpy as np

from photo_editor.adjustments.hue_saturation import HueSaturation, coerce_hue_saturation_params
from photo_editor.adjustments.levels import Levels, coerce_levels_bundle
from photo_editor.utils.color_utils import hsv_to_rgb, rgb_to_hsv


def test_coerce_levels_flat_legacy() -> None:
    b = coerce_levels_bundle({"input_black": 5, "input_white": 240, "gamma": 1.2})
    assert b["levels_rgb"]["input_black"] == 5
    assert b["levels_red"]["gamma"] == 1.2


def test_levels_apply_stacks_rgb_then_red() -> None:
    adj = Levels()
    img = np.zeros((2, 2, 4), dtype=np.float32)
    img[..., 0] = 0.5
    img[..., 1] = 0.5
    img[..., 2] = 0.5
    img[..., 3] = 1.0
    p = {
        "channel": "RGB",
        "preset": "Master",
        "levels_rgb": {"input_black": 0, "input_white": 255, "gamma": 1.0, "output_black": 0, "output_white": 255},
        "levels_red": {"input_black": 0, "input_white": 128, "gamma": 1.0, "output_black": 0, "output_white": 255},
        "levels_green": {"input_black": 0, "input_white": 255, "gamma": 1.0, "output_black": 0, "output_white": 255},
        "levels_blue": {"input_black": 0, "input_white": 255, "gamma": 1.0, "output_black": 0, "output_white": 255},
    }
    out = adj.apply(img, p)
    assert out[..., 0].mean() > out[..., 1].mean()


def test_coerce_hue_legacy() -> None:
    p = coerce_hue_saturation_params({"hue": 15, "saturation": 10, "lightness": -5})
    assert p["targets"]["master"]["hue"] == 15
    assert p["targets"]["reds"]["hue"] == 0


def test_hue_saturation_master_shift() -> None:
    adj = HueSaturation()
    img = np.zeros((4, 4, 4), dtype=np.float32)
    img[..., 0] = 1.0
    img[..., 1] = 0.0
    img[..., 2] = 0.0
    img[..., 3] = 1.0
    p = coerce_hue_saturation_params({})
    p["targets"]["master"]["hue"] = 120.0
    out = adj.apply(img, p)
    assert out[..., 1].mean() > 0.4


def test_hsv_roundtrip_vector() -> None:
    rgb = np.random.RandomState(0).rand(2, 3, 3).astype(np.float32)
    hsv = rgb_to_hsv(rgb)
    back = hsv_to_rgb(hsv)
    assert np.allclose(rgb, back, atol=1e-5)
