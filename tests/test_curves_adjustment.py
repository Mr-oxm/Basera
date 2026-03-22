"""Curves adjustment: legacy params, four-curve bundle, apply."""

import numpy as np

from photo_editor.adjustments.curves import (
    Curves,
    build_lut_y,
    coerce_curve_bundle,
    sanitize_curve_points,
)

_ID = [[0, 0], [255, 255]]


def test_sanitize_curve_points_pins_ends() -> None:
    pts = sanitize_curve_points([[10, 20], [200, 220]])
    assert pts[0][0] == 0
    assert pts[-1][0] == 255


def test_coerce_legacy_sliders() -> None:
    p = coerce_curve_bundle({"shadows": 10, "midtones": 0, "highlights": -5})
    assert p["channel"] == "RGB"
    assert len(p["points_rgb"]) == 5
    assert p["points_red"] == sanitize_curve_points(_ID)
    assert p["points_green"] == sanitize_curve_points(_ID)


def test_coerce_single_curve_red_migrates() -> None:
    p = coerce_curve_bundle(
        {"channel": "Red", "points": [[0, 10], [128, 128], [255, 250]], "shadows": 99},
    )
    assert p["channel"] == "Red"
    assert p["points_red"][1] == [128, 128]
    assert p["points_rgb"] == sanitize_curve_points(_ID)


def test_coerce_full_bundle_roundtrip() -> None:
    b = {
        "channel": "Green",
        "points_rgb": [[0, 20], [255, 240]],
        "points_red": _ID,
        "points_green": [[0, 0], [128, 100], [255, 255]],
        "points_blue": _ID,
    }
    p = coerce_curve_bundle(b)
    assert p["points_green"][1][1] == 100


def test_build_lut_y_identity() -> None:
    lut = build_lut_y([[0, 0], [255, 255]])
    assert lut.shape == (256,)
    assert np.allclose(lut[0], 0.0, atol=1e-5)
    assert np.allclose(lut[255], 1.0, atol=1e-5)


def test_curves_apply_rgb_composite_then_per_channel() -> None:
    adj = Curves()
    img = np.zeros((4, 4, 4), dtype=np.float32)
    img[..., 0] = 0.8
    img[..., 1] = 0.4
    img[..., 2] = 0.2
    img[..., 3] = 1.0

    base = {
        "channel": "RGB",
        "points_red": _ID,
        "points_green": _ID,
        "points_blue": _ID,
    }
    darkened = adj.apply(img, {**base, "points_rgb": [[0, 0], [255, 128]]})
    assert darkened[..., 3].mean() > 0.99
    assert darkened[..., :3].mean() < img[..., :3].mean()

    red_only = adj.apply(
        img,
        {
            "channel": "RGB",
            "points_rgb": _ID,
            "points_red": [[0, 0], [255, 0]],
            "points_green": _ID,
            "points_blue": _ID,
        },
    )
    assert red_only[..., 1].mean() > 0.35
    assert red_only[..., 0].mean() < 0.2
