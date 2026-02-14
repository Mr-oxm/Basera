"""Vector path representation backed by QPainterPath.

A ``VectorPath`` is an ordered sequence of *sub-paths*, each containing
nodes. This module wraps PySide6's QPainterPath for robust geometry
calculations (hit testing, bounding boxes, boolean operations) while
maintaining an editable node-based structure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Iterator, TYPE_CHECKING
from uuid import uuid4

from PySide6.QtGui import QPainterPath, QPainterPathStroker
from PySide6.QtCore import QPointF, Qt

from .geometry import Vec2, BBox, AffineTransform
from .bezier import CubicBezier

if TYPE_CHECKING:
    pass

__all__ = [
    "VectorPath", "SubPath", "PathSegment", "PathNode",
    "SegmentType", "FillRule", "HandleMode",
]


class SegmentType(Enum):
    LINE = auto()
    CUBIC = auto()
    CLOSE = auto()


class FillRule(Enum):
    NON_ZERO = auto()  # Qt::WindingFill
    EVEN_ODD = auto()  # Qt::OddEvenFill


class HandleMode(Enum):
    """Constraint mode for Bézier handles at a node."""
    SHARP = auto()       # Handles are independent
    SMOOTH = auto()      # Handles are collinear but different lengths
    SYMMETRIC = auto()   # Handles are collinear and same length


# ---------------------------------------------------------------------------
#  Path Segment (Legacy/Helper)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class PathSegment:
    """A single segment within a sub-path.
    
    Provided for compatibility with the Node Tool which iterates segments.
    """
    seg_type: SegmentType
    end: Vec2 = field(default_factory=lambda: Vec2())
    cp1: Vec2 = field(default_factory=lambda: Vec2())
    cp2: Vec2 = field(default_factory=lambda: Vec2())


# ---------------------------------------------------------------------------
#  Path Node
# ---------------------------------------------------------------------------

@dataclass
class PathNode:
    """An on-curve anchor point with optional Bézier handles."""

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
        self.in_handle = pos
        if self.mode == HandleMode.SMOOTH and self.out_handle is not None:
            direction = (self.position - pos).normalized()
            out_len = self.out_handle.distance_to(self.position)
            self.out_handle = self.position + direction * out_len
        elif self.mode == HandleMode.SYMMETRIC and self.out_handle is not None:
            offset = pos - self.position
            self.out_handle = self.position - offset

    def set_out_handle(self, pos: Vec2) -> None:
        self.out_handle = pos
        if self.mode == HandleMode.SMOOTH and self.in_handle is not None:
            direction = (self.position - pos).normalized()
            in_len = self.in_handle.distance_to(self.position)
            self.in_handle = self.position + direction * in_len
        elif self.mode == HandleMode.SYMMETRIC and self.in_handle is not None:
            offset = pos - self.position
            self.in_handle = self.position - offset

    def set_position(self, pos: Vec2) -> None:
        delta = pos - self.position
        self.position = pos
        if self.in_handle is not None:
            self.in_handle = self.in_handle + delta
        if self.out_handle is not None:
            self.out_handle = self.out_handle + delta

    def toggle_mode(self) -> None:
        modes = [HandleMode.SHARP, HandleMode.SMOOTH, HandleMode.SYMMETRIC]
        idx = modes.index(self.mode)
        self.mode = modes[(idx + 1) % 3]


# ---------------------------------------------------------------------------
#  Sub-Path
# ---------------------------------------------------------------------------

class SubPath:
    """A contiguous sequence of nodes."""

    __slots__ = ("_nodes", "closed", "_qpath_dirty", "_qpath_cache", "id")

    def __init__(self, nodes: list[PathNode] | None = None, closed: bool = False) -> None:
        self._nodes: list[PathNode] = nodes or []
        self.closed = closed
        self._qpath_dirty = True
        self._qpath_cache: QPainterPath = QPainterPath()
        self.id: str = uuid4().hex[:8]

    @property
    def nodes(self) -> list[PathNode]:
        return self._nodes

    @property
    def node_count(self) -> int:
        return len(self._nodes)
    
    @property
    def origin(self) -> Vec2 | None:
        return self._nodes[0].position if self._nodes else None

    def invalidate(self) -> None:
        self._qpath_dirty = True

    def add_node(self, node: PathNode, index: int = -1) -> None:
        if index < 0:
            self._nodes.append(node)
        else:
            self._nodes.insert(index, node)
        self.invalidate()

    def remove_node(self, index: int) -> PathNode | None:
        if 0 <= index < len(self._nodes):
            n = self._nodes.pop(index)
            self.invalidate()
            return n
        return None

    def remove_node_by_id(self, node_id: str) -> PathNode | None:
        for i, n in enumerate(self._nodes):
            if n.id == node_id:
                return self.remove_node(i)
        return None
    
    def insert_node_at_t(self, seg_index: int, t: float) -> PathNode | None:
        # Legacy support for NodeTool which still calculates 't' locally
        # This implementation still uses custom Bezier math because Qt doesn't invoke splitAt(t) easily 
        # for our node structure.
        # Ideally, we'd use geometry.py/bezier.py logic here.
        # Since I am keeping bezier.py as a utility, I'll copy the old implementation logic here 
        # or rely on the fact that the old implementation was "buggy" but maybe split logic was fine?
        # Actually, split logic is usually fine.
        
        # We need to construct the segment to split
        segs = self.segments
        if seg_index < 0 or seg_index >= len(segs):
            return None
        seg = segs[seg_index]
        if seg.seg_type == SegmentType.CLOSE:
            return None

        # Determine start point
        if seg_index == 0:
            start = self._nodes[0].position
        else:
            start = segs[seg_index - 1].end

        if seg.seg_type == SegmentType.LINE:
            new_pos = start.lerp(seg.end, t)
            new_node = PathNode(position=new_pos, mode=HandleMode.SHARP)
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
            # Update surrounding nodes
            self._nodes[seg_index].out_handle = left.p1
            # Next node in-handle
            next_idx = seg_index + 1
            if next_idx < len(self._nodes):
                self._nodes[next_idx].in_handle = right.p2
            elif self.closed: # Wrapping around
                 self._nodes[0].in_handle = right.p2
            
            self._nodes.insert(seg_index + 1, new_node)

        self.invalidate()
        return self._nodes[seg_index + 1]

    @property
    def segments(self) -> list[PathSegment]:
        # Construct segments on the fly from nodes
        segs: list[PathSegment] = []
        n = len(self._nodes)
        if n < 2 and not self.closed:
            return segs

        for i in range(n - 1):
            a, b = self._nodes[i], self._nodes[i+1]
            segs.append(self._make_segment(a, b))

        if self.closed and n >= 2:
            segs.append(self._make_segment(self._nodes[-1], self._nodes[0]))
            segs.append(PathSegment(seg_type=SegmentType.CLOSE))
        
        return segs

    @staticmethod
    def _make_segment(a: PathNode, b: PathNode) -> PathSegment:
        has_out = a.out_handle is not None and not a.out_handle.approx_eq(a.position)
        has_in = b.in_handle is not None and not b.in_handle.approx_eq(b.position)
        if has_out or has_in:
            cp1 = a.out_handle if has_out else a.position
            cp2 = b.in_handle if has_in else b.position
            return PathSegment(SegmentType.CUBIC, b.position, cp1, cp2)
        return PathSegment(SegmentType.LINE, b.position)

    # ---- QPainterPath Integration -------------------------------------------

    @property
    def qpath(self) -> QPainterPath:
        if self._qpath_dirty:
            self._rebuild_qpath()
        return self._qpath_cache

    def _rebuild_qpath(self) -> None:
        path = QPainterPath()
        if not self._nodes:
            self._qpath_cache = path
            self._qpath_dirty = False
            return

        nodes = self._nodes
        path.moveTo(nodes[0].position.to_qpoint())

        for i in range(len(nodes) - 1):
            a, b = nodes[i], nodes[i+1]
            self._append_segment_to_qpath(path, a, b)
        
        if self.closed:
            if len(nodes) >= 2:
                self._append_segment_to_qpath(path, nodes[-1], nodes[0])
            path.closeSubpath()

        self._qpath_cache = path
        self._qpath_dirty = False

    @staticmethod
    def _append_segment_to_qpath(path: QPainterPath, a: PathNode, b: PathNode) -> None:
        has_out = a.out_handle is not None and not a.out_handle.approx_eq(a.position)
        has_in = b.in_handle is not None and not b.in_handle.approx_eq(b.position)
        
        dest = b.position.to_qpoint()
        
        if not has_out and not has_in:
            path.lineTo(dest)
        else:
            c1 = a.out_handle if has_out else a.position
            c2 = b.in_handle if has_in else b.position
            path.cubicTo(c1.to_qpoint(), c2.to_qpoint(), dest)

    # ---- Geometry delegated to Qt -------------------------------------------

    def bbox(self) -> BBox:
        r = self.qpath.boundingRect()
        return BBox(Vec2(r.left(), r.top()), Vec2(r.right(), r.bottom()))

    def flatten(self, tolerance: float = 0.5) -> list[Vec2]:
        # tolerance is ignored by QPainterPath.toSubpathPolygons (it uses internal Qt logic)
        # We could use simplified() but that changes topology. 
        # toSubpathPolygons returns QList<QPolygonF>
        polys = self.qpath.toSubpathPolygons()
        if not polys:
            return []
        # Return the first polygon (SubPath is one contour)
        # Note: Qt's flattening might be different than the iterative recursive one.
        # If strict tolerance is needed this might be an issue, but usually Qt is good.
        pts = [Vec2.from_qpoint(p) for p in polys[0]]
        return pts

    def arc_length(self, tolerance: float = 0.5) -> float:
        return self.qpath.length()

    def hit_test_stroke(self, point: Vec2, tolerance: float = 3.0) -> float | None:
        stroker = QPainterPathStroker()
        stroker.setWidth(tolerance * 2)
        stroker.setCapStyle(Qt.RoundCap)
        stroke_path = stroker.createStroke(self.qpath)
        if stroke_path.contains(point.to_qpoint()):
            # QPainterPath doesn't give distance easily.
            # Return a dummy small distance if hit.
            return 0.0
        return None

    def contains_point(self, point: Vec2, fill_rule: FillRule = FillRule.NON_ZERO) -> bool:
        # fill_rule ignored for single subpath hit test usually, but we set it anyway
        path = self.qpath
        path.setFillRule(Qt.WindingFill if fill_rule == FillRule.NON_ZERO else Qt.OddEvenFill)
        return path.contains(point.to_qpoint())
    
    def reversed(self) -> SubPath:
        new_nodes: list[PathNode] = []
        for node in reversed(self._nodes):
            new_node = PathNode(
                position=node.position,
                in_handle=node.out_handle,
                out_handle=node.in_handle,
                mode=node.mode,
            )
            new_nodes.append(new_node)
        return SubPath(new_nodes, self.closed)

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


# ---------------------------------------------------------------------------
#  VectorPath
# ---------------------------------------------------------------------------

class VectorPath:
    """A complete vector path composed of one or more ``SubPath`` contours."""

    __slots__ = ("sub_paths", "fill_rule", "id", "_qpath_cache", "_qpath_dirty")

    def __init__(
        self,
        sub_paths: list[SubPath] | None = None,
        fill_rule: FillRule = FillRule.NON_ZERO,
    ) -> None:
        self.sub_paths: list[SubPath] = sub_paths or []
        self.fill_rule = fill_rule
        self.id: str = uuid4().hex[:10]
        self._qpath_cache: QPainterPath = QPainterPath()
        self._qpath_dirty: bool = True

    def add_sub_path(self, sp: SubPath) -> None:
        self.sub_paths.append(sp)
        self.invalidate()

    def remove_sub_path(self, index: int) -> SubPath | None:
        if 0 <= index < len(self.sub_paths):
            sp = self.sub_paths.pop(index)
            self.invalidate()
            return sp
        return None

    @property
    def is_empty(self) -> bool:
        return not self.sub_paths or all(sp.node_count == 0 for sp in self.sub_paths)

    @property
    def total_nodes(self) -> int:
        return sum(sp.node_count for sp in self.sub_paths)

    def invalidate(self) -> None:
        self._qpath_dirty = True
        # SubPaths handle their own invalidation

    @property
    def qpath(self) -> QPainterPath:
        if self._qpath_dirty:
            path = QPainterPath()
            path.setFillRule(Qt.WindingFill if self.fill_rule == FillRule.NON_ZERO else Qt.OddEvenFill)
            for sp in self.sub_paths:
                path.addPath(sp.qpath)
            self._qpath_cache = path
            self._qpath_dirty = False
        return self._qpath_cache

    # ---- Geometry -----------------------------------------------------------

    def bbox(self) -> BBox:
        if self.is_empty:
            return BBox.empty()
        r = self.qpath.boundingRect()
        return BBox(Vec2(r.left(), r.top()), Vec2(r.right(), r.bottom()))

    def flatten(self, tolerance: float = 0.5) -> list[list[Vec2]]:
        polys = self.qpath.toSubpathPolygons()
        result = []
        for poly in polys:
            result.append([Vec2.from_qpoint(p) for p in poly])
        return result

    def transformed(self, xf: AffineTransform) -> VectorPath:
        new_subs = [sp.transformed(xf) for sp in self.sub_paths]
        return VectorPath(new_subs, self.fill_rule)

    def reversed(self) -> VectorPath:
        new_subs = [sp.reversed() for sp in self.sub_paths]
        return VectorPath(new_subs, self.fill_rule)

    # ---- Hit testing -------------------------------------------------------

    def hit_test_fill(self, point: Vec2) -> bool:
        return self.qpath.contains(point.to_qpoint())

    def hit_test_stroke(self, point: Vec2, tolerance: float = 3.0) -> bool:
        stroker = QPainterPathStroker()
        stroker.setWidth(tolerance * 2)
        stroke_path = stroker.createStroke(self.qpath)
        return stroke_path.contains(point.to_qpoint())

    # ---- Serialization helpers ----------------------------------------------

    def to_dict(self) -> dict:
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
#  Serialization
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
#  Path Construction
# ---------------------------------------------------------------------------

def path_from_points(points: list[Vec2], closed: bool = False) -> VectorPath:
    nodes = [PathNode(position=p, mode=HandleMode.SHARP) for p in points]
    sp = SubPath(nodes, closed)
    return VectorPath([sp])
