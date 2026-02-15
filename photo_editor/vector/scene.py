"""Vector scene graph — ``VectorObject`` and ``VectorLayer``.

A ``VectorObject`` is a single vector entity combining:
* A ``VectorPath`` or ``ShapePrimitive`` (geometry)
* A ``VectorStyle`` (appearance)
* An ``AffineTransform`` (placement in the layer)
* An optional name and metadata

A ``VectorLayer`` is a container that holds an ordered list of
``VectorObject`` instances plus a spatial index for fast queries.
It can be attached to the existing ``Layer`` data model via
``Layer._vector_data``.

Scene graph design choices
--------------------------
* Flat list within each layer (no deep nesting) — matches Affinity's model
  where groups are separate layers. Cross-object operations like boolean
  ops are explicit commands, not implicit tree operations.
* Each ``VectorObject`` is fully self-contained and serialisable.
* The spatial index is lazily rebuilt on query after mutations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4
from typing import Sequence

import numpy as np

from .geometry import Vec2, BBox, AffineTransform
from .path import VectorPath, FillRule
from .style import VectorStyle
from .shapes import ShapePrimitive
from .spatial import RTree, RTreeEntry

__all__ = ["VectorObject", "VectorLayer"]


# ---------------------------------------------------------------------------
#  VectorObject
# ---------------------------------------------------------------------------

@dataclass
class VectorObject:
    """A single vector entity in the scene.

    May be driven by either a raw ``VectorPath`` (for pen-tool / boolean
    results) or a ``ShapePrimitive`` (for live-parameter shapes).  When
    a ``ShapePrimitive`` is present, ``path`` is generated from it on
    demand and cached.
    """

    name: str = "Path"
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    # Geometry — at least one must be set
    path: VectorPath | None = None
    shape: ShapePrimitive | None = None
    # Appearance
    style: VectorStyle = field(default_factory=VectorStyle)
    # Transform (local → layer coords)
    transform: AffineTransform = field(default_factory=AffineTransform.identity)
    # State
    visible: bool = True
    locked: bool = False
    selected: bool = False
    # Whole-object opacity (0..1), used when importing from SVG
    opacity: float = 1.0
    # SVG filter to apply (e.g. {"type": "gaussian_blur", "std_deviation": 4.13})
    svg_filter: dict | None = None

    # Cache
    _cached_path: VectorPath | None = field(default=None, repr=False, init=False)
    _path_dirty: bool = field(default=True, repr=False, init=False)

    def effective_path(self) -> VectorPath:
        """Resolved path — from shape primitive or direct path."""
        if self._path_dirty or self._cached_path is None:
            if self.shape is not None:
                self._cached_path = self.shape.to_path()
            elif self.path is not None:
                self._cached_path = self.path
            else:
                self._cached_path = VectorPath()
            self._path_dirty = False
        return self._cached_path

    def transformed_path(self) -> VectorPath:
        """Path in layer coordinate space (after applying local transform)."""
        p = self.effective_path()
        if self.transform.is_identity:
            return p
        return p.transformed(self.transform)

    def invalidate(self) -> None:
        """Mark cached path as dirty (call after shape parameter changes)."""
        self._path_dirty = True
        self._cached_path = None

    def detach_shape(self) -> None:
        """Convert a shape-backed object to a raw-path object.

        After detaching, node-level edits (position, handles) will survive
        calls to ``invalidate()`` because ``effective_path()`` will return
        the stored ``self.path`` instead of regenerating from the shape.
        """
        if self.shape is not None:
            self.path = self.effective_path()
            self.shape = None

    # ---- Bounding box -------------------------------------------------------

    def bbox(self) -> BBox:
        """AABB in layer coordinates, including stroke expansion."""
        p = self.transformed_path()
        bb = p.bbox()
        # Expand by half the maximum stroke width, scaled by the transform
        sw = self.style.max_stroke_width() * 0.5
        if sw > 0:
            scale = self.transform.max_scale_factor()
            bb = bb.expanded(sw * scale)
        return bb

    def local_bbox(self) -> BBox:
        """AABB in local (pre-transform) coordinates."""
        return self.effective_path().bbox()

    # ---- Hit testing -------------------------------------------------------

    def hit_test(self, point: Vec2, stroke_tolerance: float = 3.0) -> bool:
        """Test if *point* (in layer coords) hits this object's fill or stroke."""
        if not self.visible:
            return False
        bb = self.bbox()
        if not bb.contains_point(point):
            return False
        # Transform point into local coords
        try:
            inv = self.transform.inverse()
        except ValueError:
            return False
        local_pt = inv.apply(point)
        p = self.effective_path()
        # Check fill
        if self.style.has_visible_fill:
            if p.hit_test_fill(local_pt):
                return True
        # Check stroke
        if self.style.has_visible_stroke:
            sw = self.style.max_stroke_width() * 0.5 + stroke_tolerance
            if p.hit_test_stroke(local_pt, sw):
                return True
        return False

    def hit_test_node(
        self, point: Vec2, tolerance: float = 6.0
    ) -> tuple[int, int, str] | None:
        """Find nearest node to *point* (layer coords).

        Returns ``(sub_path_index, node_index, component)`` where
        component is ``"position"``, ``"in_handle"``, or ``"out_handle"``.
        Returns ``None`` for a miss.
        """
        try:
            inv = self.transform.inverse()
        except ValueError:
            return None
        local_pt = inv.apply(point)
        tol_sq = tolerance * tolerance
        p = self.effective_path()
        for si, sp in enumerate(p.sub_paths):
            for ni, node in enumerate(sp.nodes):
                # Check handles first (they're smaller targets and should take priority)
                if node.out_handle is not None:
                    if local_pt.distance_sq_to(node.out_handle) < tol_sq:
                        return (si, ni, "out_handle")
                if node.in_handle is not None:
                    if local_pt.distance_sq_to(node.in_handle) < tol_sq:
                        return (si, ni, "in_handle")
                if local_pt.distance_sq_to(node.position) < tol_sq:
                    return (si, ni, "position")
        return None

    # ---- Transform helpers --------------------------------------------------

    def translate(self, dx: float, dy: float) -> None:
        self.transform = AffineTransform.translation(dx, dy).concat(self.transform)

    def scale(self, sx: float, sy: float, center: Vec2 | None = None) -> None:
        if center:
            self.transform = (
                AffineTransform.translation(center.x, center.y)
                .concat(AffineTransform.scaling(sx, sy))
                .concat(AffineTransform.translation(-center.x, -center.y))
                .concat(self.transform)
            )
        else:
            self.transform = AffineTransform.scaling(sx, sy).concat(self.transform)

    def rotate(self, angle_rad: float, center: Vec2 | None = None) -> None:
        if center:
            self.transform = AffineTransform.rotation_around(angle_rad, center).concat(self.transform)
        else:
            self.transform = AffineTransform.rotation(angle_rad).concat(self.transform)

    # ---- Conversion to path (bakes shape + transform) -----------------------

    def flatten_to_path(self) -> VectorPath:
        """Return the final path with transform baked in.

        Useful for boolean operations and SVG export. After this, the
        original shape parameters are lost.
        """
        return self.transformed_path()

    # ---- Serialization ------------------------------------------------------

    def to_dict(self) -> dict:
        d: dict = {
            "name": self.name,
            "id": self.id,
            "visible": self.visible,
            "locked": self.locked,
            "opacity": self.opacity,
            "transform": self.transform.to_tuple(),
            "style": self.style.to_dict(),
        }
        if self.svg_filter is not None:
            d["svg_filter"] = self.svg_filter
        if self.path is not None:
            d["path"] = self.path.to_dict()
        if self.shape is not None:
            d["shape"] = self.shape.to_dict()
        return d

    @staticmethod
    def from_dict(d: dict) -> VectorObject:
        obj = VectorObject(
            name=d.get("name", "Path"),
            visible=d.get("visible", True),
            locked=d.get("locked", False),
            opacity=d.get("opacity", 1.0),
            transform=AffineTransform.from_tuple(d.get("transform", (1, 0, 0, 1, 0, 0))),
            style=VectorStyle.from_dict(d.get("style", {})),
        )
        obj.id = d.get("id", obj.id)
        obj.svg_filter = d.get("svg_filter")
        if "path" in d:
            obj.path = VectorPath.from_dict(d["path"])
        if "shape" in d:
            obj.shape = ShapePrimitive.from_dict(d["shape"])
        return obj


