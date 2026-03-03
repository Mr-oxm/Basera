"""Pick-Segments mode — interactive boolean fragment selection.

When activated the user sees every sub-segment that results from splitting
the selected paths at their mutual intersection points.  Segments can be
toggled *included* / *excluded* and the included segments are assembled
into closed shapes on *Apply*.

Implementation strategy
-----------------------
1. Flatten each selected layer's geometry into a single ``QPainterPath``.
2. For every pair of paths, find intersection points using the Qt
   ``intersected`` primitive and ``QPainterPath.elementAt`` enumeration.
3. Approximate: split every sub-path at those intersection *t* values to
   produce a list of ``Segment`` objects (polyline or Bézier chunks).
4. Each segment is independently hoverable / clickable / toggleable.
5. On Apply, walk the *included* segments, attempt to stitch them into
   closed contours, and create new vector layers.

This module is **pure logic** — it does *not* import any UI classes.
The overlay rendering lives in ``canvas_overlays`` and the toolbar
controls are in ``vector_bar``.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import uuid4

from PySide6.QtGui import QPainterPath
from PySide6.QtCore import QPointF

from .geometry import Vec2, BBox
from .path import VectorPath, SubPath, PathNode, HandleMode
from .boolean import qpath_to_vector_path
from .scene import VectorObject, VectorLayer
from .style import VectorStyle

if TYPE_CHECKING:
    from ..core.document import Document
    from ..core.layer import Layer


__all__ = ["PickSegmentsState", "Segment"]


# ---------------------------------------------------------------------------
#  Data structures
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    """One segment = a polyline approximation of a curve chunk."""

    id: str = field(default_factory=lambda: uuid4().hex[:10])
    points: list[Vec2] = field(default_factory=list)
    included: bool = True
    layer_id: str = ""
    # Original stroke color for rendering
    color: tuple[int, int, int, int] = (100, 180, 255, 255)

    @property
    def start(self) -> Vec2:
        return self.points[0] if self.points else Vec2(0, 0)

    @property
    def end(self) -> Vec2:
        return self.points[-1] if self.points else Vec2(0, 0)

    def hit_test(self, point: Vec2, tolerance: float = 10.0) -> bool:
        """Return True if *point* is inside the segment area or near an edge."""
        # First check if point is inside the filled polygon area
        if len(self.points) >= 3 and _point_in_polygon(point, self.points):
            return True
        # Fallback: check proximity to the polyline edges
        tol_sq = tolerance * tolerance
        for i in range(len(self.points) - 1):
            a = self.points[i]
            b = self.points[i + 1]
            d = _point_seg_dist_sq(point, a, b)
            if d < tol_sq:
                return True
        return False

    def bbox(self) -> BBox:
        if not self.points:
            return BBox.empty()
        xs = [p.x for p in self.points]
        ys = [p.y for p in self.points]
        return BBox(Vec2(min(xs), min(ys)), Vec2(max(xs), max(ys)))


def _point_seg_dist_sq(p: Vec2, a: Vec2, b: Vec2) -> float:
    """Squared distance from point *p* to line segment *a-b*."""
    ab = b - a
    d2 = ab.length_sq()
    if d2 < 1e-12:
        return p.distance_sq_to(a)
    t = max(0.0, min(1.0, (p - a).dot(ab) / d2))
    proj = a + ab * t
    return p.distance_sq_to(proj)


def _point_in_polygon(point: Vec2, polygon: list[Vec2]) -> bool:
    """Ray-casting algorithm for point-in-polygon test."""
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    px, py = point.x, point.y
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i].x, polygon[i].y
        xj, yj = polygon[j].x, polygon[j].y
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


# ---------------------------------------------------------------------------
#  State machine
# ---------------------------------------------------------------------------

class PickSegmentsState:
    """Holds all state for an active pick-segments session."""

    def __init__(self) -> None:
        self.active: bool = False
        self.segments: list[Segment] = []
        self.hovered_id: str | None = None
        self.layer_ids: list[str] = []  # source layers
        self._styles: dict[str, VectorStyle] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def enter(self, doc: "Document", layer_ids: list[str]) -> bool:
        """Compute segments from the selected layers.  Returns False on failure."""
        from .boolean_ops import get_sorted_vector_layers
        layers = get_sorted_vector_layers(doc, layer_ids)
        if len(layers) < 2:
            return False

        self.layer_ids = [l.id for l in layers]
        self.segments.clear()
        self.hovered_id = None

        # Build a flattened QPainterPath per layer and collect polylines
        qpaths: list[tuple[str, QPainterPath]] = []
        for layer in layers:
            vl = getattr(layer, "_vector_data", None)
            if vl is None:
                continue
            combined = QPainterPath()
            style = VectorStyle()
            for obj in vl.objects:
                combined = combined.united(obj.flatten_to_path().qpath)
                if obj.style:
                    style = copy.deepcopy(obj.style)
            qpaths.append((layer.id, combined))
            self._styles[layer.id] = style

        if len(qpaths) < 2:
            return False

        # For each path, compute the parts that lie *inside* and *outside*
        # each other path.  This gives us the visually distinct sub-segments
        # that the user can toggle.
        self._split_into_segments(qpaths)

        self.active = True
        return True

    def cancel(self) -> None:
        """Discard everything and leave pick-segments mode."""
        self.active = False
        self.segments.clear()
        self.hovered_id = None
        self.layer_ids.clear()
        self._styles.clear()

    def apply(self, doc: "Document") -> list[str]:
        """Build closed shapes from included segments, create layers.
        Returns new layer IDs.  Removes source layers."""
        if not self.active:
            return []

        included = [s for s in self.segments if s.included]
        if not included:
            self.cancel()
            return []

        contours = self._stitch_contours(included)
        if not contours:
            self.cancel()
            return []

        doc.save_snapshot("Pick Segments: Apply")

        # Determine insertion index (bottom-most source layer)
        all_layers = doc.layers.layers
        indices = []
        for lid in self.layer_ids:
            for i, l in enumerate(all_layers):
                if l.id == lid:
                    indices.append(i)
                    break
        insert_idx = min(indices) if indices else len(all_layers)

        # Remove source layers
        for lid in list(self.layer_ids):
            doc.layers.remove(lid)

        # Build a single layer with all contours as sub-paths of one
        # VectorObject.  If there are multiple contours we union their
        # QPainterPaths so the result is a single clean shape.
        from ..core.enums import LayerType
        from ..core.layer import Layer as _Layer
        from .rasterizer import rasterize_vector_layer_tight
        from .boolean import qpath_to_vector_path as _qp2vp

        style = next(iter(self._styles.values()), VectorStyle())

        # Convert each contour to a QPainterPath and union them
        combined_qp = QPainterPath()
        for contour_pts in contours:
            sub_qp = QPainterPath()
            if contour_pts:
                sub_qp.moveTo(QPointF(contour_pts[0].x, contour_pts[0].y))
                for pt in contour_pts[1:]:
                    sub_qp.lineTo(QPointF(pt.x, pt.y))
                sub_qp.closeSubpath()
            combined_qp = combined_qp.united(sub_qp)

        result_path = _qp2vp(combined_qp)
        vl = VectorLayer()
        obj = VectorObject(
            name="Custom Shape",
            path=result_path,
            style=copy.deepcopy(style),
        )
        vl.add(obj)

        new_layer = _Layer(
            name="Custom Shape",
            width=max(doc.width, 1),
            height=max(doc.height, 1),
            layer_type=LayerType.SHAPE,
        )
        new_layer._vector_data = vl
        doc.layers.add(new_layer, index=insert_idx)
        rasterize_vector_layer_tight(doc, layer=new_layer)

        # Clean up stale selected_indices and point at the new layer
        doc.layers._selected_indices = set()
        new_idx = doc.layers.layers.index(new_layer)
        doc.layers._active_index = new_idx
        doc.layers._selected_indices.add(new_idx)

        self.cancel()
        return [new_layer.id]

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def hit_test(self, point: Vec2, tolerance: float = 10.0) -> str | None:
        """Return the ID of the segment under *point*, or None."""
        for seg in self.segments:
            if seg.hit_test(point, tolerance):
                return seg.id
        return None

    def toggle(self, seg_id: str) -> None:
        """Toggle inclusion for the segment with the given ID."""
        for seg in self.segments:
            if seg.id == seg_id:
                seg.included = not seg.included
                return

    def set_hover(self, seg_id: str | None) -> None:
        self.hovered_id = seg_id

    def closed_count(self) -> int:
        """How many closed contours can be formed from included segments."""
        included = [s for s in self.segments if s.included]
        return len(self._stitch_contours(included))

    def has_open(self) -> bool:
        """True if included segments don't all form closed paths."""
        included = [s for s in self.segments if s.included]
        if not included:
            return True
        contours = self._stitch_contours(included)
        # If stitching consumed all segments, no open leftover
        used = sum(len(c) for c in contours)
        total_pts = sum(len(s.points) for s in included)
        return used < total_pts * 0.5  # rough heuristic

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _split_into_segments(
        self, qpaths: list[tuple[str, QPainterPath]]
    ) -> None:
        """Populate ``self.segments`` by splitting each path at intersections."""
        # Strategy: for each path, compute the portions that are
        # (a) outside all other paths and (b) each pairwise intersection
        # region's boundary.  We approximate by flattening each sub-region
        # into polylines.

        n = len(qpaths)

        # 1) For each path, compute the portion OUTSIDE all others
        for idx, (lid, qp) in enumerate(qpaths):
            others = QPainterPath()
            for j, (_, oqp) in enumerate(qpaths):
                if j != idx:
                    others = others.united(oqp)
            outside = qp.subtracted(others)
            self._qpath_to_segments(outside, lid, is_outside=True)

        # 2) Compute *exclusive* pairwise intersection regions.
        #    For each pair (i,j), the exclusive region is the part of
        #    their intersection that does NOT also belong to any other path.
        #    This prevents the triple-overlap area from being lumped into
        #    each pairwise segment.
        for i in range(n):
            for j in range(i + 1, n):
                lid_i, qp_i = qpaths[i]
                _lid_j, qp_j = qpaths[j]
                inter = qp_i.intersected(qp_j)
                if inter.isEmpty():
                    continue
                # Subtract every other path to get the exclusive pair region
                for k in range(n):
                    if k != i and k != j:
                        inter = inter.subtracted(qpaths[k][1])
                if not inter.isEmpty():
                    self._qpath_to_segments(inter, lid_i, is_outside=False)

        # 3) Higher-order intersections (3-way, 4-way, …).
        #    Use itertools.combinations to enumerate every subset of size
        #    ≥3 that shares a common region, subtracting any paths NOT in
        #    the subset so we get only the exclusive N-way overlap.
        if n >= 3:
            from itertools import combinations
            for size in range(3, n + 1):
                for combo in combinations(range(n), size):
                    # Intersect all paths in this subset
                    region = qpaths[combo[0]][1]
                    for ci in combo[1:]:
                        region = region.intersected(qpaths[ci][1])
                    if region.isEmpty():
                        continue
                    # Subtract paths NOT in this subset to make it exclusive
                    others_in_combo = set(combo)
                    for k in range(n):
                        if k not in others_in_combo:
                            region = region.subtracted(qpaths[k][1])
                    if not region.isEmpty():
                        # Attribute to the first layer in the combo
                        self._qpath_to_segments(
                            region, qpaths[combo[0]][0], is_outside=False)

    def _qpath_to_segments(
        self, qp: QPainterPath, layer_id: str, is_outside: bool
    ) -> None:
        """Convert a QPainterPath into Segment objects using elementAt."""
        count = qp.elementCount()
        if count == 0:
            return

        COLORS_OUTSIDE = (100, 180, 255, 255)
        COLORS_INSIDE = (200, 140, 60, 255)
        color = COLORS_OUTSIDE if is_outside else COLORS_INSIDE

        current_pts: list[Vec2] = []

        def _flush():
            nonlocal current_pts
            if len(current_pts) >= 2:
                seg = Segment(
                    points=list(current_pts),
                    included=True,
                    layer_id=layer_id,
                    color=color,
                )
                self.segments.append(seg)
            current_pts = []

        i = 0
        while i < count:
            el = qp.elementAt(i)
            etype = el.type

            if etype == QPainterPath.ElementType.MoveToElement:
                _flush()
                current_pts = [Vec2(el.x, el.y)]
                i += 1

            elif etype == QPainterPath.ElementType.LineToElement:
                current_pts.append(Vec2(el.x, el.y))
                i += 1

            elif etype == QPainterPath.ElementType.CurveToElement:
                # Cubic: 3 elements (cp1, cp2, end)
                cp1 = Vec2(el.x, el.y)
                i += 1
                if i >= count:
                    break
                el2 = qp.elementAt(i)
                cp2 = Vec2(el2.x, el2.y)
                i += 1
                if i >= count:
                    break
                el3 = qp.elementAt(i)
                end = Vec2(el3.x, el3.y)
                i += 1

                # Flatten cubic to polyline
                if current_pts:
                    start = current_pts[-1]
                else:
                    start = cp1
                pts = _flatten_cubic(start, cp1, cp2, end, tolerance=1.0)
                current_pts.extend(pts[1:])  # skip duplicate start
            else:
                i += 1

        _flush()

    @staticmethod
    def _stitch_contours(
        segments: list[Segment], tolerance: float = 3.0,
    ) -> list[list[Vec2]]:
        """Try to stitch segments into closed contours.

        Returns a list of point lists, each representing a closed contour.
        """
        if not segments:
            return []

        # Build endpoint adjacency
        remaining = list(segments)
        contours: list[list[Vec2]] = []

        while remaining:
            current = remaining.pop(0)
            chain = list(current.points)

            changed = True
            while changed:
                changed = False
                for i, seg in enumerate(remaining):
                    # Try connecting end→start
                    if chain[-1].distance_to(seg.start) < tolerance:
                        chain.extend(seg.points[1:])
                        remaining.pop(i)
                        changed = True
                        break
                    # Try connecting end→end (reversed)
                    if chain[-1].distance_to(seg.end) < tolerance:
                        chain.extend(reversed(seg.points[:-1]))
                        remaining.pop(i)
                        changed = True
                        break
                    # Try connecting start→start (reversed)
                    if chain[0].distance_to(seg.start) < tolerance:
                        chain = list(reversed(seg.points[1:])) + chain
                        remaining.pop(i)
                        changed = True
                        break
                    # Try connecting start→end
                    if chain[0].distance_to(seg.end) < tolerance:
                        chain = list(seg.points[:-1]) + chain
                        remaining.pop(i)
                        changed = True
                        break

            # Check closure
            if len(chain) >= 3 and chain[0].distance_to(chain[-1]) < tolerance:
                contours.append(chain)

        return contours


