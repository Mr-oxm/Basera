"""Vector styling system — fills, strokes, and paint descriptors.

Design
------
Following Affinity Designer / Illustrator's model, every ``VectorObject``
can have **multiple fills** and **multiple strokes**, each with independent
paint, opacity, and blend mode.  This enables layered appearance effects
(e.g. a solid fill, a gradient fill on top, a thin inner stroke and a
thick outer stroke) in a single object.

Paint types
-----------
* **SolidPaint** — flat RGBA colour
* **GradientPaint** — linear or radial gradient with arbitrary colour stops
* **PatternPaint** — tiled bitmap pattern (for hatching, textures)

Stroke features
---------------
* Variable width (per-node pressure / width profile)
* Dash patterns (gap/dash array + offset)
* Line caps: butt, round, square
* Line joins: miter, round, bevel
* Arrowheads (start / end markers)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Sequence

import numpy as np

from .geometry import Vec2

__all__ = [
    "VectorStyle",
    "VectorFill",
    "VectorStroke",
    "FillPaint",
    "SolidPaint",
    "GradientPaint",
    "GradientStop",
    "GradientType",
    "PatternPaint",
    "StrokeCap",
    "StrokeJoin",
    "DashPattern",
    "StrokeAlign",
    "WidthProfile",
]


# ---------------------------------------------------------------------------
#  Enums
# ---------------------------------------------------------------------------

class StrokeCap(Enum):
    BUTT = auto()
    ROUND = auto()
    SQUARE = auto()


class StrokeJoin(Enum):
    MITER = auto()
    ROUND = auto()
    BEVEL = auto()


class StrokeAlign(Enum):
    CENTER = auto()
    INSIDE = auto()
    OUTSIDE = auto()


class GradientType(Enum):
    LINEAR = auto()
    RADIAL = auto()
    CONICAL = auto()
    DIAMOND = auto()


# ---------------------------------------------------------------------------
#  Paint data
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class GradientStop:
    """A colour stop in a gradient."""
    offset: float                      # 0.0 – 1.0
    color: tuple[float, float, float, float]  # RGBA 0–1


class FillPaint:
    """Base class for paint descriptors."""
    pass


@dataclass(slots=True)
class SolidPaint(FillPaint):
    """Flat RGBA colour."""
    color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)

    def to_array(self) -> np.ndarray:
        return np.array(self.color, dtype=np.float32)


@dataclass
class GradientPaint(FillPaint):
    """Gradient fill with multiple stops and optional transform."""
    gradient_type: GradientType = GradientType.LINEAR
    stops: list[GradientStop] = field(default_factory=lambda: [
        GradientStop(0.0, (0.0, 0.0, 0.0, 1.0)),
        GradientStop(1.0, (1.0, 1.0, 1.0, 1.0)),
    ])
    # Line definition (for linear) or center/radius (for radial)
    start: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))
    end: Vec2 = field(default_factory=lambda: Vec2(1.0, 0.0))
    # Radial-specific
    radius: float = 1.0
    focal_offset: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))

    def color_at(self, t: float) -> tuple[float, float, float, float]:
        """Interpolate colour at position *t* (0–1) along the gradient."""
        t = max(0.0, min(1.0, t))
        if not self.stops:
            return (0.0, 0.0, 0.0, 1.0)
        if t <= self.stops[0].offset:
            return self.stops[0].color
        if t >= self.stops[-1].offset:
            return self.stops[-1].color
        for i in range(len(self.stops) - 1):
            s0, s1 = self.stops[i], self.stops[i + 1]
            if s0.offset <= t <= s1.offset:
                span = s1.offset - s0.offset
                if span < 1e-12:
                    return s0.color
                f = (t - s0.offset) / span
                return (
                    s0.color[0] + (s1.color[0] - s0.color[0]) * f,
                    s0.color[1] + (s1.color[1] - s0.color[1]) * f,
                    s0.color[2] + (s1.color[2] - s0.color[2]) * f,
                    s0.color[3] + (s1.color[3] - s0.color[3]) * f,
                )
        return self.stops[-1].color

    def sample_to_array(self, count: int = 256) -> np.ndarray:
        """Pre-compute a lookup table as (count, 4) float32 array."""
        lut = np.empty((count, 4), dtype=np.float32)
        for i in range(count):
            t = i / max(count - 1, 1)
            lut[i] = self.color_at(t)
        return lut


@dataclass
class PatternPaint(FillPaint):
    """Tiled bitmap pattern fill."""
    tile: np.ndarray = field(default_factory=lambda: np.ones((8, 8, 4), dtype=np.float32))
    scale: float = 1.0
    angle: float = 0.0
    offset: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))


# ---------------------------------------------------------------------------
#  Dash pattern
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class DashPattern:
    """Dash/gap pattern for stroked paths."""
    dashes: list[float] = field(default_factory=lambda: [])   # empty = solid
    offset: float = 0.0

    @property
    def is_solid(self) -> bool:
        return not self.dashes

    def expanded_pattern(self) -> list[float]:
        """Ensure even-length pattern (repeat if odd)."""
        if not self.dashes:
            return []
        if len(self.dashes) % 2 == 1:
            return self.dashes + self.dashes
        return list(self.dashes)


# ---------------------------------------------------------------------------
#  Width profile (variable-width strokes)
# ---------------------------------------------------------------------------

@dataclass
class WidthProfile:
    """Maps normalised position along path (0–1) to stroke width multiplier.

    ``points`` is a list of (position, left_width, right_width) tuples
    where widths are multipliers of the base stroke width.  The profile
    is linearly interpolated between points.
    """
    points: list[tuple[float, float, float]] = field(
        default_factory=lambda: [(0.0, 1.0, 1.0), (1.0, 1.0, 1.0)]
    )

    def width_at(self, t: float) -> tuple[float, float]:
        """Return (left_width, right_width) multipliers at position *t*."""
        t = max(0.0, min(1.0, t))
        if not self.points:
            return (1.0, 1.0)
        if t <= self.points[0][0]:
            return (self.points[0][1], self.points[0][2])
        if t >= self.points[-1][0]:
            return (self.points[-1][1], self.points[-1][2])
        for i in range(len(self.points) - 1):
            p0, p1 = self.points[i], self.points[i + 1]
            if p0[0] <= t <= p1[0]:
                span = p1[0] - p0[0]
                if span < 1e-12:
                    return (p0[1], p0[2])
                f = (t - p0[0]) / span
                return (
                    p0[1] + (p1[1] - p0[1]) * f,
                    p0[2] + (p1[2] - p0[2]) * f,
                )
        return (1.0, 1.0)

    @staticmethod
    def uniform() -> WidthProfile:
        return WidthProfile()

    @staticmethod
    def pressure_taper() -> WidthProfile:
        """Classic taper that narrows at both ends."""
        return WidthProfile([
            (0.00, 0.1, 0.1),
            (0.15, 0.8, 0.8),
            (0.50, 1.0, 1.0),
            (0.85, 0.8, 0.8),
            (1.00, 0.1, 0.1),
        ])


# ---------------------------------------------------------------------------
#  Fill and Stroke
# ---------------------------------------------------------------------------

@dataclass
class VectorFill:
    """A single fill entry in the appearance stack."""
    paint: FillPaint = field(default_factory=lambda: SolidPaint((0.0, 0.0, 0.0, 1.0)))
    opacity: float = 1.0
    visible: bool = True

    def effective_color_at(self, u: float = 0.0) -> np.ndarray:
        """Sample paint colour, returning float32 RGBA with opacity applied."""
        if isinstance(self.paint, SolidPaint):
            c = np.array(self.paint.color, dtype=np.float32)
        elif isinstance(self.paint, GradientPaint):
            c = np.array(self.paint.color_at(u), dtype=np.float32)
        else:
            c = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
        c[3] *= self.opacity
        return c


@dataclass
class VectorStroke:
    """A single stroke entry in the appearance stack."""
    paint: FillPaint = field(default_factory=lambda: SolidPaint((0.0, 0.0, 0.0, 1.0)))
    width: float = 1.0
    opacity: float = 1.0
    visible: bool = True
    cap: StrokeCap = StrokeCap.ROUND
    join: StrokeJoin = StrokeJoin.ROUND
    miter_limit: float = 4.0
    dash: DashPattern = field(default_factory=DashPattern)
    align: StrokeAlign = StrokeAlign.CENTER
    width_profile: WidthProfile = field(default_factory=WidthProfile.uniform)

    def effective_color(self) -> np.ndarray:
        if isinstance(self.paint, SolidPaint):
            c = np.array(self.paint.color, dtype=np.float32)
        elif isinstance(self.paint, GradientPaint):
            c = np.array(self.paint.color_at(0.5), dtype=np.float32)
        else:
            c = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
        c[3] *= self.opacity
        return c


# ---------------------------------------------------------------------------
#  Complete style stack
# ---------------------------------------------------------------------------

@dataclass
class VectorStyle:
    """Complete appearance for a vector object.

    Supports multiple fills and strokes rendered in stack order
    (fills first, then strokes, bottom to top).
    """
    fills: list[VectorFill] = field(default_factory=lambda: [
        VectorFill(SolidPaint((0.8, 0.8, 0.8, 1.0)))
    ])
    strokes: list[VectorStroke] = field(default_factory=lambda: [
        VectorStroke(SolidPaint((0.0, 0.0, 0.0, 1.0)), width=1.0)
    ])

    @property
    def has_visible_fill(self) -> bool:
        return any(f.visible and f.opacity > 0 for f in self.fills)

    @property
    def has_visible_stroke(self) -> bool:
        return any(s.visible and s.opacity > 0 and s.width > 0 for s in self.strokes)

    def max_stroke_width(self) -> float:
        return max((s.width for s in self.strokes if s.visible), default=0.0)

    def add_fill(self, fill: VectorFill | None = None) -> VectorFill:
        f = fill or VectorFill()
        self.fills.append(f)
        return f

    def add_stroke(self, stroke: VectorStroke | None = None) -> VectorStroke:
        s = stroke or VectorStroke()
        self.strokes.append(s)
        return s

    def remove_fill(self, index: int) -> None:
        if 0 <= index < len(self.fills):
            self.fills.pop(index)

    def remove_stroke(self, index: int) -> None:
        if 0 <= index < len(self.strokes):
            self.strokes.pop(index)

    # ---- Serialization ------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "fills": [_fill_to_dict(f) for f in self.fills],
            "strokes": [_stroke_to_dict(s) for s in self.strokes],
        }

    @staticmethod
    def from_dict(d: dict) -> VectorStyle:
        style = VectorStyle(fills=[], strokes=[])
        for fd in d.get("fills", []):
            style.fills.append(_fill_from_dict(fd))
        for sd in d.get("strokes", []):
            style.strokes.append(_stroke_from_dict(sd))
        return style

    @staticmethod
    def default_fill_only(
        r: float = 0.8, g: float = 0.8, b: float = 0.8, a: float = 1.0
    ) -> VectorStyle:
        return VectorStyle(
            fills=[VectorFill(SolidPaint((r, g, b, a)))],
            strokes=[],
        )

    @staticmethod
    def default_stroke_only(
        r: float = 0.0, g: float = 0.0, b: float = 0.0, a: float = 1.0,
        width: float = 1.0,
    ) -> VectorStyle:
        return VectorStyle(
            fills=[],
            strokes=[VectorStroke(SolidPaint((r, g, b, a)), width=width)],
        )


# ---------------------------------------------------------------------------
#  Serialization helpers
# ---------------------------------------------------------------------------

def _paint_to_dict(paint: FillPaint) -> dict:
    if isinstance(paint, SolidPaint):
        return {"type": "solid", "color": list(paint.color)}
    elif isinstance(paint, GradientPaint):
        return {
            "type": "gradient",
            "gradient_type": paint.gradient_type.name,
            "stops": [{"offset": s.offset, "color": list(s.color)} for s in paint.stops],
            "start": paint.start.to_tuple(),
            "end": paint.end.to_tuple(),
            "radius": paint.radius,
        }
    elif isinstance(paint, PatternPaint):
        return {"type": "pattern", "scale": paint.scale, "angle": paint.angle}
    return {"type": "solid", "color": [0, 0, 0, 1]}


def _paint_from_dict(d: dict) -> FillPaint:
    t = d.get("type", "solid")
    if t == "solid":
        return SolidPaint(tuple(d.get("color", [0, 0, 0, 1])))  # type: ignore[arg-type]
    elif t == "gradient":
        stops = [
            GradientStop(s["offset"], tuple(s["color"]))  # type: ignore[arg-type]
            for s in d.get("stops", [])
        ]
        return GradientPaint(
            gradient_type=GradientType[d.get("gradient_type", "LINEAR")],
            stops=stops,
            start=Vec2.from_tuple(d.get("start", (0, 0))),
            end=Vec2.from_tuple(d.get("end", (1, 0))),
            radius=d.get("radius", 1.0),
        )
    return SolidPaint()


def _fill_to_dict(f: VectorFill) -> dict:
    return {
        "paint": _paint_to_dict(f.paint),
        "opacity": f.opacity,
        "visible": f.visible,
    }


def _fill_from_dict(d: dict) -> VectorFill:
    return VectorFill(
        paint=_paint_from_dict(d.get("paint", {})),
        opacity=d.get("opacity", 1.0),
        visible=d.get("visible", True),
    )


def _stroke_to_dict(s: VectorStroke) -> dict:
    return {
        "paint": _paint_to_dict(s.paint),
        "width": s.width,
        "opacity": s.opacity,
        "visible": s.visible,
        "cap": s.cap.name,
        "join": s.join.name,
        "miter_limit": s.miter_limit,
        "dash": {"dashes": s.dash.dashes, "offset": s.dash.offset},
        "align": s.align.name,
    }


def _stroke_from_dict(d: dict) -> VectorStroke:
    dash_d = d.get("dash", {})
    return VectorStroke(
        paint=_paint_from_dict(d.get("paint", {})),
        width=d.get("width", 1.0),
        opacity=d.get("opacity", 1.0),
        visible=d.get("visible", True),
        cap=StrokeCap[d.get("cap", "ROUND")],
        join=StrokeJoin[d.get("join", "ROUND")],
        miter_limit=d.get("miter_limit", 4.0),
        dash=DashPattern(
            dashes=dash_d.get("dashes", []),
            offset=dash_d.get("offset", 0.0),
        ),
        align=StrokeAlign[d.get("align", "CENTER")],
    )
