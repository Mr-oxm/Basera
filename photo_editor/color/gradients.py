"""Conical and diamond gradients, presets."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..core.color import Color, ColorFill, FillType, GradientStop, LinearGradient, RadialGradient
from .conversions import hsv_to_rgb


@dataclass(frozen=True)
class ConicalGradient(ColorFill):
    """Sweep/conical gradient around a center point."""
    fill_type: FillType = FillType.LINEAR_GRADIENT  # reuse enum
    stops: tuple[GradientStop, ...] = (
        GradientStop(0.0, Color.black()),
        GradientStop(1.0, Color.white()),
    )
    center: tuple[float, float] = (0.5, 0.5)
    start_angle: float = 0.0  # degrees

    def sample(self, u: float = 0.0, v: float = 0.0) -> Color:
        dx = u - self.center[0]
        dy = v - self.center[1]
        angle = math.degrees(math.atan2(dy, dx)) - self.start_angle
        t = (angle % 360) / 360.0
        from ..core.color import _lerp_stops
        return _lerp_stops(self.stops, t)


@dataclass(frozen=True)
class DiamondGradient(ColorFill):
    """Diamond-shaped gradient from center outward."""
    fill_type: FillType = FillType.RADIAL_GRADIENT  # reuse enum
    stops: tuple[GradientStop, ...] = (
        GradientStop(0.0, Color.white()),
        GradientStop(1.0, Color.black()),
    )
    center: tuple[float, float] = (0.5, 0.5)
    radius: float = 0.5

    def sample(self, u: float = 0.0, v: float = 0.0) -> Color:
        dx = abs(u - self.center[0])
        dy = abs(v - self.center[1])
        dist = (dx + dy) / self.radius if self.radius > 0 else 1.0
        from ..core.color import _lerp_stops
        return _lerp_stops(self.stops, min(1.0, dist))


# ============================================================================
# Gradient Presets
# ============================================================================

GRADIENT_PRESETS: dict[str, tuple[GradientStop, ...]] = {
    "Black to White": (
        GradientStop(0.0, Color.black()),
        GradientStop(1.0, Color.white()),
    ),
    "Foreground to Transparent": (
        GradientStop(0.0, Color.black()),
        GradientStop(1.0, Color.transparent()),
    ),
    "Spectrum": tuple(
        GradientStop(i / 6.0, Color(*hsv_to_rgb(i * 60, 1.0, 1.0)))
        for i in range(7)
    ),
    "Sunset": (
        GradientStop(0.0, Color.from_hex("#FF512F")),
        GradientStop(0.5, Color.from_hex("#F09819")),
        GradientStop(1.0, Color.from_hex("#DD2476")),
    ),
    "Ocean": (
        GradientStop(0.0, Color.from_hex("#2E3192")),
        GradientStop(0.5, Color.from_hex("#1BFFFF")),
        GradientStop(1.0, Color.from_hex("#2E3192")),
    ),
    "Fire": (
        GradientStop(0.0, Color.from_hex("#f12711")),
        GradientStop(0.5, Color.from_hex("#f5af19")),
        GradientStop(1.0, Color.from_hex("#f12711")),
    ),
}
