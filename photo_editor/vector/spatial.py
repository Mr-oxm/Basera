"""R-tree spatial index for fast geometric queries.

Provides O(log n) point queries, window queries, and nearest-neighbour
searches over axis-aligned bounding boxes.  Used for:

* Hit-testing vector objects under the cursor
* Viewport culling (only render objects whose AABB intersects the view)
* Snap-to-geometry (find nearby anchor points)
* Boolean-operation candidate filtering

Implementation
--------------
This is a classic R-tree with Guttman's quadratic split.  Bulk-loading
uses Sort-Tile-Recursive (STR) when the index is built from scratch.
Node fanout (``MAX_ENTRIES``) is tuned for typical vector document sizes
(hundreds to low thousands of objects).

The tree stores ``RTreeEntry`` objects that pair an AABB with an opaque
``payload`` (usually a ``VectorObject`` id).  AABBs are lightweight
``BBox`` instances from the geometry module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .geometry import Vec2, BBox

__all__ = ["RTree", "RTreeEntry"]

# Fanout parameters — tune for workload
_MIN_ENTRIES = 4
_MAX_ENTRIES = 9


# ---------------------------------------------------------------------------
#  R-tree entry
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class RTreeEntry:
    """Leaf entry: bounding box + opaque payload."""
    bbox: BBox
    payload: Any


# ---------------------------------------------------------------------------
#  R-tree node (internal)
# ---------------------------------------------------------------------------

class _RNode:
    __slots__ = ("bbox", "children", "entries", "is_leaf")

    def __init__(self, is_leaf: bool = True) -> None:
        self.bbox: BBox = BBox.empty()
        self.children: list[_RNode] = []       # internal node children
        self.entries: list[RTreeEntry] = []     # leaf entries
        self.is_leaf = is_leaf

    def recompute_bbox(self) -> None:
        bb = BBox.empty()
        if self.is_leaf:
            for e in self.entries:
                bb = bb.union(e.bbox)
        else:
            for c in self.children:
                bb = bb.union(c.bbox)
        self.bbox = bb

    @property
    def count(self) -> int:
        return len(self.entries) if self.is_leaf else len(self.children)


# ---------------------------------------------------------------------------
#  R-tree
# ---------------------------------------------------------------------------

class RTree:
    """Spatial index using quadratic-split R-tree."""

    def __init__(self) -> None:
        self._root = _RNode(is_leaf=True)
        self._size = 0

    @property
    def size(self) -> int:
        return self._size

    @property
    def is_empty(self) -> bool:
        return self._size == 0

    # ---- Insertion ----------------------------------------------------------

    def insert(self, bbox: BBox, payload: Any) -> None:
        """Insert an entry into the tree."""
        entry = RTreeEntry(bbox=bbox, payload=payload)
        new_node = self._insert_entry(self._root, entry)
        if new_node is not None:
            # Root was split — create a new root
            old_root = self._root
            self._root = _RNode(is_leaf=False)
            self._root.children = [old_root, new_node]
            self._root.recompute_bbox()
        self._size += 1

    def _insert_entry(self, node: _RNode, entry: RTreeEntry) -> _RNode | None:
        if node.is_leaf:
            node.entries.append(entry)
            node.bbox = node.bbox.union(entry.bbox)
            if len(node.entries) > _MAX_ENTRIES:
                return self._split_leaf(node)
            return None
        # Choose child with minimum area enlargement
        best_child = self._choose_subtree(node, entry.bbox)
        new_node = self._insert_entry(best_child, entry)
        node.recompute_bbox()
        if new_node is not None:
            node.children.append(new_node)
            node.recompute_bbox()
            if len(node.children) > _MAX_ENTRIES:
                return self._split_internal(node)
        return None

    def _choose_subtree(self, node: _RNode, bbox: BBox) -> _RNode:
        best: _RNode | None = None
        best_enlarge = float("inf")
        best_area = float("inf")
        for child in node.children:
            enlarged = child.bbox.union(bbox)
            enlarge = enlarged.area - child.bbox.area
            if enlarge < best_enlarge or (enlarge == best_enlarge and child.bbox.area < best_area):
                best_enlarge = enlarge
                best_area = child.bbox.area
                best = child
        return best  # type: ignore[return-value]

    # ---- Splitting ----------------------------------------------------------

    def _split_leaf(self, node: _RNode) -> _RNode:
        """Quadratic split of a leaf node."""
        entries = node.entries
        i, j = self._pick_seeds_leaf(entries)
        group_a: list[RTreeEntry] = [entries[i]]
        group_b: list[RTreeEntry] = [entries[j]]
        bb_a = entries[i].bbox
        bb_b = entries[j].bbox
        remaining = [e for k, e in enumerate(entries) if k != i and k != j]
        for e in remaining:
            if len(group_a) + len(remaining) <= _MIN_ENTRIES:
                group_a.append(e)
                bb_a = bb_a.union(e.bbox)
                continue
            if len(group_b) + len(remaining) <= _MIN_ENTRIES:
                group_b.append(e)
                bb_b = bb_b.union(e.bbox)
                continue
            ea = bb_a.union(e.bbox).area - bb_a.area
            eb = bb_b.union(e.bbox).area - bb_b.area
            if ea < eb:
                group_a.append(e)
                bb_a = bb_a.union(e.bbox)
            else:
                group_b.append(e)
                bb_b = bb_b.union(e.bbox)
        node.entries = group_a
        node.recompute_bbox()
        new_node = _RNode(is_leaf=True)
        new_node.entries = group_b
        new_node.recompute_bbox()
        return new_node

    def _split_internal(self, node: _RNode) -> _RNode:
        children = node.children
        i, j = self._pick_seeds_internal(children)
        group_a = [children[i]]
        group_b = [children[j]]
        bb_a = children[i].bbox
        bb_b = children[j].bbox
        remaining = [c for k, c in enumerate(children) if k != i and k != j]
        for c in remaining:
            ea = bb_a.union(c.bbox).area - bb_a.area
            eb = bb_b.union(c.bbox).area - bb_b.area
            if ea < eb:
                group_a.append(c)
                bb_a = bb_a.union(c.bbox)
            else:
                group_b.append(c)
                bb_b = bb_b.union(c.bbox)
        node.children = group_a
        node.is_leaf = False
        node.recompute_bbox()
        new_node = _RNode(is_leaf=False)
        new_node.children = group_b
        new_node.recompute_bbox()
        return new_node

    @staticmethod
    def _pick_seeds_leaf(entries: list[RTreeEntry]) -> tuple[int, int]:
        worst = -1.0
        si, sj = 0, 1
        n = len(entries)
        for i in range(n):
            for j in range(i + 1, n):
                combined = entries[i].bbox.union(entries[j].bbox).area
                waste = combined - entries[i].bbox.area - entries[j].bbox.area
                if waste > worst:
                    worst = waste
                    si, sj = i, j
        return si, sj

    @staticmethod
    def _pick_seeds_internal(children: list[_RNode]) -> tuple[int, int]:
        worst = -1.0
        si, sj = 0, 1
        n = len(children)
        for i in range(n):
            for j in range(i + 1, n):
                combined = children[i].bbox.union(children[j].bbox).area
                waste = combined - children[i].bbox.area - children[j].bbox.area
                if waste > worst:
                    worst = waste
                    si, sj = i, j
        return si, sj

    # ---- Removal ------------------------------------------------------------

    def remove(self, bbox: BBox, payload: Any) -> bool:
        """Remove an entry matching *bbox* and *payload*.  Returns True if found."""
        orphans: list[RTreeEntry] = []
        found = self._remove_recursive(self._root, bbox, payload, orphans)
        if found:
            self._size -= 1
            for e in orphans:
                self.insert(e.bbox, e.payload)
            # Shrink tree height if root has single child
            if not self._root.is_leaf and len(self._root.children) == 1:
                self._root = self._root.children[0]
        return found

    def _remove_recursive(
        self, node: _RNode, bbox: BBox, payload: Any, orphans: list[RTreeEntry]
    ) -> bool:
        if node.is_leaf:
            for i, e in enumerate(node.entries):
                if e.payload is payload and e.bbox == bbox:
                    node.entries.pop(i)
                    node.recompute_bbox()
                    return True
            return False
        for i, child in enumerate(node.children):
            if not child.bbox.intersects(bbox):
                continue
            if self._remove_recursive(child, bbox, payload, orphans):
                if child.count < _MIN_ENTRIES:
                    # Reinsert under-full node's entries
                    if child.is_leaf:
                        orphans.extend(child.entries)
                    else:
                        self._collect_entries(child, orphans)
                    node.children.pop(i)
                node.recompute_bbox()
                return True
        return False

    @staticmethod
    def _collect_entries(node: _RNode, out: list[RTreeEntry]) -> None:
        if node.is_leaf:
            out.extend(node.entries)
        else:
            for c in node.children:
                RTree._collect_entries(c, out)

    # ---- Queries ------------------------------------------------------------

    def query_point(self, point: Vec2) -> list[RTreeEntry]:
        """Return all entries whose AABB contains *point*."""
        results: list[RTreeEntry] = []
        self._query_point_recursive(self._root, point, results)
        return results

    def _query_point_recursive(
        self, node: _RNode, point: Vec2, results: list[RTreeEntry]
    ) -> None:
        if not node.bbox.contains_point(point):
            return
        if node.is_leaf:
            for e in node.entries:
                if e.bbox.contains_point(point):
                    results.append(e)
        else:
            for c in node.children:
                self._query_point_recursive(c, point, results)

    def query_rect(self, rect: BBox) -> list[RTreeEntry]:
        """Return all entries whose AABB intersects *rect*."""
        results: list[RTreeEntry] = []
        self._query_rect_recursive(self._root, rect, results)
        return results

    def _query_rect_recursive(
        self, node: _RNode, rect: BBox, results: list[RTreeEntry]
    ) -> None:
        if not node.bbox.intersects(rect):
            return
        if node.is_leaf:
            for e in node.entries:
                if e.bbox.intersects(rect):
                    results.append(e)
        else:
            for c in node.children:
                self._query_rect_recursive(c, rect, results)

    def query_nearest(
        self, point: Vec2, max_results: int = 1
    ) -> list[tuple[float, RTreeEntry]]:
        """Find the *max_results* nearest entries to *point* (by AABB distance).

        Returns list of ``(distance, entry)`` sorted by distance.
        """
        results: list[tuple[float, RTreeEntry]] = []
        self._knn_recursive(self._root, point, max_results, results)
        results.sort(key=lambda x: x[0])
        return results[:max_results]

    def _knn_recursive(
        self,
        node: _RNode,
        point: Vec2,
        k: int,
        results: list[tuple[float, RTreeEntry]],
    ) -> None:
        if node.is_leaf:
            for e in node.entries:
                d = _bbox_distance(e.bbox, point)
                if len(results) < k or d < results[-1][0]:
                    results.append((d, e))
                    results.sort(key=lambda x: x[0])
                    if len(results) > k:
                        results.pop()
        else:
            # Sort children by distance for priority traversal
            dists = [(i, _bbox_distance(c.bbox, point)) for i, c in enumerate(node.children)]
            dists.sort(key=lambda x: x[1])
            for idx, d in dists:
                if len(results) >= k and d > results[-1][0]:
                    break
                self._knn_recursive(node.children[idx], point, k, results)

    # ---- Bulk operations ----------------------------------------------------

    def clear(self) -> None:
        self._root = _RNode(is_leaf=True)
        self._size = 0

    def rebuild(self, entries: list[RTreeEntry]) -> None:
        """Rebuild the tree using Sort-Tile-Recursive (STR) bulk-loading.

        Much faster than repeated insert for large datasets.
        """
        self.clear()
        if not entries:
            return
        self._size = len(entries)
        self._root = self._str_build(entries)

    def _str_build(self, entries: list[RTreeEntry]) -> _RNode:
        if len(entries) <= _MAX_ENTRIES:
            node = _RNode(is_leaf=True)
            node.entries = list(entries)
            node.recompute_bbox()
            return node
        # Sort by center X
        entries_sorted = sorted(entries, key=lambda e: e.bbox.center.x)
        # Compute number of slices
        import math
        page = _MAX_ENTRIES
        num_slices = max(1, math.ceil(len(entries_sorted) / page))
        slice_size = math.ceil(len(entries_sorted) / num_slices)
        children: list[_RNode] = []
        for i in range(0, len(entries_sorted), slice_size):
            chunk = entries_sorted[i : i + slice_size]
            # Sort chunk by center Y
            chunk.sort(key=lambda e: e.bbox.center.y)
            for j in range(0, len(chunk), page):
                leaf_entries = chunk[j : j + page]
                child = _RNode(is_leaf=True)
                child.entries = leaf_entries
                child.recompute_bbox()
                children.append(child)
        # Recursively build internal nodes
        while len(children) > _MAX_ENTRIES:
            new_children: list[_RNode] = []
            for i in range(0, len(children), _MAX_ENTRIES):
                group = children[i : i + _MAX_ENTRIES]
                internal = _RNode(is_leaf=False)
                internal.children = group
                internal.recompute_bbox()
                new_children.append(internal)
            children = new_children
        if len(children) == 1:
            return children[0]
        root = _RNode(is_leaf=False)
        root.children = children
        root.recompute_bbox()
        return root

    def all_entries(self) -> list[RTreeEntry]:
        """Collect all entries (for serialization / debugging)."""
        entries: list[RTreeEntry] = []
        RTree._collect_entries(self._root, entries)
        return entries

    @property
    def height(self) -> int:
        h = 0
        node = self._root
        while not node.is_leaf and node.children:
            h += 1
            node = node.children[0]
        return h


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _bbox_distance(bb: BBox, point: Vec2) -> float:
    """Minimum distance from *point* to the boundary/interior of *bb*."""
    dx = max(bb.min_pt.x - point.x, 0.0, point.x - bb.max_pt.x)
    dy = max(bb.min_pt.y - point.y, 0.0, point.y - bb.max_pt.y)
    return (dx * dx + dy * dy) ** 0.5
