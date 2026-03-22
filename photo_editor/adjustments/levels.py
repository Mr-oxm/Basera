"""Levels non-destructive adjustment — per-channel blocks + RGB composite."""

from __future__ import annotations

import numpy as np

from .adjustment_base import Adjustment

_LEVEL_KEYS = ("levels_rgb", "levels_red", "levels_green", "levels_blue")


def _default_block() -> dict:
    return {
        "input_black": 0,
        "input_white": 255,
        "gamma": 1.0,
        "output_black": 0,
        "output_white": 255,
    }


def coerce_levels_bundle(params: dict | None) -> dict:
    """Normalize params to levels_rgb/red/green/blue blocks + UI fields."""
    if params is None:
        params = {}
    d = _default_block()
    if all(isinstance(params.get(k), dict) for k in _LEVEL_KEYS):
        out: dict = {"channel": params.get("channel", "RGB"), "preset": params.get("preset", "Master")}
        for k in _LEVEL_KEYS:
            merged = {**d, **params[k]}
            merged["input_black"] = int(np.clip(float(merged["input_black"]), 0, 254))
            merged["input_white"] = int(np.clip(float(merged["input_white"]), 1, 255))
            merged["gamma"] = float(np.clip(float(merged["gamma"]), 0.1, 10.0))
            merged["output_black"] = int(np.clip(float(merged["output_black"]), 0, 255))
            merged["output_white"] = int(np.clip(float(merged["output_white"]), 0, 255))
            if merged["input_white"] <= merged["input_black"]:
                merged["input_white"] = merged["input_black"] + 1
            out[k] = merged
        return out

    block = {
        "input_black": int(np.clip(float(params.get("input_black", 0)), 0, 254)),
        "input_white": int(np.clip(float(params.get("input_white", 255)), 1, 255)),
        "gamma": float(np.clip(float(params.get("gamma", 1.0)), 0.1, 10.0)),
        "output_black": int(np.clip(float(params.get("output_black", 0)), 0, 255)),
        "output_white": int(np.clip(float(params.get("output_white", 255)), 0, 255)),
    }
    if block["input_white"] <= block["input_black"]:
        block["input_white"] = block["input_black"] + 1
    out = {"channel": params.get("channel", "RGB"), "preset": params.get("preset", "Master")}
    for k in _LEVEL_KEYS:
        out[k] = dict(block)
    return out


def _levels_1d(ch: np.ndarray, block: dict) -> np.ndarray:
    """Apply levels to a single channel (2D float [0,1])."""
    in_black = float(block["input_black"]) / 255.0
    in_white = float(block["input_white"]) / 255.0
    gamma = float(block["gamma"])
    out_black = float(block["output_black"]) / 255.0
    out_white = float(block["output_white"]) / 255.0

    gamma = np.clip(gamma, 0.1, 10.0)
    in_range = max(in_white - in_black, 1e-6)

    x = (ch - in_black) / in_range
    x = np.clip(x, 0.0, 1.0)
    if abs(gamma - 1.0) > 1e-6:
        x = np.power(x, 1.0 / gamma)
    return (x * (out_white - out_black) + out_black).astype(np.float32)


def _levels_rgb_uniform(rgb: np.ndarray, block: dict) -> np.ndarray:
    """Apply the same levels curve independently to R, G, and B."""
    out = np.empty_like(rgb, dtype=np.float32)
    for c in range(3):
        out[..., c] = _levels_1d(rgb[..., c], block)
    return out


class Levels(Adjustment):
    """Photoshop-style Levels: RGB composite curve plus per-channel curves."""

    def __init__(self) -> None:
        b = _default_block()
        super().__init__(
            "Levels",
            {
                "channel": "RGB",
                "preset": "Master",
                "levels_rgb": dict(b),
                "levels_red": dict(b),
                "levels_green": dict(b),
                "levels_blue": dict(b),
            },
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).copy()
        alpha = self._alpha(image)
        bundle = coerce_levels_bundle(params)

        rgb = _levels_rgb_uniform(rgb, bundle["levels_rgb"])
        rgb[..., 0] = _levels_1d(rgb[..., 0], bundle["levels_red"])
        rgb[..., 1] = _levels_1d(rgb[..., 1], bundle["levels_green"])
        rgb[..., 2] = _levels_1d(rgb[..., 2], bundle["levels_blue"])

        return self._merge(rgb, alpha)
