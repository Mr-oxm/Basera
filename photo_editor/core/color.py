"""Color representation, conversion utilities, and abstract fill system.

The fill system provides a unified way to describe solid colours,
linear gradients, and radial gradients.  Any text run, shape stroke,
or layer effect can reference a ``ColorFill`` rather than a plain
colour, enabling gradient-per-character text and similar features.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Sequence

import numpy as np


# ============================================================================
# Core Color
# ============================================================================

@dataclass(frozen=True)
class Color:
    """Immutable RGBA color in [0, 1] float space."""

    r: float = 0.0
    g: float = 0.0
    b: float = 0.0
    a: float = 1.0

    # ---- Constructors -------------------------------------------------------

    @classmethod
    def from_rgb8(cls, r: int, g: int, b: int, a: int = 255) -> Color:
        return cls(r / 255.0, g / 255.0, b / 255.0, a / 255.0)

    @classmethod
    def from_hex(cls, hex_str: str) -> Color:
        h = hex_str.lstrip("#")
        if len(h) == 6:
            return cls.from_rgb8(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        if len(h) == 8:
            return cls.from_rgb8(
                int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16),
            )
        raise ValueError(f"Invalid hex color: {hex_str}")

    @classmethod
    def from_array(cls, arr: np.ndarray) -> Color:
        """Create from an RGBA float32 array."""
        return cls(float(arr[0]), float(arr[1]), float(arr[2]),
                   float(arr[3]) if len(arr) > 3 else 1.0)

    # ---- Conversions --------------------------------------------------------

    def to_rgb8(self) -> tuple[int, int, int, int]:
        return (
            int(self.r * 255), int(self.g * 255),
            int(self.b * 255), int(self.a * 255),
        )

    def to_hex(self) -> str:
        r, g, b, a = self.to_rgb8()
        return f"#{r:02x}{g:02x}{b:02x}" if a == 255 else f"#{r:02x}{g:02x}{b:02x}{a:02x}"

    def to_array(self) -> np.ndarray:
        return np.array([self.r, self.g, self.b, self.a], dtype=np.float32)

    def lerp(self, other: Color, t: float) -> Color:
        """Linearly interpolate between *self* and *other*."""
        s = 1.0 - t
        return Color(
            self.r * s + other.r * t,
            self.g * s + other.g * t,
            self.b * s + other.b * t,
            self.a * s + other.a * t,
        )

    # ---- Presets ------------------------------------------------------------

    @classmethod
    def black(cls) -> Color:
        return cls(0.0, 0.0, 0.0, 1.0)

    @classmethod
    def white(cls) -> Color:
        return cls(1.0, 1.0, 1.0, 1.0)

    @classmethod
    def transparent(cls) -> Color:
        return cls(0.0, 0.0, 0.0, 0.0)


# ============================================================================
# Abstract Color Fill System
# ============================================================================

class FillType(Enum):
    """Discriminator for ColorFill subclasses."""
    SOLID = auto()
    LINEAR_GRADIENT = auto()
    RADIAL_GRADIENT = auto()


@dataclass(frozen=True)
class GradientStop:
    """A single stop in a gradient.  *position* is in [0, 1]."""
    position: float
    color: Color


@dataclass(frozen=True)
class ColorFill:
    """Base for all fill types.  Use the subclass constructors."""
    fill_type: FillType = FillType.SOLID

    # ---- Sampling -----------------------------------------------------------

    def sample(self, u: float = 0.0, v: float = 0.0) -> Color:
        """Return the colour at normalised coordinate *(u, v)*.

        For solids this ignores the arguments.  For gradients the
        coordinate maps along the gradient axis.
        """
        return Color.black()

    def sample_array(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        """Vectorised sample → (N, 4) float32 RGBA array."""
        c = self.sample()
        out = np.empty((u.shape[0], 4), dtype=np.float32)
        out[:] = c.to_array()
        return out

    def to_dict(self) -> dict:
        """Serialise to a plain dict for snapshot storage."""
        return {"fill_type": self.fill_type.name}

    @staticmethod
    def from_dict(d: dict) -> ColorFill:
        """Reconstruct from a snapshot dict."""
        ft = d.get("fill_type", "SOLID")
        if ft == "LINEAR_GRADIENT":
            stops = [GradientStop(s["pos"], Color(*s["rgba"])) for s in d["stops"]]
            return LinearGradient(stops=tuple(stops), angle=d.get("angle", 0.0))
        if ft == "RADIAL_GRADIENT":
            stops = [GradientStop(s["pos"], Color(*s["rgba"])) for s in d["stops"]]
            return RadialGradient(
                stops=tuple(stops),
                center=(d.get("cx", 0.5), d.get("cy", 0.5)),
                radius=d.get("radius", 0.5),
            )
        # Default: solid
        c = Color(*d["rgba"]) if "rgba" in d else Color.black()
        return SolidFill(color=c)


@dataclass(frozen=True)
class SolidFill(ColorFill):
    """Single flat colour."""
    fill_type: FillType = FillType.SOLID
    color: Color = field(default_factory=Color.black)

    def sample(self, u: float = 0.0, v: float = 0.0) -> Color:
        return self.color

    def sample_array(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        out = np.empty((u.shape[0], 4), dtype=np.float32)
        out[:] = self.color.to_array()
        return out

    def to_dict(self) -> dict:
        c = self.color
        return {"fill_type": "SOLID", "rgba": [c.r, c.g, c.b, c.a]}


def _lerp_stops(stops: Sequence[GradientStop], t: float) -> Color:
    """Evaluate a gradient at position *t* in [0, 1]."""
    if not stops:
        return Color.black()
    t = max(0.0, min(1.0, t))
    if t <= stops[0].position:
        return stops[0].color
    if t >= stops[-1].position:
        return stops[-1].color
    for i in range(len(stops) - 1):
        s0, s1 = stops[i], stops[i + 1]
        if s0.position <= t <= s1.position:
            span = s1.position - s0.position
            local = (t - s0.position) / span if span > 0 else 0.0
            return s0.color.lerp(s1.color, local)
    return stops[-1].color


def _lerp_stops_array(stops: Sequence[GradientStop], t: np.ndarray) -> np.ndarray:
    """Vectorised gradient evaluation → (N, 4) float32."""
    n = t.shape[0]
    out = np.empty((n, 4), dtype=np.float32)
    if not stops:
        out[:] = 0.0
        return out
    t = np.clip(t, 0.0, 1.0)
    # Build colour array from stops
    positions = np.array([s.position for s in stops], dtype=np.float32)
    colours = np.array([[s.color.r, s.color.g, s.color.b, s.color.a]
                        for s in stops], dtype=np.float32)
    # Use numpy interp per channel
    for ch in range(4):
        out[:, ch] = np.interp(t, positions, colours[:, ch])
    return out


@dataclass(frozen=True)
class LinearGradient(ColorFill):
    """Linear gradient along an angle (degrees, 0 = left→right)."""
    fill_type: FillType = FillType.LINEAR_GRADIENT
    stops: tuple[GradientStop, ...] = (
        GradientStop(0.0, Color.black()),
        GradientStop(1.0, Color.white()),
    )
    angle: float = 0.0  # degrees

    def sample(self, u: float = 0.0, v: float = 0.0) -> Color:
        rad = math.radians(self.angle)
        t = u * math.cos(rad) + v * math.sin(rad)
        return _lerp_stops(self.stops, t)

    def sample_array(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        rad = math.radians(self.angle)
        t = u * math.cos(rad) + v * math.sin(rad)
        return _lerp_stops_array(self.stops, t)

    def to_dict(self) -> dict:
        return {
            "fill_type": "LINEAR_GRADIENT",
            "angle": self.angle,
            "stops": [{"pos": s.position,
                        "rgba": [s.color.r, s.color.g, s.color.b, s.color.a]}
                       for s in self.stops],
        }


@dataclass(frozen=True)
class RadialGradient(ColorFill):
    """Radial gradient from *center* outward to *radius* (normalised coords)."""
    fill_type: FillType = FillType.RADIAL_GRADIENT
    stops: tuple[GradientStop, ...] = (
        GradientStop(0.0, Color.white()),
        GradientStop(1.0, Color.black()),
    )
    center: tuple[float, float] = (0.5, 0.5)
    radius: float = 0.5

    def sample(self, u: float = 0.0, v: float = 0.0) -> Color:
        dx = u - self.center[0]
        dy = v - self.center[1]
        dist = math.sqrt(dx * dx + dy * dy)
        t = dist / self.radius if self.radius > 0 else 1.0
        return _lerp_stops(self.stops, t)

    def sample_array(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        dx = u - self.center[0]
        dy = v - self.center[1]
        dist = np.sqrt(dx * dx + dy * dy)
        t = dist / self.radius if self.radius > 0 else np.ones_like(dist)
        return _lerp_stops_array(self.stops, t)

    def to_dict(self) -> dict:
        return {
            "fill_type": "RADIAL_GRADIENT",
            "cx": self.center[0], "cy": self.center[1],
            "radius": self.radius,
            "stops": [{"pos": s.position,
                        "rgba": [s.color.r, s.color.g, s.color.b, s.color.a]}
                       for s in self.stops],
        }