# ---------------------------------------------------------------------------
#  Utility
# ---------------------------------------------------------------------------

def _flatten_cubic(
    p0: Vec2, p1: Vec2, p2: Vec2, p3: Vec2, tolerance: float = 1.0
) -> list[Vec2]:
    """Flatten a cubic Bézier to a polyline via recursive subdivision."""
    result: list[Vec2] = [p0]
    _subdivide(p0, p1, p2, p3, tolerance * tolerance, result)
    result.append(p3)
    return result


def _subdivide(
    p0: Vec2, p1: Vec2, p2: Vec2, p3: Vec2, tol_sq: float, out: list[Vec2]
) -> None:
    mid = Vec2(
        (p0.x + 3 * p1.x + 3 * p2.x + p3.x) / 8,
        (p0.y + 3 * p1.y + 3 * p2.y + p3.y) / 8,
    )
    chord_mid = Vec2((p0.x + p3.x) / 2, (p0.y + p3.y) / 2)
    if mid.distance_sq_to(chord_mid) < tol_sq:
        return
    # De Casteljau split at t=0.5
    q0 = Vec2((p0.x + p1.x) / 2, (p0.y + p1.y) / 2)
    q1 = Vec2((p1.x + p2.x) / 2, (p1.y + p2.y) / 2)
    q2 = Vec2((p2.x + p3.x) / 2, (p2.y + p3.y) / 2)
    r0 = Vec2((q0.x + q1.x) / 2, (q0.y + q1.y) / 2)
    r1 = Vec2((q1.x + q2.x) / 2, (q1.y + q2.y) / 2)
    s = Vec2((r0.x + r1.x) / 2, (r0.y + r1.y) / 2)
    _subdivide(p0, q0, r0, s, tol_sq, out)
    out.append(s)
    _subdivide(s, r1, q2, p3, tol_sq, out)
