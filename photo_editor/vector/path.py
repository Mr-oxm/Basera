"""Vector path representation — the central data structure.

A ``VectorPath`` is an ordered sequence of *sub-paths*, each containing
one or more ``PathSegment`` objects.  A sub-path may be open (stroke only)
or closed (filled).

Segment types
-------------
* ``LINE``  — straight segment from the previous point to ``end``.
* ``CUBIC`` — cubic Bézier from previous point via ``cp1``, ``cp2`` to ``end``.
* ``CLOSE`` — closes the sub-path back to its first point.

The design mirrors SVG/PDF path semantics so export is straightforward.
Internally every segment stores its endpoint and (for cubics) the two
control points.  The *start* of each segment is implicitly the *end* of
the previous one (or the sub-path origin for the first segment).

Node model
----------
Each on-curve point is wrapped in a ``PathNode`` that tracks:
* Position (``Vec2``)
* In-handle and out-handle offsets (``Vec2``, relative to node)
* Handle constraint mode: ``SMOOTH``, ``SHARP``, ``SYMMETRIC``

This makes the Node Tool's job straightforward — it manipulates
``PathNode`` objects and the path rebuilds its segment list on commit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Iterator
from uuid import uuid4

from .geometry import Vec2, BBox, AffineTransform
from .bezier import CubicBezier

__all__ = [
    "VectorPath", "SubPath", "PathSegment", "PathNode",
    "SegmentType", "FillRule", "HandleMode",
]


class SegmentType(Enum):
    LINE = auto()
    CUBIC = auto()
    CLOSE = auto()


class FillRule(Enum):
    NON_ZERO = auto()
    EVEN_ODD = auto()


class HandleMode(Enum):
    """Constraint mode for Bézier handles at a node."""
    SHARP = auto()       # Handles are independent
    SMOOTH = auto()      # Handles are collinear but different lengths
    SYMMETRIC = auto()   # Handles are collinear and same length


# ---------------------------------------------------------------------------
#  Path Segment
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class PathSegment:
    """A single segment within a sub-path.

    * For ``LINE``: only ``end`` is meaningful.
    * For ``CUBIC``: ``cp1`` and ``cp2`` are the two control points.
    * For ``CLOSE``: all fields may be ignored (the segment closes
      back to the sub-path origin).
    """

    seg_type: SegmentType
    end: Vec2 = field(default_factory=lambda: Vec2())
    cp1: Vec2 = field(default_factory=lambda: Vec2())
    cp2: Vec2 = field(default_factory=lambda: Vec2())


# ---------------------------------------------------------------------------
#  Path Node (for interactive editing)
# ---------------------------------------------------------------------------

@dataclass
class PathNode:
    """An on-curve anchor point with optional Bézier handles.

    Handles are stored as *absolute* positions to simplify hit-testing
    and rendering.  Constraint enforcement (smooth/symmetric) is done
    when a handle is moved via ``set_in_handle`` / ``set_out_handle``.
    """

    position: Vec2
    in_handle: Vec2 | None = None   # Control point *arriving* at this node
    out_handle: Vec2 | None = None  # Control point *leaving* this node
    mode: HandleMode = HandleMode.SHARP
    selected: bool = False
    id: str = field(default_factory=lambda: uuid4().hex[:8])

    @property
    def has_in_handle(self) -> bool:
        return self.in_handle is not None and not self.in_handle.approx_eq(self.position)

    @property
    def has_out_handle(self) -> bool:
        return self.out_handle is not None and not self.out_handle.approx_eq(self.position)

    def set_in_handle(self, pos: Vec2) -> None:
        """Set the in-handle and enforce constraint mode on out-handle."""
        self.in_handle = pos
        if self.mode == HandleMode.SMOOTH and self.out_handle is not None:
            direction = (self.position - pos).normalized()
            out_len = self.out_handle.distance_to(self.position)
            self.out_handle = self.position + direction * out_len
        elif self.mode == HandleMode.SYMMETRIC and self.out_handle is not None:
            offset = pos - self.position
            self.out_handle = self.position - offset

    def set_out_handle(self, pos: Vec2) -> None:
        """Set the out-handle and enforce constraint mode on in-handle."""
        self.out_handle = pos
        if self.mode == HandleMode.SMOOTH and self.in_handle is not None:
            direction = (self.position - pos).normalized()
            in_len = self.in_handle.distance_to(self.position)
            self.in_handle = self.position + direction * in_len
        elif self.mode == HandleMode.SYMMETRIC and self.in_handle is not None:
            offset = pos - self.position
            self.in_handle = self.position - offset

    def set_position(self, pos: Vec2) -> None:
        """Move node, keeping handles in their relative positions."""
        delta = pos - self.position
        self.position = pos
        if self.in_handle is not None:
            self.in_handle = self.in_handle + delta
        if self.out_handle is not None:
            self.out_handle = self.out_handle + delta

    def toggle_mode(self) -> None:
        """Cycle SHARP → SMOOTH → SYMMETRIC → SHARP."""
        modes = [HandleMode.SHARP, HandleMode.SMOOTH, HandleMode.SYMMETRIC]
        idx = modes.index(self.mode)
        self.mode = modes[(idx + 1) % 3]


# ---------------------------------------------------------------------------
#  Sub-Path
# ---------------------------------------------------------------------------

class SubPath:
    """A contiguous sequence of nodes forming an open or closed contour.

    This is the primary editable representation.  Segments are lazily
    rebuilt from the node list when ``segments`` is accessed after a
    mutation.
    """

    __slots__ = ("_nodes", "closed", "_segments_dirty", "_cached_segments", "id")

    def __init__(self, nodes: list[PathNode] | None = None, closed: bool = False) -> None:
        self._nodes: list[PathNode] = nodes or []
        self.closed = closed
        self._segments_dirty = True
        self._cached_segments: list[PathSegment] = []
        self.id: str = uuid4().hex[:8]

    @property
    def nodes(self) -> list[PathNode]:
        return self._nodes

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    def invalidate(self) -> None:
        self._segments_dirty = True

    # ---- Mutation helpers ---------------------------------------------------

    def add_node(self, node: PathNode, index: int = -1) -> None:
        if index < 0:
            self._nodes.append(node)
        else:
            self._nodes.insert(index, node)
        self._segments_dirty = True

    def remove_node(self, index: int) -> PathNode | None:
        if 0 <= index < len(self._nodes):
            n = self._nodes.pop(index)
            self._segments_dirty = True
            return n
        return None

    def remove_node_by_id(self, node_id: str) -> PathNode | None:
        for i, n in enumerate(self._nodes):
            if n.id == node_id:
                return self.remove_node(i)
        return None

    def insert_node_at_t(self, seg_index: int, t: float) -> PathNode | None:
        """Insert a new node by splitting segment *seg_index* at parameter *t*.

        Returns the new node, or ``None`` if the index is invalid.
        """
        segs = self.segments
        if seg_index < 0 or seg_index >= len(segs):
            return None
        seg = segs[seg_index]
        if seg.seg_type == SegmentType.CLOSE:
            return None

        # Determine the start point
        if seg_index == 0:
            start = self._nodes[0].position
        else:
            start = segs[seg_index - 1].end

        if seg.seg_type == SegmentType.LINE:
            new_pos = start.lerp(seg.end, t)
            new_node = PathNode(position=new_pos, mode=HandleMode.SHARP)
            # Insert after the node at seg_index
            self._nodes.insert(seg_index + 1, new_node)
        elif seg.seg_type == SegmentType.CUBIC:
            bez = CubicBezier(start, seg.cp1, seg.cp2, seg.end)
            left, right = bez.split_at(t)
            new_node = PathNode(
                position=left.p3,
                in_handle=left.p2,
                out_handle=right.p1,
                mode=HandleMode.SMOOTH,
            )
            # Update surrounding nodes' handles
            self._nodes[seg_index].out_handle = left.p1
            if seg_index + 1 < len(self._nodes):
                self._nodes[seg_index + 1].in_handle = right.p2
            elif self.closed and seg_index + 1 == len(self._nodes):
                self._nodes[0].in_handle = right.p2
            self._nodes.insert(seg_index + 1, new_node)

        self._segments_dirty = True
        return new_node

    # ---- Segment generation -------------------------------------------------

    @property
    def segments(self) -> list[PathSegment]:
        if self._segments_dirty:
            self._rebuild_segments()
        return self._cached_segments

    def _rebuild_segments(self) -> None:
        """Generate segment list from the node list."""
        segs: list[PathSegment] = []
        nodes = self._nodes
        n = len(nodes)
        if n < 2 and not self.closed:
            self._cached_segments = segs
            self._segments_dirty = False
            return

        for i in range(n - 1):
            a, b = nodes[i], nodes[i + 1]
            seg = self._make_segment(a, b)
            segs.append(seg)

        if self.closed and n >= 2:
            # Closing segment back to first node
            seg = self._make_segment(nodes[-1], nodes[0])
            segs.append(seg)
            segs.append(PathSegment(seg_type=SegmentType.CLOSE))

        self._cached_segments = segs
        self._segments_dirty = False

    @staticmethod
    def _make_segment(a: PathNode, b: PathNode) -> PathSegment:
        """Create a segment between two adjacent nodes."""
        has_out = a.out_handle is not None and not a.out_handle.approx_eq(a.position)
        has_in = b.in_handle is not None and not b.in_handle.approx_eq(b.position)
        if has_out or has_in:
            cp1 = a.out_handle if has_out else a.position
            cp2 = b.in_handle if has_in else b.position
            return PathSegment(
                seg_type=SegmentType.CUBIC,
                end=b.position,
                cp1=cp1,
                cp2=cp2,
            )
        return PathSegment(seg_type=SegmentType.LINE, end=b.position)

    # ---- Geometry queries ---------------------------------------------------

    @property
    def origin(self) -> Vec2 | None:
        return self._nodes[0].position if self._nodes else None

    def bbox(self) -> BBox:
        bb = BBox.empty()
        start = self.origin
        if start is None:
            return bb
        for seg in self.segments:
            if seg.seg_type == SegmentType.LINE:
                bb = bb.union(BBox.from_points([start, seg.end]))
                start = seg.end
            elif seg.seg_type == SegmentType.CUBIC:
                bez = CubicBezier(start, seg.cp1, seg.cp2, seg.end)
                bb = bb.union(bez.bbox())
                start = seg.end
            elif seg.seg_type == SegmentType.CLOSE:
                origin = self.origin
                if origin is not None:
                    bb = bb.union(BBox.from_points([start, origin]))
                    start = origin
        return bb

    def flatten(self, tolerance: float = 0.5) -> list[Vec2]:
        """Convert to polyline for rasterisation / hit-testing."""
        pts: list[Vec2] = []
        start = self.origin
        if start is None:
            return pts
        pts.append(start)
        for seg in self.segments:
            if seg.seg_type == SegmentType.LINE:
                pts.append(seg.end)
                start = seg.end
            elif seg.seg_type == SegmentType.CUBIC:
                bez = CubicBezier(start, seg.cp1, seg.cp2, seg.end)
                flat = bez.flatten(tolerance)
                pts.extend(flat[1:])  # skip duplicate start
                start = seg.end
            elif seg.seg_type == SegmentType.CLOSE:
                origin = self.origin
                if origin is not None and not start.approx_eq(origin):
                    pts.append(origin)
                start = origin
        return pts

    def arc_length(self, tolerance: float = 0.5) -> float:
        total = 0.0
        start = self.origin
        if start is None:
            return 0.0
        for seg in self.segments:
            if seg.seg_type == SegmentType.LINE:
                total += start.distance_to(seg.end)
                start = seg.end
            elif seg.seg_type == SegmentType.CUBIC:
                bez = CubicBezier(start, seg.cp1, seg.cp2, seg.end)
                total += bez.arc_length(tolerance)
                start = seg.end
            elif seg.seg_type == SegmentType.CLOSE:
                origin = self.origin
                if origin is not None:
                    total += start.distance_to(origin)
        return total

    def reversed(self) -> SubPath:
        """Return a new sub-path with reversed winding."""
        new_nodes: list[PathNode] = []
        for node in reversed(self._nodes):
            new_node = PathNode(
                position=node.position,
                in_handle=node.out_handle,
                out_handle=node.in_handle,
                mode=node.mode,
            )
            new_nodes.append(new_node)
        sp = SubPath(new_nodes, self.closed)
        return sp

    def transformed(self, xf: AffineTransform) -> SubPath:
        new_nodes: list[PathNode] = []
        for node in self._nodes:
            new_node = PathNode(
                position=xf.apply(node.position),
                in_handle=xf.apply(node.in_handle) if node.in_handle else None,
                out_handle=xf.apply(node.out_handle) if node.out_handle else None,
                mode=node.mode,
            )
            new_nodes.append(new_node)
        return SubPath(new_nodes, self.closed)

    # ---- Hit testing -------------------------------------------------------

    def hit_test_stroke(self, point: Vec2, tolerance: float = 3.0) -> float | None:
        """Return parameter along path if *point* is within *tolerance* of the stroke.

        Returns the approximate distance, or ``None`` for miss.
        """
        start = self.origin
        if start is None:
            return None
        best_dist = float("inf")
        for seg in self.segments:
            if seg.seg_type == SegmentType.LINE:
                d = _point_line_distance(point, start, seg.end)
                best_dist = min(best_dist, d)
                start = seg.end
            elif seg.seg_type == SegmentType.CUBIC:
                bez = CubicBezier(start, seg.cp1, seg.cp2, seg.end)
                _, nearest = bez.nearest_point(point)
                d = point.distance_to(nearest)
                best_dist = min(best_dist, d)
                start = seg.end
            elif seg.seg_type == SegmentType.CLOSE:
                origin = self.origin
                if origin is not None:
                    d = _point_line_distance(point, start, origin)
                    best_dist = min(best_dist, d)
                    start = origin
        return best_dist if best_dist <= tolerance else None

    def contains_point(self, point: Vec2, fill_rule: FillRule = FillRule.NON_ZERO) -> bool:
        """Winding-number / even-odd test for point-in-closed-path.

        Uses the flattened polyline for the test.
        """
        if not self.closed:
            return False
        poly = self.flatten(0.5)
        if len(poly) < 3:
            return False
        if fill_rule == FillRule.EVEN_ODD:
            return _point_in_polygon_even_odd(point, poly)
        return _point_in_polygon_winding(point, poly) != 0


# ---------------------------------------------------------------------------
#  VectorPath — a complete path with multiple sub-paths
# ---------------------------------------------------------------------------

class VectorPath:
    """A complete vector path composed of one or more ``SubPath`` contours.

    This is the primary data model for a single vector shape / compound
    path.  It owns fill-rule, and delegates styling to ``VectorStyle``.
    """

    __slots__ = ("sub_paths", "fill_rule", "id", "_bbox_cache", "_bbox_dirty")

    def __init__(
        self,
        sub_paths: list[SubPath] | None = None,
        fill_rule: FillRule = FillRule.NON_ZERO,
    ) -> None:
        self.sub_paths: list[SubPath] = sub_paths or []
        self.fill_rule = fill_rule
        self.id: str = uuid4().hex[:10]
        self._bbox_cache: BBox = BBox.empty()
        self._bbox_dirty: bool = True

    # ---- Sub-path management ------------------------------------------------

    def add_sub_path(self, sp: SubPath) -> None:
        self.sub_paths.append(sp)
        self._bbox_dirty = True

    def remove_sub_path(self, index: int) -> SubPath | None:
        if 0 <= index < len(self.sub_paths):
            sp = self.sub_paths.pop(index)
            self._bbox_dirty = True
            return sp
        return None

    @property
    def is_empty(self) -> bool:
        return not self.sub_paths or all(sp.node_count == 0 for sp in self.sub_paths)

    @property
    def total_nodes(self) -> int:
        return sum(sp.node_count for sp in self.sub_paths)

    def invalidate(self) -> None:
        self._bbox_dirty = True
        for sp in self.sub_paths:
            sp.invalidate()

    # ---- Geometry -----------------------------------------------------------

    def bbox(self) -> BBox:
        if self._bbox_dirty:
            bb = BBox.empty()
            for sp in self.sub_paths:
                bb = bb.union(sp.bbox())
            self._bbox_cache = bb
            self._bbox_dirty = False
        return self._bbox_cache

    def flatten(self, tolerance: float = 0.5) -> list[list[Vec2]]:
        """Flatten all sub-paths into polylines."""
        return [sp.flatten(tolerance) for sp in self.sub_paths]

    def transformed(self, xf: AffineTransform) -> VectorPath:
        new_subs = [sp.transformed(xf) for sp in self.sub_paths]
        return VectorPath(new_subs, self.fill_rule)

    def reversed(self) -> VectorPath:
        new_subs = [sp.reversed() for sp in self.sub_paths]
        return VectorPath(new_subs, self.fill_rule)

    # ---- Hit testing -------------------------------------------------------

    def hit_test_fill(self, point: Vec2) -> bool:
        """Test if *point* is inside the filled region."""
        if self.fill_rule == FillRule.EVEN_ODD:
            total = 0
            for sp in self.sub_paths:
                if sp.closed:
                    poly = sp.flatten(0.5)
                    if len(poly) >= 3:
                        if _point_in_polygon_even_odd(point, poly):
                            total += 1
            return total % 2 == 1
        else:
            winding = 0
            for sp in self.sub_paths:
                if sp.closed:
                    poly = sp.flatten(0.5)
                    if len(poly) >= 3:
                        winding += _point_in_polygon_winding(point, poly)
            return winding != 0

    def hit_test_stroke(self, point: Vec2, tolerance: float = 3.0) -> bool:
        for sp in self.sub_paths:
            d = sp.hit_test_stroke(point, tolerance)
            if d is not None:
                return True
        return False

    # ---- Serialization helpers ----------------------------------------------

    def to_dict(self) -> dict:
        """Serialize for undo/redo and file storage."""
        return {
            "id": self.id,
            "fill_rule": self.fill_rule.name,
            "sub_paths": [_sub_path_to_dict(sp) for sp in self.sub_paths],
        }

    @staticmethod
    def from_dict(d: dict) -> VectorPath:
        vp = VectorPath(
            fill_rule=FillRule[d.get("fill_rule", "NON_ZERO")],
        )
        vp.id = d.get("id", vp.id)
        for sp_d in d.get("sub_paths", []):
            vp.sub_paths.append(_sub_path_from_dict(sp_d))
        return vp

    def __repr__(self) -> str:
        return f"VectorPath(sub_paths={len(self.sub_paths)}, nodes={self.total_nodes})"


# ---------------------------------------------------------------------------
#  Path construction helpers
# ---------------------------------------------------------------------------

def path_from_points(points: list[Vec2], closed: bool = False) -> VectorPath:
    """Create a simple polyline (straight segments) from a point list."""
    nodes = [PathNode(position=p, mode=HandleMode.SHARP) for p in points]
    sp = SubPath(nodes, closed)
    return VectorPath([sp])


def path_from_cubic_chain(
    control_points: list[Vec2], closed: bool = False
) -> VectorPath:
    """Build path from a flat list of cubic control points.

    Layout: [p0, cp1_out, cp2_in, p1, cp1_out, cp2_in, p2, ...]
    Every 3 values after the initial point define the out-handle of the
    previous node, the in-handle of the next node, and the next node
    position.
    """
    if len(control_points) < 4:
        return VectorPath()
    nodes: list[PathNode] = []
    # First node
    nodes.append(PathNode(position=control_points[0], mode=HandleMode.SMOOTH))
    i = 1
    while i + 2 < len(control_points):
        out_h = control_points[i]
        in_h = control_points[i + 1]
        pos = control_points[i + 2]
        # Set out-handle on previous node
        nodes[-1].out_handle = out_h
        # Create next node with in-handle
        node = PathNode(position=pos, in_handle=in_h, mode=HandleMode.SMOOTH)
        nodes.append(node)
        i += 3
    sp = SubPath(nodes, closed)
    return VectorPath([sp])


# ---------------------------------------------------------------------------
#  Internal serialization
# ---------------------------------------------------------------------------

def _sub_path_to_dict(sp: SubPath) -> dict:
    return {
        "id": sp.id,
        "closed": sp.closed,
        "nodes": [
            {
                "id": n.id,
                "pos": n.position.to_tuple(),
                "in": n.in_handle.to_tuple() if n.in_handle else None,
                "out": n.out_handle.to_tuple() if n.out_handle else None,
                "mode": n.mode.name,
            }
            for n in sp.nodes
        ],
    }


def _sub_path_from_dict(d: dict) -> SubPath:
    nodes: list[PathNode] = []
    for nd in d.get("nodes", []):
        node = PathNode(
            position=Vec2.from_tuple(nd["pos"]),
            in_handle=Vec2.from_tuple(nd["in"]) if nd.get("in") else None,
            out_handle=Vec2.from_tuple(nd["out"]) if nd.get("out") else None,
            mode=HandleMode[nd.get("mode", "SHARP")],
        )
        node.id = nd.get("id", node.id)
        nodes.append(node)
    sp = SubPath(nodes, d.get("closed", False))
    sp.id = d.get("id", sp.id)
    return sp


# ---------------------------------------------------------------------------
#  Point-in-polygon helpers
# ---------------------------------------------------------------------------

def _point_in_polygon_even_odd(p: Vec2, poly: list[Vec2]) -> bool:
    """Ray-casting even-odd test."""
    n = len(poly)
    inside = False
    j = n - 1
    px, py = p.x, p.y
    for i in range(n):
        yi, yj = poly[i].y, poly[j].y
        xi, xj = poly[i].x, poly[j].x
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-30) + xi):
            inside = not inside
        j = i
    return inside


def _point_in_polygon_winding(p: Vec2, poly: list[Vec2]) -> int:
    """Winding-number test — robust for self-intersecting contours."""
    n = len(poly)
    winding = 0
    px, py = p.x, p.y
    for i in range(n):
        j = (i + 1) % n
        yi, yj = poly[i].y, poly[j].y
        xi, xj = poly[i].x, poly[j].x
        if yi <= py:
            if yj > py:
                # Upward crossing
                cross = (xj - xi) * (py - yi) - (px - xi) * (yj - yi)
                if cross > 0.0:
                    winding += 1
        else:
            if yj <= py:
                # Downward crossing
                cross = (xj - xi) * (py - yi) - (px - xi) * (yj - yi)
                if cross < 0.0:
                    winding -= 1
    return winding


def _point_line_distance(p: Vec2, a: Vec2, b: Vec2) -> float:
    """Distance from *p* to the line segment *a*→*b*."""
    ab = b - a
    ab_sq = ab.length_sq()
    if ab_sq < 1e-12:
        return p.distance_to(a)
    t = max(0.0, min(1.0, (p - a).dot(ab) / ab_sq))
    proj = Vec2(a.x + t * ab.x, a.y + t * ab.y)
    return p.distance_to(proj)
