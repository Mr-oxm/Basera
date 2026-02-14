"""Live-parameter shape primitives.

Each shape class stores its *semantic* parameters (e.g. corner radius for
a rectangle, number of sides for a polygon) and generates a ``VectorPath``
on demand via ``to_path()``.  The generated path is cached and invalidated
when parameters change.

This gives the user:
1. Non-destructive editing — change corner radius after creation
2. Efficient storage — only the parameters are saved, not the full path
3. Consistent behaviour — ``to_path()`` always returns a clean path that
   the rasteriser and boolean engine can consume

All shapes are positioned in **local coordinates** centred at the shape's
origin.  The ``VectorObject`` transform positions them in the document.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .geometry import Vec2, BBox
from .path import (
    VectorPath, SubPath, PathNode, HandleMode,
)

__all__ = [
    "ShapePrimitive",
    "RectangleShape",
    "EllipseShape",
    "PolygonShape",
    "StarShape",
    "LineShape",
    "TriangleShape",
    "ArrowShape",
    "HeartShape",
    "DiamondShape",
    "CrossShape",
    "RingShape",
    "TrapezoidShape",
    "ParallelogramShape",
    "CrescentShape",
    "SpeechBubbleShape",
]


# ---------------------------------------------------------------------------
#  Base
# ---------------------------------------------------------------------------

class ShapePrimitive:
    """Abstract base for parametric shapes."""

    def to_path(self) -> VectorPath:
        raise NotImplementedError

    def bbox(self) -> BBox:
        return self.to_path().bbox()

    def to_dict(self) -> dict:
        raise NotImplementedError

    @staticmethod
    def from_dict(d: dict) -> ShapePrimitive:
        kind = d.get("type", "")
        _MAP = {
            "rectangle": RectangleShape,
            "ellipse": EllipseShape,
            "polygon": PolygonShape,
            "star": StarShape,
            "line": LineShape,
            "triangle": TriangleShape,
            "arrow": ArrowShape,
            "heart": HeartShape,
            "diamond": DiamondShape,
            "cross": CrossShape,
            "ring": RingShape,
            "trapezoid": TrapezoidShape,
            "parallelogram": ParallelogramShape,
            "crescent": CrescentShape,
            "speech_bubble": SpeechBubbleShape,
        }
        cls = _MAP.get(kind)
        if cls is not None:
            return cls.from_dict(d)
        raise ValueError(f"Unknown shape type: {kind}")


# ---------------------------------------------------------------------------
#  Rectangle
# ---------------------------------------------------------------------------

@dataclass
class RectangleShape(ShapePrimitive):
    """Axis-aligned rectangle with optional independent corner radii."""

    width: float = 100.0
    height: float = 100.0
    # Per-corner radii: top-left, top-right, bottom-right, bottom-left
    corner_radii: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    def to_path(self) -> VectorPath:
        w, h = self.width, self.height
        hw, hh = w * 0.5, h * 0.5
        r_tl, r_tr, r_br, r_bl = self.corner_radii
        # Clamp radii
        max_r = min(hw, hh)
        r_tl = min(r_tl, max_r)
        r_tr = min(r_tr, max_r)
        r_br = min(r_br, max_r)
        r_bl = min(r_bl, max_r)

        # Approximate circular arc with cubic Bézier: kappa ≈ 0.5522847498
        K = 0.5522847498

        nodes: list[PathNode] = []

        if r_tl <= 0 and r_tr <= 0 and r_br <= 0 and r_bl <= 0:
            # Simple rectangle — no radii
            nodes = [
                PathNode(Vec2(-hw, -hh), mode=HandleMode.SHARP),
                PathNode(Vec2(hw, -hh), mode=HandleMode.SHARP),
                PathNode(Vec2(hw, hh), mode=HandleMode.SHARP),
                PathNode(Vec2(-hw, hh), mode=HandleMode.SHARP),
            ]
        else:
            # Rounded rectangle — 8 nodes (2 per corner)
            # Top edge (left to right)
            nodes.append(PathNode(
                position=Vec2(-hw + r_tl, -hh),
                out_handle=Vec2(-hw + r_tl, -hh),  # straight segment
                mode=HandleMode.SHARP,
            ))
            nodes.append(PathNode(
                position=Vec2(hw - r_tr, -hh),
                mode=HandleMode.SHARP,
            ))
            # Top-right corner
            if r_tr > 0:
                nodes[-1].out_handle = Vec2(hw - r_tr + r_tr * K, -hh)
                nodes.append(PathNode(
                    position=Vec2(hw, -hh + r_tr),
                    in_handle=Vec2(hw, -hh + r_tr - r_tr * K),
                    mode=HandleMode.SMOOTH,
                ))
            else:
                nodes.append(PathNode(Vec2(hw, -hh), mode=HandleMode.SHARP))
            # Right edge
            nodes.append(PathNode(
                position=Vec2(hw, hh - r_br),
                mode=HandleMode.SHARP,
            ))
            # Bottom-right corner
            if r_br > 0:
                nodes[-1].out_handle = Vec2(hw, hh - r_br + r_br * K)
                nodes.append(PathNode(
                    position=Vec2(hw - r_br, hh),
                    in_handle=Vec2(hw - r_br + r_br * K, hh),
                    mode=HandleMode.SMOOTH,
                ))
            else:
                nodes.append(PathNode(Vec2(hw, hh), mode=HandleMode.SHARP))
            # Bottom edge
            nodes.append(PathNode(
                position=Vec2(-hw + r_bl, hh),
                mode=HandleMode.SHARP,
            ))
            # Bottom-left corner
            if r_bl > 0:
                nodes[-1].out_handle = Vec2(-hw + r_bl - r_bl * K, hh)
                nodes.append(PathNode(
                    position=Vec2(-hw, hh - r_bl),
                    in_handle=Vec2(-hw, hh - r_bl + r_bl * K),
                    mode=HandleMode.SMOOTH,
                ))
            else:
                nodes.append(PathNode(Vec2(-hw, hh), mode=HandleMode.SHARP))
            # Left edge
            nodes.append(PathNode(
                position=Vec2(-hw, -hh + r_tl),
                mode=HandleMode.SHARP,
            ))
            # Top-left corner (closing)
            if r_tl > 0:
                nodes[-1].out_handle = Vec2(-hw, -hh + r_tl - r_tl * K)
                nodes[0].in_handle = Vec2(-hw + r_tl - r_tl * K, -hh)

        sp = SubPath(nodes, closed=True)
        return VectorPath([sp])

    def to_dict(self) -> dict:
        return {
            "type": "rectangle",
            "width": self.width,
            "height": self.height,
            "corner_radii": list(self.corner_radii),
        }

    @staticmethod
    def from_dict(d: dict) -> RectangleShape:
        return RectangleShape(
            width=d.get("width", 100.0),
            height=d.get("height", 100.0),
            corner_radii=tuple(d.get("corner_radii", [0, 0, 0, 0])),  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
#  Ellipse
# ---------------------------------------------------------------------------

@dataclass
class EllipseShape(ShapePrimitive):
    """Ellipse (or circle) with optional start/end angles for arcs."""

    rx: float = 50.0        # Semi-axis X
    ry: float = 50.0        # Semi-axis Y
    start_angle: float = 0.0    # Degrees, for arcs
    end_angle: float = 360.0    # Degrees, for arcs
    inner_radius: float = 0.0   # 0–1, for donuts

    def to_path(self) -> VectorPath:
        # Full ellipse approximation using 4 cubic Béziers (kappa method)
        K = 0.5522847498
        rx, ry = self.rx, self.ry

        if abs(self.end_angle - self.start_angle) >= 360.0 and self.inner_radius <= 0.0:
            # Full ellipse
            nodes = [
                PathNode(
                    position=Vec2(rx, 0.0),
                    in_handle=Vec2(rx, ry * K),
                    out_handle=Vec2(rx, -ry * K),
                    mode=HandleMode.SMOOTH,
                ),
                PathNode(
                    position=Vec2(0.0, -ry),
                    in_handle=Vec2(rx * K, -ry),
                    out_handle=Vec2(-rx * K, -ry),
                    mode=HandleMode.SMOOTH,
                ),
                PathNode(
                    position=Vec2(-rx, 0.0),
                    in_handle=Vec2(-rx, -ry * K),
                    out_handle=Vec2(-rx, ry * K),
                    mode=HandleMode.SMOOTH,
                ),
                PathNode(
                    position=Vec2(0.0, ry),
                    in_handle=Vec2(-rx * K, ry),
                    out_handle=Vec2(rx * K, ry),
                    mode=HandleMode.SMOOTH,
                ),
            ]
            sp = SubPath(nodes, closed=True)
            return VectorPath([sp])
        else:
            # Arc — sample points
            return self._arc_path()

    def _arc_path(self) -> VectorPath:
        """Generate parametric arc path."""
        start_rad = math.radians(self.start_angle)
        end_rad = math.radians(self.end_angle)
        steps = max(8, int(abs(self.end_angle - self.start_angle) / 10))
        nodes: list[PathNode] = []
        for i in range(steps + 1):
            t = i / steps
            angle = start_rad + (end_rad - start_rad) * t
            x = self.rx * math.cos(angle)
            y = self.ry * math.sin(angle)
            node = PathNode(position=Vec2(x, y), mode=HandleMode.SMOOTH)
            # Compute tangent for handle placement
            dx = -self.rx * math.sin(angle)
            dy = self.ry * math.cos(angle)
            handle_len = (end_rad - start_rad) / steps / 3.0
            node.out_handle = Vec2(x + dx * handle_len, y + dy * handle_len)
            node.in_handle = Vec2(x - dx * handle_len, y - dy * handle_len)
            nodes.append(node)

        closed = abs(self.end_angle - self.start_angle) >= 360.0
        if self.inner_radius > 0.0:
            # Donut — add inner contour
            inner_nodes: list[PathNode] = []
            irx = self.rx * self.inner_radius
            iry = self.ry * self.inner_radius
            for i in range(steps, -1, -1):
                t = i / steps
                angle = start_rad + (end_rad - start_rad) * t
                x = irx * math.cos(angle)
                y = iry * math.sin(angle)
                node = PathNode(position=Vec2(x, y), mode=HandleMode.SMOOTH)
                dx = -irx * math.sin(angle)
                dy = iry * math.cos(angle)
                handle_len = (end_rad - start_rad) / steps / 3.0
                node.in_handle = Vec2(x + dx * handle_len, y + dy * handle_len)
                node.out_handle = Vec2(x - dx * handle_len, y - dy * handle_len)
                inner_nodes.append(node)
            sp_outer = SubPath(nodes, closed=True)
            sp_inner = SubPath(inner_nodes, closed=True)
            return VectorPath([sp_outer, sp_inner])

        sp = SubPath(nodes, closed=closed)
        return VectorPath([sp])

    def to_dict(self) -> dict:
        return {
            "type": "ellipse",
            "rx": self.rx,
            "ry": self.ry,
            "start_angle": self.start_angle,
            "end_angle": self.end_angle,
            "inner_radius": self.inner_radius,
        }

    @staticmethod
    def from_dict(d: dict) -> EllipseShape:
        return EllipseShape(
            rx=d.get("rx", 50.0),
            ry=d.get("ry", 50.0),
            start_angle=d.get("start_angle", 0.0),
            end_angle=d.get("end_angle", 360.0),
            inner_radius=d.get("inner_radius", 0.0),
        )


# ---------------------------------------------------------------------------
#  Regular polygon
# ---------------------------------------------------------------------------

@dataclass
class PolygonShape(ShapePrimitive):
    """Regular polygon with optional corner rounding."""

    sides: int = 6
    radius: float = 50.0
    corner_radius: float = 0.0
    rotation: float = 0.0   # Degrees

    def to_path(self) -> VectorPath:
        nodes: list[PathNode] = []
        rot_rad = math.radians(self.rotation) - math.pi / 2  # Start at top

        for i in range(self.sides):
            angle = rot_rad + 2.0 * math.pi * i / self.sides
            x = self.radius * math.cos(angle)
            y = self.radius * math.sin(angle)
            node = PathNode(position=Vec2(x, y), mode=HandleMode.SHARP)

            if self.corner_radius > 0:
                # Add smooth handles for rounding
                prev_angle = rot_rad + 2.0 * math.pi * ((i - 1) % self.sides) / self.sides
                next_angle = rot_rad + 2.0 * math.pi * ((i + 1) % self.sides) / self.sides
                # Direction to previous and next vertex
                to_prev = Vec2(math.cos(prev_angle), math.sin(prev_angle)) - Vec2(math.cos(angle), math.sin(angle))
                to_next = Vec2(math.cos(next_angle), math.sin(next_angle)) - Vec2(math.cos(angle), math.sin(angle))
                to_prev_n = to_prev.normalized()
                to_next_n = to_next.normalized()
                r = min(self.corner_radius, self.radius * 0.4)
                node.in_handle = Vec2(x + to_prev_n.x * r * 0.45, y + to_prev_n.y * r * 0.45)
                node.out_handle = Vec2(x + to_next_n.x * r * 0.45, y + to_next_n.y * r * 0.45)
                node.mode = HandleMode.SMOOTH

            nodes.append(node)

        sp = SubPath(nodes, closed=True)
        return VectorPath([sp])

    def to_dict(self) -> dict:
        return {
            "type": "polygon",
            "sides": self.sides,
            "radius": self.radius,
            "corner_radius": self.corner_radius,
            "rotation": self.rotation,
        }

    @staticmethod
    def from_dict(d: dict) -> PolygonShape:
        return PolygonShape(
            sides=d.get("sides", 6),
            radius=d.get("radius", 50.0),
            corner_radius=d.get("corner_radius", 0.0),
            rotation=d.get("rotation", 0.0),
        )


# ---------------------------------------------------------------------------
#  Star
# ---------------------------------------------------------------------------

@dataclass
class StarShape(ShapePrimitive):
    """Star polygon with inner/outer radii and optional smoothing."""

    points: int = 5
    outer_radius: float = 50.0
    inner_radius: float = 25.0
    corner_radius: float = 0.0
    inner_corner_radius: float = 0.0
    rotation: float = 0.0

    def to_path(self) -> VectorPath:
        nodes: list[PathNode] = []
        rot_rad = math.radians(self.rotation) - math.pi / 2
        n2 = self.points * 2

        for i in range(n2):
            angle = rot_rad + 2.0 * math.pi * i / n2
            r = self.outer_radius if i % 2 == 0 else self.inner_radius
            x = r * math.cos(angle)
            y = r * math.sin(angle)

            cr = self.corner_radius if i % 2 == 0 else self.inner_corner_radius
            if cr > 0:
                node = PathNode(position=Vec2(x, y), mode=HandleMode.SMOOTH)
                # Direction perpendicular to radius
                prev_angle = rot_rad + 2.0 * math.pi * ((i - 1) % n2) / n2
                next_angle = rot_rad + 2.0 * math.pi * ((i + 1) % n2) / n2
                r_prev = self.inner_radius if i % 2 == 0 else self.outer_radius
                r_next = self.inner_radius if i % 2 == 0 else self.outer_radius
                px = r_prev * math.cos(prev_angle)
                py = r_prev * math.sin(prev_angle)
                nx = r_next * math.cos(next_angle)
                ny = r_next * math.sin(next_angle)
                to_prev = Vec2(px - x, py - y).normalized()
                to_next = Vec2(nx - x, ny - y).normalized()
                handle_len = cr * 0.45
                node.in_handle = Vec2(x + to_prev.x * handle_len, y + to_prev.y * handle_len)
                node.out_handle = Vec2(x + to_next.x * handle_len, y + to_next.y * handle_len)
            else:
                node = PathNode(position=Vec2(x, y), mode=HandleMode.SHARP)
            nodes.append(node)

        sp = SubPath(nodes, closed=True)
        return VectorPath([sp])

    def to_dict(self) -> dict:
        return {
            "type": "star",
            "points": self.points,
            "outer_radius": self.outer_radius,
            "inner_radius": self.inner_radius,
            "corner_radius": self.corner_radius,
            "inner_corner_radius": self.inner_corner_radius,
            "rotation": self.rotation,
        }

    @staticmethod
    def from_dict(d: dict) -> StarShape:
        return StarShape(
            points=d.get("points", 5),
            outer_radius=d.get("outer_radius", 50.0),
            inner_radius=d.get("inner_radius", 25.0),
            corner_radius=d.get("corner_radius", 0.0),
            inner_corner_radius=d.get("inner_corner_radius", 0.0),
            rotation=d.get("rotation", 0.0),
        )


# ---------------------------------------------------------------------------
#  Line
# ---------------------------------------------------------------------------

@dataclass
class LineShape(ShapePrimitive):
    """Simple two-point line."""

    start: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))
    end: Vec2 = field(default_factory=lambda: Vec2(100.0, 0.0))

    def to_path(self) -> VectorPath:
        nodes = [
            PathNode(position=self.start, mode=HandleMode.SHARP),
            PathNode(position=self.end, mode=HandleMode.SHARP),
        ]
        sp = SubPath(nodes, closed=False)
        return VectorPath([sp])

    def to_dict(self) -> dict:
        return {
            "type": "line",
            "start": self.start.to_tuple(),
            "end": self.end.to_tuple(),
        }

    @staticmethod
    def from_dict(d: dict) -> LineShape:
        return LineShape(
            start=Vec2.from_tuple(d.get("start", (0, 0))),
            end=Vec2.from_tuple(d.get("end", (100, 0))),
        )


# ---------------------------------------------------------------------------
#  Triangle
# ---------------------------------------------------------------------------

@dataclass
class TriangleShape(ShapePrimitive):
    """Isosceles triangle centred at origin."""

    width: float = 100.0
    height: float = 100.0

    def to_path(self) -> VectorPath:
        hw, hh = self.width * 0.5, self.height * 0.5
        nodes = [
            PathNode(position=Vec2(0.0, -hh), mode=HandleMode.SHARP),
            PathNode(position=Vec2(hw, hh), mode=HandleMode.SHARP),
            PathNode(position=Vec2(-hw, hh), mode=HandleMode.SHARP),
        ]
        return VectorPath([SubPath(nodes, closed=True)])

    def to_dict(self) -> dict:
        return {"type": "triangle", "width": self.width, "height": self.height}

    @staticmethod
    def from_dict(d: dict) -> TriangleShape:
        return TriangleShape(d.get("width", 100.0), d.get("height", 100.0))


# ---------------------------------------------------------------------------
#  Arrow
# ---------------------------------------------------------------------------

@dataclass
class ArrowShape(ShapePrimitive):
    """Right-pointing arrow.  *head_length* and *shaft_width* are 0-1 ratios."""

    width: float = 120.0
    height: float = 60.0
    head_length: float = 0.4
    shaft_width: float = 0.4

    def to_path(self) -> VectorPath:
        hw, hh = self.width * 0.5, self.height * 0.5
        hl = self.width * max(0.1, min(self.head_length, 0.9))
        sw = self.height * max(0.1, min(self.shaft_width, 0.9)) * 0.5
        tip_x = hw
        notch_x = hw - hl
        nodes = [
            PathNode(position=Vec2(-hw, -sw), mode=HandleMode.SHARP),
            PathNode(position=Vec2(notch_x, -sw), mode=HandleMode.SHARP),
            PathNode(position=Vec2(notch_x, -hh), mode=HandleMode.SHARP),
            PathNode(position=Vec2(tip_x, 0.0), mode=HandleMode.SHARP),
            PathNode(position=Vec2(notch_x, hh), mode=HandleMode.SHARP),
            PathNode(position=Vec2(notch_x, sw), mode=HandleMode.SHARP),
            PathNode(position=Vec2(-hw, sw), mode=HandleMode.SHARP),
        ]
        return VectorPath([SubPath(nodes, closed=True)])

    def to_dict(self) -> dict:
        return {"type": "arrow", "width": self.width, "height": self.height,
                "head_length": self.head_length, "shaft_width": self.shaft_width}

    @staticmethod
    def from_dict(d: dict) -> ArrowShape:
        return ArrowShape(d.get("width", 120.0), d.get("height", 60.0),
                          d.get("head_length", 0.4), d.get("shaft_width", 0.4))


# ---------------------------------------------------------------------------
#  Heart
# ---------------------------------------------------------------------------

@dataclass
class HeartShape(ShapePrimitive):
    """Approximate heart via cubic Béziers."""

    width: float = 100.0
    height: float = 100.0

    def to_path(self) -> VectorPath:
        hw, hh = self.width * 0.5, self.height * 0.5
        # Build heart with cubics: bottom tip → right lobe → top dip → left lobe → back
        bottom = Vec2(0.0, hh)
        top_dip = Vec2(0.0, -hh * 0.35)
        right_top = Vec2(hw, -hh)
        left_top = Vec2(-hw, -hh)

        n0 = PathNode(position=bottom, mode=HandleMode.SHARP)
        n1 = PathNode(
            position=right_top,
            in_handle=Vec2(hw * 0.65, hh * 0.15),
            out_handle=Vec2(hw * 1.0, -hh * 0.65),
            mode=HandleMode.SMOOTH,
        )
        n2 = PathNode(
            position=top_dip,
            in_handle=Vec2(hw * 0.35, -hh * 0.9),
            out_handle=Vec2(-hw * 0.35, -hh * 0.9),
            mode=HandleMode.SMOOTH,
        )
        n3 = PathNode(
            position=left_top,
            in_handle=Vec2(-hw * 1.0, -hh * 0.65),
            out_handle=Vec2(-hw * 0.65, hh * 0.15),
            mode=HandleMode.SMOOTH,
        )
        return VectorPath([SubPath([n0, n1, n2, n3], closed=True)])

    def to_dict(self) -> dict:
        return {"type": "heart", "width": self.width, "height": self.height}

    @staticmethod
    def from_dict(d: dict) -> HeartShape:
        return HeartShape(d.get("width", 100.0), d.get("height", 100.0))


# ---------------------------------------------------------------------------
#  Diamond
# ---------------------------------------------------------------------------

@dataclass
class DiamondShape(ShapePrimitive):
    """Axis-aligned rhombus."""

    width: float = 100.0
    height: float = 100.0

    def to_path(self) -> VectorPath:
        hw, hh = self.width * 0.5, self.height * 0.5
        nodes = [
            PathNode(position=Vec2(0.0, -hh), mode=HandleMode.SHARP),
            PathNode(position=Vec2(hw, 0.0), mode=HandleMode.SHARP),
            PathNode(position=Vec2(0.0, hh), mode=HandleMode.SHARP),
            PathNode(position=Vec2(-hw, 0.0), mode=HandleMode.SHARP),
        ]
        return VectorPath([SubPath(nodes, closed=True)])

    def to_dict(self) -> dict:
        return {"type": "diamond", "width": self.width, "height": self.height}

    @staticmethod
    def from_dict(d: dict) -> DiamondShape:
        return DiamondShape(d.get("width", 100.0), d.get("height", 100.0))


# ---------------------------------------------------------------------------
#  Cross / Plus
# ---------------------------------------------------------------------------

@dataclass
class CrossShape(ShapePrimitive):
    """Plus / cross shape.  *arm_ratio* (0-1) is arm width relative to size."""

    width: float = 100.0
    height: float = 100.0
    arm_ratio: float = 0.33

    def to_path(self) -> VectorPath:
        hw, hh = self.width * 0.5, self.height * 0.5
        a = max(0.05, min(self.arm_ratio, 0.95))
        ax, ay = hw * a, hh * a
        nodes = [
            PathNode(position=Vec2(-ax, -hh), mode=HandleMode.SHARP),
            PathNode(position=Vec2(ax, -hh), mode=HandleMode.SHARP),
            PathNode(position=Vec2(ax, -ay), mode=HandleMode.SHARP),
            PathNode(position=Vec2(hw, -ay), mode=HandleMode.SHARP),
            PathNode(position=Vec2(hw, ay), mode=HandleMode.SHARP),
            PathNode(position=Vec2(ax, ay), mode=HandleMode.SHARP),
            PathNode(position=Vec2(ax, hh), mode=HandleMode.SHARP),
            PathNode(position=Vec2(-ax, hh), mode=HandleMode.SHARP),
            PathNode(position=Vec2(-ax, ay), mode=HandleMode.SHARP),
            PathNode(position=Vec2(-hw, ay), mode=HandleMode.SHARP),
            PathNode(position=Vec2(-hw, -ay), mode=HandleMode.SHARP),
            PathNode(position=Vec2(-ax, -ay), mode=HandleMode.SHARP),
        ]
        return VectorPath([SubPath(nodes, closed=True)])

    def to_dict(self) -> dict:
        return {"type": "cross", "width": self.width, "height": self.height,
                "arm_ratio": self.arm_ratio}

    @staticmethod
    def from_dict(d: dict) -> CrossShape:
        return CrossShape(d.get("width", 100.0), d.get("height", 100.0),
                          d.get("arm_ratio", 0.33))


# ---------------------------------------------------------------------------
#  Ring / Donut
# ---------------------------------------------------------------------------

@dataclass
class RingShape(ShapePrimitive):
    """Annular ring (outer ellipse minus inner ellipse).

    *thickness* is 0-1 fraction of the radius reserved for the ring wall.
    """

    rx: float = 50.0
    ry: float = 50.0
    thickness: float = 0.3

    def to_path(self) -> VectorPath:
        t = max(0.05, min(self.thickness, 0.95))
        outer = self._ellipse_sp(self.rx, self.ry, clockwise=True)
        inner = self._ellipse_sp(self.rx * (1.0 - t), self.ry * (1.0 - t), clockwise=False)
        return VectorPath([outer, inner])

    @staticmethod
    def _ellipse_sp(rx: float, ry: float, clockwise: bool = True) -> SubPath:
        k = 0.5522847498  # cubic approx constant
        kx, ky = rx * k, ry * k
        if clockwise:
            pts = [
                (Vec2(0, -ry), Vec2(kx, -ry), Vec2(-kx, -ry)),
                (Vec2(rx, 0), Vec2(rx, -ky), Vec2(rx, ky)),
                (Vec2(0, ry), Vec2(-kx, ry), Vec2(kx, ry)),
                (Vec2(-rx, 0), Vec2(-rx, ky), Vec2(-rx, -ky)),
            ]
        else:
            pts = [
                (Vec2(0, -ry), Vec2(-kx, -ry), Vec2(kx, -ry)),
                (Vec2(-rx, 0), Vec2(-rx, -ky), Vec2(-rx, ky)),
                (Vec2(0, ry), Vec2(kx, ry), Vec2(-kx, ry)),
                (Vec2(rx, 0), Vec2(rx, ky), Vec2(rx, -ky)),
            ]
        nodes = []
        for pos, in_h, out_h in pts:
            nodes.append(PathNode(position=pos, in_handle=in_h, out_handle=out_h,
                                  mode=HandleMode.SMOOTH))
        return SubPath(nodes, closed=True)

    def to_dict(self) -> dict:
        return {"type": "ring", "rx": self.rx, "ry": self.ry,
                "thickness": self.thickness}

    @staticmethod
    def from_dict(d: dict) -> RingShape:
        return RingShape(d.get("rx", 50.0), d.get("ry", 50.0),
                         d.get("thickness", 0.3))


# ---------------------------------------------------------------------------
#  Trapezoid
# ---------------------------------------------------------------------------

@dataclass
class TrapezoidShape(ShapePrimitive):
    """Symmetric trapezoid.  *top_ratio* (0-1) is top-edge width / bottom-edge."""

    width: float = 100.0
    height: float = 80.0
    top_ratio: float = 0.6

    def to_path(self) -> VectorPath:
        hw, hh = self.width * 0.5, self.height * 0.5
        t = max(0.0, min(self.top_ratio, 1.0))
        tw = hw * t
        nodes = [
            PathNode(position=Vec2(-tw, -hh), mode=HandleMode.SHARP),
            PathNode(position=Vec2(tw, -hh), mode=HandleMode.SHARP),
            PathNode(position=Vec2(hw, hh), mode=HandleMode.SHARP),
            PathNode(position=Vec2(-hw, hh), mode=HandleMode.SHARP),
        ]
        return VectorPath([SubPath(nodes, closed=True)])

    def to_dict(self) -> dict:
        return {"type": "trapezoid", "width": self.width, "height": self.height,
                "top_ratio": self.top_ratio}

    @staticmethod
    def from_dict(d: dict) -> TrapezoidShape:
        return TrapezoidShape(d.get("width", 100.0), d.get("height", 80.0),
                              d.get("top_ratio", 0.6))


# ---------------------------------------------------------------------------
#  Parallelogram
# ---------------------------------------------------------------------------

@dataclass
class ParallelogramShape(ShapePrimitive):
    """Parallelogram.  *skew* (0-1) controls horizontal offset of top edge."""

    width: float = 120.0
    height: float = 80.0
    skew: float = 0.25

    def to_path(self) -> VectorPath:
        hw, hh = self.width * 0.5, self.height * 0.5
        s = max(0.0, min(self.skew, 0.9))
        offset = self.width * s
        nodes = [
            PathNode(position=Vec2(-hw + offset, -hh), mode=HandleMode.SHARP),
            PathNode(position=Vec2(hw + offset, -hh), mode=HandleMode.SHARP),
            PathNode(position=Vec2(hw - offset, hh), mode=HandleMode.SHARP),
            PathNode(position=Vec2(-hw - offset, hh), mode=HandleMode.SHARP),
        ]
        return VectorPath([SubPath(nodes, closed=True)])

    def to_dict(self) -> dict:
        return {"type": "parallelogram", "width": self.width,
                "height": self.height, "skew": self.skew}

    @staticmethod
    def from_dict(d: dict) -> ParallelogramShape:
        return ParallelogramShape(d.get("width", 120.0), d.get("height", 80.0),
                                  d.get("skew", 0.25))


# ---------------------------------------------------------------------------
#  Crescent / Moon
# ---------------------------------------------------------------------------

@dataclass
class CrescentShape(ShapePrimitive):
    """Crescent moon.  *offset* (0-1) controls how much the inner circle is shifted."""

    radius: float = 50.0
    offset: float = 0.35

    def to_path(self) -> VectorPath:
        r = self.radius
        off = max(0.05, min(self.offset, 0.9))
        k = 0.5522847498

        # Outer circle (clockwise)
        outer = self._circle_nodes(r, k, clockwise=True)
        # Inner circle shifted right, counter-clockwise
        ir = r * (1.0 - off * 0.2)  # slightly smaller
        shift = r * off
        inner_nodes = self._circle_nodes(ir, k, clockwise=False, cx=shift)
        return VectorPath([
            SubPath(outer, closed=True),
            SubPath(inner_nodes, closed=True),
        ])

    @staticmethod
    def _circle_nodes(r: float, k: float, clockwise: bool = True,
                      cx: float = 0.0) -> list[PathNode]:
        kr = r * k
        if clockwise:
            data = [
                (Vec2(cx, -r), Vec2(cx + kr, -r), Vec2(cx - kr, -r)),
                (Vec2(cx + r, 0), Vec2(cx + r, -kr), Vec2(cx + r, kr)),
                (Vec2(cx, r), Vec2(cx - kr, r), Vec2(cx + kr, r)),
                (Vec2(cx - r, 0), Vec2(cx - r, kr), Vec2(cx - r, -kr)),
            ]
        else:
            data = [
                (Vec2(cx, -r), Vec2(cx - kr, -r), Vec2(cx + kr, -r)),
                (Vec2(cx - r, 0), Vec2(cx - r, -kr), Vec2(cx - r, kr)),
                (Vec2(cx, r), Vec2(cx + kr, r), Vec2(cx - kr, r)),
                (Vec2(cx + r, 0), Vec2(cx + r, kr), Vec2(cx + r, -kr)),
            ]
        return [PathNode(position=p, in_handle=ih, out_handle=oh,
                         mode=HandleMode.SMOOTH) for p, ih, oh in data]

    def to_dict(self) -> dict:
        return {"type": "crescent", "radius": self.radius, "offset": self.offset}

    @staticmethod
    def from_dict(d: dict) -> CrescentShape:
        return CrescentShape(d.get("radius", 50.0), d.get("offset", 0.35))


# ---------------------------------------------------------------------------
#  Speech Bubble
# ---------------------------------------------------------------------------

@dataclass
class SpeechBubbleShape(ShapePrimitive):
    """Rounded rectangle with a triangular speech tail at the bottom."""

    width: float = 140.0
    height: float = 80.0
    corner_radius: float = 10.0
    tail_position: float = 0.3   # 0-1 fraction along bottom edge

    def to_path(self) -> VectorPath:
        hw, hh = self.width * 0.5, self.height * 0.5
        r = min(self.corner_radius, hw * 0.5, hh * 0.5)
        tp = max(0.1, min(self.tail_position, 0.9))
        tail_w = self.width * 0.12
        tail_h = self.height * 0.35
        tail_cx = -hw + self.width * tp

        # Build rounded rect body (sharp nodes at corner tangent points)
        nodes = []
        # Top edge (left to right)
        nodes.append(PathNode(position=Vec2(-hw + r, -hh), mode=HandleMode.SHARP))
        nodes.append(PathNode(position=Vec2(hw - r, -hh), mode=HandleMode.SHARP))
        # Top-right corner
        k = r * 0.5522847498
        nodes.append(PathNode(
            position=Vec2(hw, -hh + r),
            in_handle=Vec2(hw, -hh + r - k),
            out_handle=Vec2(hw, -hh + r + k if r + k < hh else -hh + r),
            mode=HandleMode.SMOOTH,
        ))
        # Right edge → bottom-right corner
        nodes.append(PathNode(
            position=Vec2(hw, hh - r),
            mode=HandleMode.SHARP,
        ))
        nodes.append(PathNode(position=Vec2(hw - r, hh), mode=HandleMode.SHARP))
        # Bottom edge with tail
        nodes.append(PathNode(position=Vec2(tail_cx + tail_w * 0.5, hh), mode=HandleMode.SHARP))
        nodes.append(PathNode(position=Vec2(tail_cx, hh + tail_h), mode=HandleMode.SHARP))
        nodes.append(PathNode(position=Vec2(tail_cx - tail_w * 0.5, hh), mode=HandleMode.SHARP))
        nodes.append(PathNode(position=Vec2(-hw + r, hh), mode=HandleMode.SHARP))
        # Bottom-left corner
        nodes.append(PathNode(
            position=Vec2(-hw, hh - r),
            in_handle=Vec2(-hw, hh - r + k if r + k < hh else hh - r),
            out_handle=Vec2(-hw, hh - r - k),
            mode=HandleMode.SMOOTH,
        ))
        # Left edge → top-left corner
        nodes.append(PathNode(position=Vec2(-hw, -hh + r), mode=HandleMode.SHARP))

        return VectorPath([SubPath(nodes, closed=True)])

    def to_dict(self) -> dict:
        return {"type": "speech_bubble", "width": self.width,
                "height": self.height, "corner_radius": self.corner_radius,
                "tail_position": self.tail_position}

    @staticmethod
    def from_dict(d: dict) -> SpeechBubbleShape:
        return SpeechBubbleShape(
            d.get("width", 140.0), d.get("height", 80.0),
            d.get("corner_radius", 10.0), d.get("tail_position", 0.3),
        )
