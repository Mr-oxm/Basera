"""Swatch palette management."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.color import Color
from .conversions import hsv_to_rgb


@dataclass
class SwatchPalette:
    """A named collection of colour swatches."""
    name: str = "Default"
    colors: list[Color] = field(default_factory=list)

    @staticmethod
    def default_palette() -> SwatchPalette:
        """Create a standard starter palette."""
        colors: list[Color] = []
        for v in range(0, 256, 32):
            colors.append(Color.from_rgb8(v, v, v))
        for h_deg in range(0, 360, 15):
            r, g, b = hsv_to_rgb(float(h_deg), 1.0, 1.0)
            colors.append(Color(r, g, b))
        for h_deg in range(0, 360, 15):
            r, g, b = hsv_to_rgb(float(h_deg), 0.4, 1.0)
            colors.append(Color(r, g, b))
        for h_deg in range(0, 360, 15):
            r, g, b = hsv_to_rgb(float(h_deg), 1.0, 0.5)
            colors.append(Color(r, g, b))
        return SwatchPalette("Default", colors)
