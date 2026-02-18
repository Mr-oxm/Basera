"""Color harmony generation — complementary, analogous, triadic, etc."""

from __future__ import annotations

from enum import Enum, auto

from ..core.color import Color
from .conversions import rgb_to_hsv, hsv_to_rgb


class HarmonyType(Enum):
    COMPLEMENTARY = auto()
    ANALOGOUS = auto()
    TRIADIC = auto()
    SPLIT_COMPLEMENTARY = auto()
    TETRADIC = auto()
    SQUARE = auto()
    MONOCHROMATIC = auto()


def generate_harmony(base: Color, harmony: HarmonyType) -> list[Color]:
    """Generate a list of harmonious colours from *base*."""
    h, s, v = rgb_to_hsv(base.r, base.g, base.b)

    def _rotated(deg: float) -> Color:
        r, g, b = hsv_to_rgb((h + deg) % 360, s, v)
        return Color(r, g, b, base.a)

    if harmony == HarmonyType.COMPLEMENTARY:
        return [base, _rotated(180)]
    elif harmony == HarmonyType.ANALOGOUS:
        return [_rotated(-30), base, _rotated(30)]
    elif harmony == HarmonyType.TRIADIC:
        return [base, _rotated(120), _rotated(240)]
    elif harmony == HarmonyType.SPLIT_COMPLEMENTARY:
        return [base, _rotated(150), _rotated(210)]
    elif harmony == HarmonyType.TETRADIC:
        return [base, _rotated(90), _rotated(180), _rotated(270)]
    elif harmony == HarmonyType.SQUARE:
        return [base, _rotated(90), _rotated(180), _rotated(270)]
    elif harmony == HarmonyType.MONOCHROMATIC:
        results = []
        for vf in [0.2, 0.4, 0.6, 0.8, 1.0]:
            r, g, b = hsv_to_rgb(h, s, v * vf)
            results.append(Color(r, g, b, base.a))
        return results
    return [base]
