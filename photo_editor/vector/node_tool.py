"""Node Tool — interactive vector anchor / handle manipulation.

The Node Tool allows users to:
* Select and move anchor points (nodes)
* Adjust Bézier control handles (in-handle, out-handle)
* Toggle handle modes (sharp / smooth / symmetric)
* Insert nodes by clicking on a segment (double-click)
* Delete selected nodes (Delete / Backspace)
* Rubber-band (marquee) selection of multiple nodes
* Break / join paths at selected nodes
* Move entire selected objects when dragging object body

This mirrors Affinity Designer's Node Tool and Illustrator's Direct
Selection Tool.
"""

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from ..tools.tool_base import Tool
from ..core.enums import LayerType

from ..vector.geometry import Vec2, BBox
from ..vector.path import VectorPath, SubPath, PathNode, PathSegment, HandleMode, SegmentType
from ..vector.scene import VectorObject, VectorLayer

if TYPE_CHECKING:
    from ..core.document import Document

__all__ = ["NodeTool"]


class NodeTool(Tool):
    """Node manipulation tool for vector paths."""

    def __init__(self) -> None:
        super().__init__("Node")
        # Hit state
        self._hit_object: VectorObject | None = None
        self._hit_subpath_idx: int = -1
        self._hit_node_idx: int = -1
        self._hit_component: str = ""  # "position", "in_handle", "out_handle"
        # Drag state
        self._drag_start: Vec2 | None = None
        self._drag_current: Vec2 | None = None
        self._dragging: bool = False
        self._snapshot_taken: bool = False
        # Object body drag (move whole object)
        self._body_drag: bool = False
        self._body_drag_origin: Vec2 | None = None
        # Marquee selection
        self._marquee_start: Vec2 | None = None
        self._marquee_current: Vec2 | None = None
        self._marquee_active: bool = False
        # Multi-node move: track all selected nodes' original positions
        self._moving_nodes: list[tuple[VectorObject, int, int, Vec2]] = []
        # Segment drag state
        self._seg_drag: bool = False
        self._seg_drag_si: int = -1
        self._seg_drag_seg_idx: int = -1
        self._seg_drag_t: float = 0.5
        # Tolerances (screen pixels)
        self.node_tolerance: float = 8.0
        self.handle_tolerance: float = 7.0
        self.stroke_tolerance: float = 6.0
        # Style defaults (for property bar sync)
        self.fill_color: tuple[float, float, float, float] = (0.8, 0.8, 0.8, 1.0)
        self.stroke_color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
        self.stroke_width: float = 2.0
        # Throttle rasterize during drag (~12 fps)
        self._last_rasterize_time: float = 0.0
        self._rasterize_interval: float = 0.08

    # ---- Tool interface -----------------------------------------------------

    def on_press(self, doc: "Document", x: int, y: int, pressure: float = 1.0) -> None:
        pos = Vec2(float(x), float(y))
        self._drag_start = pos
        self._drag_current = pos
        self._dragging = False
        self._snapshot_taken = False
        self._body_drag = False
        self._body_drag_origin = None
        self._marquee_start = None
        self._marquee_current = None
        self._marquee_active = False
        self._moving_nodes.clear()
        self._seg_drag = False

        vl = self._get_vector_layer(doc)
        if vl is None:
            return

        # 1. Try hitting a handle on selected objects (handles have priority)
        alt_held = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier)
        for obj in vl.selected_objects():
            hit = self._hit_test_handles(obj, pos)
            if hit is not None:
                si, ni, comp = hit
                # Alt+click on a handle → delete that single handle
                if alt_held:
                    doc.save_snapshot("Node: delete handle")
                    obj.detach_shape()
                    sp = obj.effective_path().sub_paths[si]
                    node = sp.nodes[ni]
                    if comp == "in_handle":
                        node.in_handle = None
                    elif comp == "out_handle":
                        node.out_handle = None
                    # If both handles are now gone, revert to SHARP
                    if node.in_handle is None and node.out_handle is None:
                        node.mode = HandleMode.SHARP
                    sp.invalidate()
                    obj.effective_path().invalidate()
                    obj.invalidate()
                    self._rasterize_to_layer(doc)
                    return
                self._hit_object = obj
                self._hit_subpath_idx = si
                self._hit_node_idx = ni
                self._hit_component = comp
                return

        # 2. Try hitting a node on selected objects
        shift_held = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)
        for obj in vl.selected_objects():
            hit = self._hit_test_nodes(obj, pos)
            if hit is not None:
                si, ni = hit
                self._hit_object = obj
                self._hit_subpath_idx = si
                self._hit_node_idx = ni
                self._hit_component = "position"
                node = obj.effective_path().sub_paths[si].nodes[ni]
                if shift_held:
                    # Toggle node selection with Shift
                    node.selected = not node.selected
                else:
                    # Without Shift: if node is already selected, keep multi-selection
                    # for dragging. If not selected, select only this one.
                    if not node.selected:
                        self._deselect_all_nodes(vl)
                        node.selected = True
                # Collect all selected nodes for multi-drag
                self._collect_selected_nodes(vl)
                return

        # 2b. Try hitting a path segment on selected objects (for dragging curves)
        for obj in vl.selected_objects():
            seg_hit = self._hit_test_segment(obj, pos)
            if seg_hit is not None:
                si, seg_idx, t = seg_hit
                self._hit_object = obj
                self._hit_subpath_idx = si
                self._hit_node_idx = -1
                self._hit_component = "segment"
                self._seg_drag = True
                self._seg_drag_si = si
                self._seg_drag_seg_idx = seg_idx
                self._seg_drag_t = t
                return

        # 3. Try hitting any unselected object's node
        for obj in reversed(vl.objects):
            if obj.selected or not obj.visible or obj.locked:
                continue
            hit = self._hit_test_nodes(obj, pos)
            if hit is not None:
                si, ni = hit
                vl.deselect_all()
                self._deselect_all_nodes(vl)
                obj.selected = True
                node = obj.effective_path().sub_paths[si].nodes[ni]
                node.selected = True
                self._hit_object = obj
                self._hit_subpath_idx = si
                self._hit_node_idx = ni
                self._hit_component = "position"
                return

        # 4. Try hitting object body (for moving entire objects)
        hit_obj = vl.hit_test(pos, self.stroke_tolerance)
        if hit_obj is not None:
            if not hit_obj.selected:
                if not shift_held:
                    vl.deselect_all()
                    self._deselect_all_nodes(vl)
                hit_obj.selected = True
            else:
                # Clicked on already-selected object body: deselect nodes
                # so we move the whole object, unless Shift is held
                if not shift_held:
                    self._deselect_all_nodes(vl)
            self._hit_object = hit_obj
            self._hit_subpath_idx = -1
            self._hit_node_idx = -1
            self._hit_component = ""
            self._body_drag = True
            self._body_drag_origin = pos
            return

        # 5. Miss — start marquee or deselect
        vl.deselect_all()
        self._deselect_all_nodes(vl)
        self._marquee_start = pos
        self._marquee_current = pos
        self._hit_object = None

    def on_move(self, doc: "Document", x: int, y: int, pressure: float = 1.0) -> None:
        pos = Vec2(float(x), float(y))
        self._drag_current = pos

        if self._drag_start is None:
            return

        dist = pos.distance_to(self._drag_start)
        if dist > 3.0:
            self._dragging = True

        # Segment drag — reshape curve between two nodes
        if (self._seg_drag and self._hit_object is not None
                and self._hit_component == "segment" and self._dragging):
            if not self._snapshot_taken:
                doc.save_snapshot("Node: reshape segment")
                self._snapshot_taken = True
            self._hit_object.detach_shape()
            sp = self._hit_object.effective_path().sub_paths[self._seg_drag_si]
            seg_idx = self._seg_drag_seg_idx
            n = len(sp.nodes)
            # Identify the two nodes bounding this segment
            n0 = sp.nodes[seg_idx]
            if seg_idx + 1 < n:
                n1 = sp.nodes[seg_idx + 1]
            elif sp.closed:
                n1 = sp.nodes[0]
            else:
                self._seg_drag = False
                return

            try:
                inv = self._hit_object.transform.inverse()
                local_pt = inv.apply(pos)
                local_start = inv.apply(self._drag_start)
            except ValueError:
                local_pt = pos
                local_start = self._drag_start

            delta = local_pt - local_start
            t = self._seg_drag_t

            # Ensure the relevant handles exist for this segment.
            # n0 only needs out_handle (controls curve going forward),
            # n1 only needs in_handle (controls curve coming in).
            # We do NOT create both handles — a node can have one sharp
            # side and one smooth side.
            if n0.out_handle is None:
                direction = self._compute_auto_handle_dir(sp, seg_idx)
                dist = self._auto_handle_length(sp, seg_idx)
                n0.out_handle = n0.position + direction * dist
            ni1 = (seg_idx + 1) % n
            if n1.in_handle is None:
                direction = self._compute_auto_handle_dir(sp, ni1)
                dist = self._auto_handle_length(sp, ni1)
                n1.in_handle = n1.position - direction * dist

            # Move the relevant handles to reshape the segment
            # Weight the movement by t: at t=0.5, both handles move equally
            w0 = 1.0 - t  # weight for out_handle of n0
            w1 = t         # weight for in_handle of n1
            scale_factor = 1.5  # amplify for responsiveness
            if n0.out_handle is not None:
                n0.set_out_handle(n0.out_handle + delta * (w0 * scale_factor))
            if n1.in_handle is not None:
                n1.set_in_handle(n1.in_handle + delta * (w1 * scale_factor))

            self._drag_start = pos  # incremental delta
            sp.invalidate()
            self._hit_object.effective_path().invalidate()
            self._hit_object.invalidate()
            self._throttled_rasterize(doc)
            return

        # Body drag — move entire object
        if self._body_drag and self._hit_object is not None and self._dragging:
            if not self._snapshot_taken:
                doc.save_snapshot("Node: move object")
                self._snapshot_taken = True
            origin = self._body_drag_origin or self._drag_start
            delta = pos - origin
            self._body_drag_origin = pos
            from ..vector.geometry import AffineTransform
            self._hit_object.transform = (
                AffineTransform.translation(delta.x, delta.y)
                .concat(self._hit_object.transform)
            )
            self._hit_object.invalidate()
            self._throttled_rasterize(doc)
            return

        # Handle drag
        if (self._hit_object is not None and self._hit_node_idx >= 0
                and self._hit_component in ("in_handle", "out_handle")
                and self._dragging):
            if not self._snapshot_taken:
                doc.save_snapshot("Node: move handle")
                self._snapshot_taken = True
            self._hit_object.detach_shape()
            sp = self._hit_object.effective_path().sub_paths[self._hit_subpath_idx]
            node = sp.nodes[self._hit_node_idx]
            try:
                inv = self._hit_object.transform.inverse()
                local_pt = inv.apply(pos)
            except ValueError:
                local_pt = pos
            if self._hit_component == "in_handle":
                node.set_in_handle(local_pt)
            else:
                node.set_out_handle(local_pt)
            sp.invalidate()
            self._hit_object.effective_path().invalidate()
            self._hit_object.invalidate()
            self._throttled_rasterize(doc)
            return

        # Node position drag (multi-select)
        if (self._hit_object is not None and self._hit_node_idx >= 0
                and self._hit_component == "position" and self._dragging):
            if not self._snapshot_taken:
                doc.save_snapshot("Node: move")
                self._snapshot_taken = True
            delta = pos - self._drag_start
            for obj, si, ni, orig_world in self._moving_nodes:
                obj.detach_shape()
                try:
                    inv = obj.transform.inverse()
                    local_orig = inv.apply(orig_world)
                    local_new = inv.apply(orig_world + delta)
                except ValueError:
                    local_orig = orig_world
                    local_new = orig_world + delta
                
                # Careful: obj.effective_path() might regenerate if we called obj.invalidate() in loop?
                # Actually obj.invalidate() clears cache. detach_shape() sets .path.
                # So effective_path() returns .path.
                path = obj.effective_path()
                sp = path.sub_paths[si]
                node = sp.nodes[ni]
                node.set_position(local_new)
                sp.invalidate()
                path.invalidate()
                obj.invalidate()
            self._throttled_rasterize(doc)
            return

        # Marquee update
        if self._marquee_start is not None and self._dragging:
            self._marquee_active = True
            self._marquee_current = pos
    
    def on_release(self, doc: "Document", x: int, y: int) -> None:
        pos = Vec2(float(x), float(y))

        if self._marquee_active and self._marquee_start is not None:
            self._do_marquee_select(doc, self._marquee_start, pos)

        if self._dragging and self._snapshot_taken:
            self._rasterize_to_layer(doc)

        # Reset state
        self._drag_start = None
        self._drag_current = None
        self._dragging = False
        self._body_drag = False
        self._body_drag_origin = None
        self._marquee_start = None
        self._marquee_current = None
        self._marquee_active = False
        self._moving_nodes.clear()

    # ---- Node operations (called by keyboard shortcuts / main_window) -------

    def delete_selected_nodes(self, doc: "Document") -> None:
        """Delete all selected nodes from selected objects.
        
        If no nodes are selected, deletes the entire selected objects.
        """
        vl = self._get_vector_layer(doc)
        if vl is None:
            return

        has_selected = False
        for obj in vl.selected_objects():
            path = obj.effective_path()
            for sp in path.sub_paths:
                if any(n.selected for n in sp.nodes):
                    has_selected = True
                    break
            if has_selected:
                break

        if not has_selected:
            # No selected nodes → delete selected objects
            selected = list(vl.selected_objects())
            if selected:
                doc.save_snapshot("Node: delete object")
                for obj in selected:
                    vl.remove(obj.id)
                self._hit_object = None
                self._rasterize_to_layer(doc)
            return

        doc.save_snapshot("Node: delete nodes")
        for obj in vl.selected_objects():
            obj.detach_shape()
            path = obj.effective_path()
            for sp in path.sub_paths:
                to_remove = [i for i, n in enumerate(sp.nodes) if n.selected]
                for idx in reversed(to_remove):
                    sp.remove_node(idx)
                if to_remove:
                    sp.invalidate()
            # Remove empty sub-paths
            path.sub_paths = [sp for sp in path.sub_paths if sp.node_count > 0]
            path.invalidate()
            obj.invalidate()

        # Remove objects with no sub-paths left
        empty_ids = []
        for obj in vl.selected_objects():
            if not obj.effective_path().sub_paths:
                empty_ids.append(obj.id)
        for oid in empty_ids:
            vl.remove(oid)

        self._hit_object = None
        self._rasterize_to_layer(doc)

    def toggle_node_mode(self, doc: "Document") -> None:
        """Cycle handle mode on selected nodes: SHARP → SMOOTH → SYMMETRIC → SHARP."""
        vl = self._get_vector_layer(doc)
        if vl is None:
            return

        changed = False
        for obj in vl.selected_objects():
            obj.detach_shape()
            path = obj.effective_path()
            obj_changed = False
            for sp in path.sub_paths:
                sp_changed = False
                for node in sp.nodes:
                    if node.selected:
                        if not changed:
                            doc.save_snapshot("Node: toggle mode")
                            changed = True
                        node.toggle_mode()
                        # Apply constraint based on new mode
                        if node.mode == HandleMode.SYMMETRIC and node.out_handle:
                            offset = node.out_handle - node.position
                            node.in_handle = node.position - offset
                        elif node.mode == HandleMode.SMOOTH and node.in_handle and node.out_handle:
                            direction = (node.out_handle - node.position).normalized()
                            in_len = node.in_handle.distance_to(node.position)
                            node.in_handle = node.position - direction * in_len
                        sp_changed = True
                        obj_changed = True
                if sp_changed:
                    sp.invalidate()
            if obj_changed:
                path.invalidate()
                obj.invalidate()

        if changed:
            self._rasterize_to_layer(doc)

    @staticmethod
    def _compute_auto_handle_dir(sp: SubPath, ni: int) -> Vec2:
        """Compute a natural handle direction based on neighboring nodes.
        
        Returns a normalized direction vector from the previous node
        toward the next node. Falls back to Vec2(1,0) if no neighbors.
        """
        nodes = sp.nodes
        n = len(nodes)
        prev_pos = None
        next_pos = None
        
        if ni > 0:
            prev_pos = nodes[ni - 1].position
        elif sp.closed and n >= 3:
            prev_pos = nodes[-1].position
            
        if ni < n - 1:
            next_pos = nodes[ni + 1].position
        elif sp.closed and n >= 3:
            next_pos = nodes[0].position
        
        node_pos = nodes[ni].position
        
        if prev_pos is not None and next_pos is not None:
            direction = (next_pos - prev_pos).normalized()
            if direction.length_sq() < 1e-9:
                direction = Vec2(1.0, 0.0)
            return direction
        elif next_pos is not None:
            direction = (next_pos - node_pos).normalized()
            if direction.length_sq() < 1e-9:
                direction = Vec2(1.0, 0.0)
            return direction
        elif prev_pos is not None:
            direction = (node_pos - prev_pos).normalized()
            if direction.length_sq() < 1e-9:
                direction = Vec2(1.0, 0.0)
            return direction
        
        return Vec2(1.0, 0.0)

    def set_node_mode(self, doc: "Document", mode: HandleMode) -> None:
        """Set handle mode on all selected nodes to the given mode."""
        vl = self._get_vector_layer(doc)
        if vl is None:
            return

        changed = False
        for obj in vl.selected_objects():
            obj.detach_shape()
            path = obj.effective_path()
            obj_changed = False
            for sp in path.sub_paths:
                sp_changed = False
                for ni, node in enumerate(sp.nodes):
                    if node.selected and node.mode != mode:
                        if not changed:
                            doc.save_snapshot(f"Node: set {mode.name.lower()}")
                            changed = True
                        node.mode = mode
                        if mode == HandleMode.SHARP:
                            # Remove handles to make straight line segments
                            node.in_handle = None
                            node.out_handle = None
                        elif mode == HandleMode.SMOOTH:
                            if node.out_handle and node.in_handle:
                                # Existing handles: enforce collinearity
                                direction = (node.out_handle - node.position).normalized()
                                in_len = node.in_handle.distance_to(node.position)
                                node.in_handle = node.position - direction * in_len
                            else:
                                # Create handles along neighbor direction
                                direction = self._compute_auto_handle_dir(sp, ni)
                                dist = self._auto_handle_length(sp, ni)
                                node.out_handle = node.position + direction * dist
                                node.in_handle = node.position - direction * dist
                        elif mode == HandleMode.SYMMETRIC:
                            if node.out_handle:
                                offset = node.out_handle - node.position
                                node.in_handle = node.position - offset
                            elif node.in_handle:
                                offset = node.in_handle - node.position
                                node.out_handle = node.position - offset
                            else:
                                # Create handles along neighbor direction
                                direction = self._compute_auto_handle_dir(sp, ni)
                                dist = self._auto_handle_length(sp, ni)
                                node.out_handle = node.position + direction * dist
                                node.in_handle = node.position - direction * dist
                        sp_changed = True
                        obj_changed = True
                if sp_changed:
                    sp.invalidate()
            if obj_changed:
                path.invalidate()
                obj.invalidate()

        if changed:
            self._rasterize_to_layer(doc)

    @staticmethod
    def _auto_handle_length(sp: SubPath, ni: int) -> float:
        """Compute a sensible default handle length (~1/3 of avg neighbor distance)."""
        nodes = sp.nodes
        n = len(nodes)
        total = 0.0
        count = 0
        pos = nodes[ni].position
        if ni > 0:
            total += pos.distance_to(nodes[ni - 1].position)
            count += 1
        elif sp.closed and n >= 3:
            total += pos.distance_to(nodes[-1].position)
            count += 1
        if ni < n - 1:
            total += pos.distance_to(nodes[ni + 1].position)
            count += 1
        elif sp.closed and n >= 3:
            total += pos.distance_to(nodes[0].position)
            count += 1
        if count == 0:
            return 20.0
        return max(5.0, (total / count) * 0.33)

    def insert_node_on_segment(self, doc: "Document", x: int, y: int) -> None:
        """Insert a node at the point on the path nearest to (x, y)."""
        pos = Vec2(float(x), float(y))
        vl = self._get_vector_layer(doc)
        if vl is None:
            return

        def _point_line_distance(p: Vec2, a: Vec2, b: Vec2) -> float:
            ab = b - a
            d2 = ab.length_sq()
            if d2 == 0:
                return p.distance_to(a)
            t = max(0.0, min(1.0, (p - a).dot(ab) / d2))
            proj = a + ab * t
            return p.distance_to(proj)

        for obj in vl.selected_objects():
            obj.detach_shape()
            path = obj.effective_path()
            for si, sp in enumerate(path.sub_paths):
                best_seg = -1
                best_t = 0.5
                best_dist = float("inf")

                try:
                    inv = obj.transform.inverse()
                    local_pt = inv.apply(pos)
                except ValueError:
                    local_pt = pos

                start = sp.origin
                if start is None:
                    continue

                for seg_i, curve in enumerate(sp.iter_curves()):
                    t, nearest = curve.nearest_point(local_pt)
                    d = local_pt.distance_to(nearest)
                    if d < best_dist:
                        best_dist = d
                        best_seg = seg_i
                        # Clamp t to avoid trivial splits at endpoints
                        best_t = max(0.05, min(0.95, t))

                if best_seg >= 0 and best_dist < self.stroke_tolerance * 3:
                    doc.save_snapshot("Node: insert")
                    new_node = sp.insert_node_at_t(best_seg, best_t)
                    if new_node:
                        new_node.selected = True
                    sp.invalidate()
                    path.invalidate()
                    obj.invalidate()
                    self._rasterize_to_layer(doc)
                    return

    def break_path_at_node(self, doc: "Document") -> None:
        """Break the path at selected nodes, creating open endpoints."""
        vl = self._get_vector_layer(doc)
        if vl is None:
            return
        doc.save_snapshot("Node: break path")

        for obj in vl.selected_objects():
            obj.detach_shape()
            path = obj.effective_path()
            new_sub_paths: list[SubPath] = []
            for sp in path.sub_paths:
                selected_indices = [i for i, n in enumerate(sp.nodes) if n.selected]
                if not selected_indices:
                    new_sub_paths.append(sp)
                    continue
                if sp.closed:
                    idx = selected_indices[0]
                    nodes = sp.nodes[idx:] + sp.nodes[:idx]
                    new_sp = SubPath(nodes, closed=False)
                    new_sub_paths.append(new_sp)
                else:
                    prev = 0
                    for idx in selected_indices:
                        if idx > prev:
                            chunk = sp.nodes[prev:idx + 1]
                            new_sub_paths.append(SubPath(list(chunk), closed=False))
                        prev = idx
                    if prev < len(sp.nodes):
                        chunk = sp.nodes[prev:]
                        new_sub_paths.append(SubPath(list(chunk), closed=False))

            path.sub_paths = new_sub_paths
            path.invalidate()
            obj.invalidate()
        self._rasterize_to_layer(doc)

    def select_all_nodes(self, doc: "Document") -> None:
        """Select all nodes on selected objects."""
        vl = self._get_vector_layer(doc)
        if vl is None:
            return
        for obj in vl.selected_objects():
            path = obj.effective_path()
            for sp in path.sub_paths:
                for node in sp.nodes:
                    node.selected = True

    # ---- Internal helpers ---------------------------------------------------

    def _hit_test_handles(self, obj: VectorObject, pos: Vec2) -> tuple[int, int, str] | None:
        """Test handles on already-selected nodes (priority over node body)."""
        try:
            inv = obj.transform.inverse()
        except ValueError:
            return None
        local_pt = inv.apply(pos)
        tol_sq = self.handle_tolerance ** 2
        path = obj.effective_path()
        for si, sp in enumerate(path.sub_paths):
            for ni, node in enumerate(sp.nodes):
                if not node.selected:
                    continue
                if node.out_handle is not None:
                    if local_pt.distance_sq_to(node.out_handle) < tol_sq:
                        return (si, ni, "out_handle")
                if node.in_handle is not None:
                    if local_pt.distance_sq_to(node.in_handle) < tol_sq:
                        return (si, ni, "in_handle")
        return None

    def _hit_test_nodes(self, obj: VectorObject, pos: Vec2) -> tuple[int, int] | None:
        """Test node positions on an object."""
        try:
            inv = obj.transform.inverse()
        except ValueError:
            return None
        local_pt = inv.apply(pos)
        tol_sq = self.node_tolerance ** 2
        path = obj.effective_path()
        for si, sp in enumerate(path.sub_paths):
            for ni, node in enumerate(sp.nodes):
                if local_pt.distance_sq_to(node.position) < tol_sq:
                    return (si, ni)
        return None

    def _hit_test_segment(self, obj: VectorObject, pos: Vec2) -> tuple[int, int, float] | None:
        """Test if click is on a path segment. Returns (si, seg_idx, t) or None."""
        try:
            inv = obj.transform.inverse()
        except ValueError:
            return None
        local_pt = inv.apply(pos)
        tol = self.stroke_tolerance * 2.0
        path = obj.effective_path()
        for si, sp in enumerate(path.sub_paths):
            for seg_idx, curve in enumerate(sp.iter_curves()):
                t, nearest = curve.nearest_point(local_pt)
                d = local_pt.distance_to(nearest)
                if d < tol:
                    return (si, seg_idx, max(0.1, min(0.9, t)))
        return None

    def _collect_selected_nodes(self, vl: VectorLayer) -> None:
        """Collect all selected nodes across all selected objects for multi-drag."""
        self._moving_nodes.clear()
        for obj in vl.selected_objects():
            path = obj.effective_path()
            for si, sp in enumerate(path.sub_paths):
                for ni, node in enumerate(sp.nodes):
                    if node.selected:
                        world_pos = obj.transform.apply(node.position)
                        self._moving_nodes.append((obj, si, ni, world_pos))

    def _do_marquee_select(self, doc: "Document", start: Vec2, end: Vec2) -> None:
        """Select all nodes within the marquee rectangle."""
        rect = BBox(
            Vec2(min(start.x, end.x), min(start.y, end.y)),
            Vec2(max(start.x, end.x), max(start.y, end.y)),
        )
        vl = self._get_vector_layer(doc)
        if vl is None:
            return

        # Select objects overlapping the marquee
        for obj in vl.objects:
            if not obj.visible or obj.locked:
                continue
            obj_bb = obj.bbox()
            if rect.intersects(obj_bb):
                obj.selected = True

        # Select individual nodes within the marquee
        for obj in vl.selected_objects():
            path = obj.effective_path()
            for sp in path.sub_paths:
                for node in sp.nodes:
                    pt = obj.transform.apply(node.position)
                    if rect.contains_point(pt):
                        node.selected = True

    def _deselect_all_nodes(self, vl: VectorLayer) -> None:
        for obj in vl.objects:
            path = obj.effective_path()
            for sp in path.sub_paths:
                for node in sp.nodes:
                    node.selected = False

    @staticmethod
    def _get_vector_layer(doc: "Document") -> VectorLayer | None:
        layer = doc.layers.active_layer
        if layer is None:
            return None
        return getattr(layer, "_vector_data", None)

    @staticmethod
    def _rasterize_to_layer(doc: "Document") -> None:
        from .rasterizer import rasterize_vector_layer_tight
        rasterize_vector_layer_tight(doc, force=True)

    def _throttled_rasterize(self, doc: "Document") -> None:
        """Rasterize at most once per ``_rasterize_interval`` during drag."""
        now = time.monotonic()
        if now - self._last_rasterize_time >= self._rasterize_interval:
            self._rasterize_to_layer(doc)
            self._last_rasterize_time = now

    # ---- State queries for UI overlay ---------------------------------------

    @property
    def selected_object(self) -> VectorObject | None:
        return self._hit_object

    @property
    def marquee_rect(self) -> tuple[Vec2, Vec2] | None:
        """Return the current marquee rectangle for overlay drawing."""
        if self._marquee_active and self._marquee_start and self._marquee_current:
            return (self._marquee_start, self._marquee_current)
        return None

    @property
    def is_dragging_node(self) -> bool:
        return self._dragging and self._hit_node_idx >= 0

    @property
    def is_body_dragging(self) -> bool:
        return self._body_drag and self._dragging

    def selected_nodes_bbox(self, doc: "Document") -> tuple[float, float, float, float] | None:
        """Return bounding box (x, y, w, h) in doc coords for all selected nodes.

        Returns None if fewer than 2 nodes are selected.
        """
        vl = self._get_vector_layer(doc)
        if vl is None:
            return None

        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")
        count = 0

        for obj in vl.selected_objects():
            path = obj.effective_path()
            for sp in path.sub_paths:
                for node in sp.nodes:
                    if node.selected:
                        pt = obj.transform.apply(node.position)
                        min_x = min(min_x, pt.x)
                        min_y = min(min_y, pt.y)
                        max_x = max(max_x, pt.x)
                        max_y = max(max_y, pt.y)
                        count += 1

        if count < 2:
            return None
        return (min_x, min_y, max_x - min_x, max_y - min_y)