# ---------------------------------------------------------------------------
#  VectorLayer
# ---------------------------------------------------------------------------

class VectorLayer:
    """Container for ``VectorObject`` instances with spatial indexing.

    Attached to a ``Layer`` as ``layer._vector_data``.  Provides
    spatial queries (point, window) and object management.
    """

    def __init__(self) -> None:
        self._objects: list[VectorObject] = []
        self._index = RTree()
        self._index_dirty = True

    # ---- Object management --------------------------------------------------

    @property
    def objects(self) -> list[VectorObject]:
        return self._objects

    @property
    def count(self) -> int:
        return len(self._objects)

    def add(self, obj: VectorObject, index: int = -1) -> None:
        if index < 0:
            self._objects.append(obj)
        else:
            self._objects.insert(index, obj)
        self._index_dirty = True

    def remove(self, obj_id: str) -> VectorObject | None:
        for i, obj in enumerate(self._objects):
            if obj.id == obj_id:
                self._objects.pop(i)
                self._index_dirty = True
                return obj
        return None

    def get(self, obj_id: str) -> VectorObject | None:
        for obj in self._objects:
            if obj.id == obj_id:
                return obj
        return None

    def reorder(self, obj_id: str, new_index: int) -> None:
        for i, obj in enumerate(self._objects):
            if obj.id == obj_id:
                self._objects.pop(i)
                self._objects.insert(min(new_index, len(self._objects)), obj)
                self._index_dirty = True
                return

    def clear(self) -> None:
        self._objects.clear()
        self._index.clear()
        self._index_dirty = False

    # ---- Selection ----------------------------------------------------------

    def selected_objects(self) -> list[VectorObject]:
        return [o for o in self._objects if o.selected]

    def select_all(self) -> None:
        for o in self._objects:
            o.selected = True

    def deselect_all(self) -> None:
        for o in self._objects:
            o.selected = False

    def select_by_id(self, obj_id: str) -> None:
        for o in self._objects:
            if o.id == obj_id:
                o.selected = True

    # ---- Spatial index -------------------------------------------------------

    def _rebuild_index(self) -> None:
        entries = []
        for obj in self._objects:
            if obj.visible:
                entries.append(RTreeEntry(bbox=obj.bbox(), payload=obj.id))
        self._index.rebuild(entries)
        self._index_dirty = False

    def _ensure_index(self) -> None:
        if self._index_dirty:
            self._rebuild_index()

    def invalidate_index(self) -> None:
        self._index_dirty = True

    # ---- Queries ------------------------------------------------------------

    def hit_test(self, point: Vec2, stroke_tolerance: float = 3.0) -> VectorObject | None:
        """Find the topmost visible object hit by *point*.

        Uses R-tree for broad-phase, then precise path hit-testing.
        Iterates in reverse (top to bottom) for correct z-ordering.
        """
        self._ensure_index()
        candidates = self._index.query_point(point)
        cand_ids = {e.payload for e in candidates}
        # Test in reverse order (topmost first)
        for obj in reversed(self._objects):
            if obj.id in cand_ids and obj.visible and not obj.locked:
                if obj.hit_test(point, stroke_tolerance):
                    return obj
        return None

    def query_rect(self, rect: BBox) -> list[VectorObject]:
        """All visible objects whose AABB intersects *rect*."""
        self._ensure_index()
        entries = self._index.query_rect(rect)
        ids = {e.payload for e in entries}
        return [o for o in self._objects if o.id in ids and o.visible]

    def objects_in_view(self, viewport: BBox) -> list[VectorObject]:
        """Objects visible in the viewport — used for render culling."""
        return self.query_rect(viewport)

    # ---- Bounding box -------------------------------------------------------

    def bbox(self) -> BBox:
        bb = BBox.empty()
        for obj in self._objects:
            if obj.visible:
                bb = bb.union(obj.bbox())
        return bb

    # ---- Serialization ------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "objects": [o.to_dict() for o in self._objects],
        }

    @staticmethod
    def from_dict(d: dict) -> VectorLayer:
        vl = VectorLayer()
        for od in d.get("objects", []):
            vl.add(VectorObject.from_dict(od))
        return vl

    def to_dict_list(self) -> list[dict]:
        """Flat list for undo/redo snapshot."""
        return [o.to_dict() for o in self._objects]

    @staticmethod
    def from_dict_list(lst: list[dict]) -> VectorLayer:
        vl = VectorLayer()
        for d in lst:
            vl.add(VectorObject.from_dict(d))
        return vl
