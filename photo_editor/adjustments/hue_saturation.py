"""Hue / Saturation / Lightness (or HSV) with per–hue-range targets."""

from __future__ import annotations

import copy

import numpy as np

from .adjustment_base import Adjustment
from ..utils.color_utils import hsl_to_rgb, hsv_to_rgb, rgb_to_hsl, rgb_to_hsv


_TARGET_ORDER = ("master", "reds", "yellows", "greens", "cyans", "blues", "magentas")

_DEFAULT_RANGES: dict[str, tuple[float, float]] = {
    "master": (0.0, 360.0),
    "reds": (330.0, 30.0),
    "yellows": (30.0, 90.0),
    "greens": (90.0, 150.0),
    "cyans": (150.0, 210.0),
    "blues": (210.0, 270.0),
    "magentas": (270.0, 330.0),
}


def target_id_for_hue_degrees(h: float) -> str:
    """Map a hue in [0, 360) to the named range (reds, yellows, …), or *master* if none match."""
    h = float(h) % 360.0
    for tid in _TARGET_ORDER:
        if tid == "master":
            continue
        lo, hi = _DEFAULT_RANGES[tid]
        if lo <= hi:
            if lo <= h <= hi:
                return tid
        else:
            if h >= lo or h <= hi:
                return tid
    return "master"


def _default_targets() -> dict[str, dict]:
    return {
        k: {
            "hue": 0.0,
            "saturation": 0.0,
            "lightness": 0.0,
            "range_lo": float(_DEFAULT_RANGES[k][0]),
            "range_hi": float(_DEFAULT_RANGES[k][1]),
        }
        for k in _TARGET_ORDER
    }


def coerce_hue_saturation_params(params: dict | None) -> dict:
    if params is None:
        params = {}
    if isinstance(params.get("targets"), dict) and params["targets"]:
        base = _default_targets()
        for k in base:
            if k in params["targets"] and isinstance(params["targets"][k], dict):
                src = params["targets"][k]
                for fld in ("hue", "saturation", "lightness", "range_lo", "range_hi"):
                    if fld in src:
                        base[k][fld] = float(src[fld])
        at = params.get("active_target", "master")
        if at not in base:
            at = "master"
        return {
            "use_hsv": bool(params.get("use_hsv", False)),
            "active_target": at,
            "targets": base,
        }
    t = _default_targets()
    t["master"]["hue"] = float(params.get("hue", 0))
    t["master"]["saturation"] = float(params.get("saturation", 0))
    t["master"]["lightness"] = float(params.get("lightness", 0))
    return {
        "use_hsv": bool(params.get("use_hsv", False)),
        "active_target": "master",
        "targets": t,
    }


def _hue_weight(h: np.ndarray, lo: float, hi: float, feather: float = 18.0) -> np.ndarray:
    """Smooth mask [0,1] by hue; h in [0,1), lo/hi in degrees [0,360]."""
    hd = (h % 1.0) * 360.0
    feather = max(feather, 1e-3)
    if lo <= hi:
        inside = (hd >= lo) & (hd <= hi)
        d_low = np.abs(hd - lo)
        d_high = np.abs(hd - hi)
        dist = np.where(inside, 0.0, np.minimum(d_low, d_high))
    else:
        inside = (hd >= lo) | (hd <= hi)
        d_lo = np.minimum(np.abs(hd - lo), np.abs(hd - (lo - 360.0)))
        d_hi = np.minimum(np.abs(hd - hi), np.abs(hd - (hi + 360.0)))
        dist = np.where(inside, 0.0, np.minimum(d_lo, d_hi))
    return np.clip(1.0 - dist / feather, 0.0, 1.0).astype(np.float32)


def _shift_sat(s: np.ndarray, delta: float) -> np.ndarray:
    factor = delta / 100.0
    pos = factor > 0
    boosted = s + (1.0 - s) * factor
    reduced = s * (1.0 + factor)
    return np.clip(np.where(pos, boosted, reduced), 0.0, 1.0)


def _shift_light_or_value(x: np.ndarray, delta: float) -> np.ndarray:
    shift = delta / 100.0
    pos = shift > 0
    up = x + (1.0 - x) * shift
    down = x * (1.0 + shift)
    return np.clip(np.where(pos, up, down), 0.0, 1.0)


class HueSaturation(Adjustment):
    """Weighted multi-range hue/sat/light (or HSV) adjustments."""

    def __init__(self) -> None:
        super().__init__(
            "Hue/Saturation",
            {
                "use_hsv": False,
                "active_target": "master",
                "targets": copy.deepcopy(_default_targets()),
            },
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image)
        alpha = self._alpha(image)
        p = coerce_hue_saturation_params(params)
        targets = p["targets"]

        flat = all(
            abs(targets[k]["hue"]) < 1e-6
            and abs(targets[k]["saturation"]) < 1e-6
            and abs(targets[k]["lightness"]) < 1e-6
            for k in _TARGET_ORDER
        )
        if flat:
            return image.copy()

        h0: np.ndarray
        s_ch: np.ndarray
        lv: np.ndarray

        if p["use_hsv"]:
            hsv = rgb_to_hsv(rgb)
            h0, s_ch, lv = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        else:
            hsl = rgb_to_hsl(rgb)
            h0, s_ch, lv = hsl[..., 0], hsl[..., 1], hsl[..., 2]

        h_acc = h0.astype(np.float32).copy()
        s_acc = s_ch.astype(np.float32).copy()
        lv_acc = lv.astype(np.float32).copy()

        for name in _TARGET_ORDER:
            t = targets[name]
            w = _hue_weight(h0, t["range_lo"], t["range_hi"])
            dh = t["hue"] / 360.0
            h_acc = (h_acc + w * dh) % 1.0

        for name in _TARGET_ORDER:
            t = targets[name]
            w = _hue_weight(h0, t["range_lo"], t["range_hi"])
            s_tgt = _shift_sat(s_acc, t["saturation"])
            s_acc = s_acc + w * (s_tgt - s_acc)

        for name in _TARGET_ORDER:
            t = targets[name]
            w = _hue_weight(h0, t["range_lo"], t["range_hi"])
            lv_tgt = _shift_light_or_value(lv_acc, t["lightness"])
            lv_acc = lv_acc + w * (lv_tgt - lv_acc)

        if p["use_hsv"]:
            result = hsv_to_rgb(np.stack([h_acc, s_acc, lv_acc], axis=-1))
        else:
            result = hsl_to_rgb(np.stack([h_acc, s_acc, lv_acc], axis=-1))

        return self._merge(result, alpha)
