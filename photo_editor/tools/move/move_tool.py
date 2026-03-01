"""MoveTool — the main move/resize/rotate layer tool.

This module assembles the sub-module mixins into the final ``MoveTool``
class.  All heavy lifting is delegated:

* Hit-testing          → :mod:`.hit_test`
* Layer auto-select    → :mod:`.auto_select`
* Floating selection   → :mod:`.float_selection.FloatSelectionMixin`
* Resize operations    → :mod:`.resize_ops.ResizeMixin`
* Rotate operations    → :mod:`.rotate_ops.RotateMixin`
* Vector baking        → :mod:`.vector_commit.VectorCommitMixin`
* Alignment / flip     → :mod:`.align_ops`
"""

from __future__ import annotations

import numpy as np

from ..tool_base import Tool
from ...core.document import Document
from ...core.enums import LayerType

from ._enums import _Mode, _Handle
from . import hit_test as _ht
from .auto_select import find_layer_at, point_on_layer
from .float_selection import FloatSelectionMixin
from .resize_ops import ResizeMixin
from .rotate_ops import RotateMixin
from .vector_commit import VectorCommitMixin
from . import align_ops as _align


class MoveTool(FloatSelectionMixin, ResizeMixin, RotateMixin, VectorCommitMixin, Tool):
    """Click-drag to move; drag handles to resize; drag outside box to rotate.

    Uses the layer's non-destructive transform system so resize and
    rotate operations always recompute display pixels from the stored
    original source — quality is never lost no matter how many times
    the user transforms a layer (Affinity-style).
    """

    # Expose these as class-level constants so external code can read them
    HANDLE_MARGIN = _ht.HANDLE_MARGIN
    ROTATE_HANDLE_OFFSET = _ht.ROTATE_HANDLE_OFFSET

    def __init__(self) -> None:
        super().__init__("Move")
        self._mode = _Mode.NONE
        self._handle = _Handle.NONE
        self._start_x: int = 0
        self._start_y: int = 0
        self._orig_position: tuple[int, int] = (0, 0)
        self._orig_pixels: np.ndarray | None = None
        self._orig_width: int = 0
        self._orig_height: int = 0
        self._dragging: bool = False
        self._current_angle: float = 0.0
        # Reference to the layer being transformed (for mid-drag writes)
        self._active_layer = None
        # Anchor state for rotated resize
        self._anchor_screen: tuple[float, float] = (0.0, 0.0)
        self._anchor_sign: tuple[int, int] = (0, 0)
        self._is_rotated_resize: bool = False
        # Non-destructive transform: angle at the start of the drag
        self._base_angle: float = 0.0
        # Auto-select: when True, clicking outside the active layer
        # picks the topmost visible layer whose opaque pixels are
        # under the cursor.
        self.auto_select: bool = True
        # Callback set by MainWindow to handle layer selection changes.
        # Signature: (layer_index: int) -> None
        self.on_layer_auto_selected: callable | None = None
        # Group support: track children and their original state
        self._group_children: list = []
        self._group_child_positions: dict[str, tuple[int, int]] = {}
        self._group_child_pixels: dict[str, np.ndarray] = {}
        self._group_orig_bbox: tuple[int, int, int, int] | None = None
        # Non-destructive group transforms (Affinity-style)
        self._group_child_base_sx: dict[str, float] = {}
        self._group_child_base_sy: dict[str, float] = {}
        self._group_child_base_angle: dict[str, float] = {}
        self._group_child_dims: dict[str, tuple[int, int]] = {}
        # Floating selection state (used by FloatSelectionMixin)
        self._floating: bool = False
        self._float_pixels: np.ndarray | None = None
        self._float_base: np.ndarray | None = None
        self._float_orig: np.ndarray | None = None
        self._float_dx: int = 0
        self._float_dy: int = 0
        self._float_committed_dx: int = 0
        self._float_committed_dy: int = 0
        # Vector transform pivot (used by VectorCommitMixin)
        self._orig_center: tuple[float, float] = (0.0, 0.0)

    # ------------------------------------------------------------------
    # Public query (used by MainWindow for bounding-box overlay)
    # ------------------------------------------------------------------

    def rotation_info_for(self, layer) -> tuple[int, int, float] | None:
        """Return ``(base_w, base_h, total_angle)`` for *layer*.

        The total angle includes any mid-drag rotation that has not yet
        been committed.  Returns ``None`` when the layer has no rotation.
        """
        if layer is None:
            return None
        extra = self._current_angle if (layer is self._active_layer) else 0.0
        total = layer.transform_angle + extra
        if total != 0.0 and layer.transform_base_w > 0:
            return (layer.transform_base_w, layer.transform_base_h, total)
        return None

    # ------------------------------------------------------------------
    # Hit-test wrappers (delegate to hit_test module)
    # ------------------------------------------------------------------

    @staticmethod
    def _bbox(doc: Document) -> tuple[int, int, int, int] | None:
        return _ht.bbox(doc)

    @staticmethod
    def _group_bbox(doc: Document, group) -> tuple[int, int, int, int] | None:
        return _ht.group_bbox(doc, group)

    def _hit_test(self, doc: Document, x: int, y: int) -> tuple[_Mode, _Handle]:
        return _ht.hit_test(doc, x, y, current_angle=self._current_angle)

    @staticmethod
    def _hit_test_rect(
        bx: float, by: float, bw: float, bh: float,
        x: float, y: float,
    ) -> tuple[_Mode, _Handle]:
        return _ht.hit_test_rect(bx, by, bw, bh, x, y)

    # ------------------------------------------------------------------
    # Auto-select wrappers (delegate to auto_select module)
    # ------------------------------------------------------------------

    @staticmethod
    def _point_on_layer(layer, x: int, y: int, alpha_threshold: float = 0.01) -> bool:
        return point_on_layer(layer, x, y, alpha_threshold)

    @staticmethod
    def _find_layer_at(
        doc: Document, x: int, y: int,
        exclude_id: str | None = None,
        alpha_threshold: float = 0.01,
    ) -> int | None:
        return find_layer_at(doc, x, y, exclude_id, alpha_threshold)

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        layer = doc.layers.active_layer

        # --- Auto-select: always pick the topmost visible layer at the
        #     click point, unless the click lands on a resize/rotate
        #     handle of the active layer's bounding box. -----------------
        auto_switched = False
        if self.auto_select:
            skip_autoselect = False
            if layer is not None:
                mode_hit, _ = self._hit_test(doc, x, y)
                # Skip auto-select when clicking inside the bbox (MOVE)
                # or on a resize handle so the user can transform the
                # active layer without triggering an unwanted switch.
                # ROTATE (outside bbox) does NOT skip, so auto-select
                # can still find a layer underneath.
                if mode_hit in (_Mode.MOVE, _Mode.RESIZE):
                    skip_autoselect = True

            if not skip_autoselect:
                topmost_idx = find_layer_at(doc, x, y)
                if topmost_idx is not None:
                    topmost = doc.layers.layers[topmost_idx]
                    if layer is None or topmost.id != layer.id:
                        doc.layers.active_index = topmost_idx
                        if self.on_layer_auto_selected:
                            self.on_layer_auto_selected(topmost_idx)
                        layer = doc.layers.active_layer
                        auto_switched = True

        if layer is None or layer.locked:
            return

        self._mode, self._handle = self._hit_test(doc, x, y)

        # If the click lands in the ROTATE zone and auto-select switched
        # layers, demote to MOVE (on opaque pixels) or NONE (empty).
        # Without a switch, keep ROTATE so the user can rotate the layer
        # from anywhere outside the bbox.
        if self.auto_select and self._mode == _Mode.ROTATE:
            if auto_switched:
                if point_on_layer(layer, x, y):
                    self._mode = _Mode.MOVE
                    self._handle = _Handle.NONE
                else:
                    self._mode = _Mode.NONE
                    return

        label = {_Mode.MOVE: "Move", _Mode.RESIZE: "Resize", _Mode.ROTATE: "Rotate"}
        doc.save_snapshot(label.get(self._mode, "Transform"))

        self._start_x, self._start_y = x, y
        self._orig_position = layer.position
        self._dragging = True
        self._active_layer = layer
        self._is_rotated_resize = False
        self._current_angle = 0.0
        self._base_angle = layer.transform_angle

        # -- Floating selection: if a selection is active and mode is MOVE,
        #    cut selected pixels into a floating buffer. -------------------
        if (self._mode == _Mode.MOVE
                and doc.selection.active
                and layer.layer_type not in (LayerType.GROUP, LayerType.ADJUSTMENT, LayerType.FILTER)):

            # Continue an in-progress float without re-cutting
            if self._floating and self._float_pixels is not None:
                self._float_dx = self._float_committed_dx
                self._float_dy = self._float_committed_dy
                return

            sel_mask = self._get_sel_mask(doc)
            if sel_mask is not None and sel_mask.max() > 0:
                mask4 = sel_mask[..., np.newaxis]
                self._float_orig = layer.pixels.copy()
                self._float_pixels = layer.pixels * mask4
                layer.pixels[:] = layer.pixels * (1.0 - mask4)
                np.clip(layer.pixels, 0, 1, out=layer.pixels)
                self._float_base = layer.pixels.copy()
                self._floating = True
                self._float_dx = 0
                self._float_dy = 0
                self._float_committed_dx = 0
                self._float_committed_dy = 0
                return  # skip normal setup

        # If there's an existing float but we're not continuing it, commit it
        if self._floating:
            self.commit_float(doc)

        # -- Group setup ---------------------------------------------------
        self._group_children = []
        self._group_child_positions = {}
        self._group_child_pixels = {}
        self._group_orig_bbox = None
        self._group_child_base_sx = {}
        self._group_child_base_sy = {}
        self._group_child_base_angle = {}
        self._group_child_dims = {}

        if layer.layer_type == LayerType.GROUP:
            for child in doc.layers:
                if child.parent_id != layer.id:
                    continue
                self._group_children.append(child)
                self._group_child_positions[child.id] = child.position
                if child.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER):
                    continue
                # Composite group children to get raster pixels for scaling
                if child.layer_type == LayerType.GROUP:
                    from ...engine.compositor import Compositor
                    from ...core.layer_stack import LayerStack
                    compositor = Compositor()
                    px = compositor.composite_group_tight(child, doc.layers)
                    if px is not None and px.size > 0:
                        bounds = LayerStack._content_bounds(child, doc.layers)
                        if bounds is not None:
                            child.position = (int(bounds[0]), int(bounds[1]))
                        child.pixels = px
                child.init_non_destructive()
                self._group_child_base_sx[child.id] = child.transform_scale_x
                self._group_child_base_sy[child.id] = child.transform_scale_y
                self._group_child_base_angle[child.id] = child.transform_angle
                self._group_child_dims[child.id] = (child.width, child.height)
            bbox = _ht.group_bbox(doc, layer)
            self._group_orig_bbox = bbox
            if bbox:
                self._orig_width = bbox[2]
                self._orig_height = bbox[3]
            else:
                self._orig_width = layer.width
                self._orig_height = layer.height
            self._orig_pixels = None
            return  # skip single-layer setup below

        # -- Single-layer non-destructive setup ----------------------------
        layer.init_non_destructive()

        # Collect mask children so transforms propagate to them
        self._mask_children: list = []
        self._mask_child_positions: dict[str, tuple[int, int]] = {}
        self._mask_child_base_sx: dict[str, float] = {}
        self._mask_child_base_sy: dict[str, float] = {}
        self._mask_child_base_angle: dict[str, float] = {}
        for mid in layer.mask_layers:
            mc = doc.layers.get(mid)
            if mc is not None:
                mc.init_non_destructive()
                self._mask_children.append(mc)
                self._mask_child_positions[mc.id] = mc.position
                self._mask_child_base_sx[mc.id] = mc.transform_scale_x
                self._mask_child_base_sy[mc.id] = mc.transform_scale_y
                self._mask_child_base_angle[mc.id] = mc.transform_angle

        if self._mode == _Mode.ROTATE:
            self._orig_width = layer.width
            self._orig_height = layer.height

        elif self._mode == _Mode.RESIZE:
            if layer.transform_angle != 0.0 and layer.transform_base_w > 0:
                self._is_rotated_resize = True
                self._orig_width = layer.transform_base_w
                self._orig_height = layer.transform_base_h
                self._setup_resize_anchor(layer)
            else:
                self._orig_width = layer.width
                self._orig_height = layer.height

        # Record original bbox centre for vector commit
        self._orig_center = (
            layer.position[0] + layer.width / 2.0,
            layer.position[1] + layer.height / 2.0,
        )

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        if not self._dragging:
            return
        layer = doc.layers.active_layer
        if layer is None:
            return

        dx = x - self._start_x
        dy = y - self._start_y

        # -- Floating selection move --
        if self._floating and self._float_pixels is not None and self._float_base is not None:
            self._float_dx = self._float_committed_dx + dx
            self._float_dy = self._float_committed_dy + dy
            layer.pixels[:] = self._float_base
            self._composite_float(layer.pixels, self._float_dx, self._float_dy)
            return

        is_group = layer.layer_type == LayerType.GROUP

        if self._mode == _Mode.MOVE:
            ox, oy = self._orig_position
            layer.position = (ox + dx, oy + dy)
            # Move all group children together
            for child in self._group_children:
                cox, coy = self._group_child_positions[child.id]
                child.position = (cox + dx, coy + dy)
            # Move mask children with the parent
            for mc in getattr(self, "_mask_children", []):
                mcox, mcoy = self._mask_child_positions[mc.id]
                mc.position = (mcox + dx, mcoy + dy)

        elif self._mode == _Mode.RESIZE:
            if is_group:
                self._apply_group_resize(dx, dy)
            else:
                self._apply_resize(layer, dx, dy)
                self._sync_mask_transforms(layer)

        elif self._mode == _Mode.ROTATE:
            if is_group:
                self._apply_group_rotate(x, y)
            else:
                self._apply_rotate(layer, x, y)
                self._sync_mask_transforms(layer)

    def on_release(self, doc: Document, x: int, y: int) -> None:
        # Floating selection: keep the float alive, just commit the offset
        if self._floating and self._active_layer is not None:
            self._float_committed_dx = self._float_dx
            self._float_committed_dy = self._float_dy
            self._dragging = False
            self._mode = _Mode.NONE
            self._handle = _Handle.NONE
            return

        if self._mode in (_Mode.ROTATE, _Mode.RESIZE) and self._active_layer is not None:
            if self._active_layer.layer_type == LayerType.RASTER:
                self._active_layer.compute_display(fast=False)
                for mc in getattr(self, "_mask_children", []):
                    mc.compute_display(fast=False)
            elif self._active_layer.layer_type == LayerType.GROUP:
                for child in self._group_children:
                    if child.layer_type == LayerType.RASTER:
                        child.compute_display(fast=False)

        # --- Vector layer commit ---
        if self._active_layer is not None and self._mode != _Mode.NONE:
            if self._active_layer.layer_type == LayerType.SHAPE:
                vl = getattr(self._active_layer, "_vector_data", None)
                if vl:
                    self._commit_vector_transform(doc, self._active_layer, vl)
            elif self._active_layer.layer_type == LayerType.GROUP:
                self._commit_group_vector_transforms(doc)
                doc.layers.update_group_bbox(self._active_layer)

        self._dragging = False
        self._orig_pixels = None
        self._mode = _Mode.NONE
        self._handle = _Handle.NONE
        self._current_angle = 0.0
        self._base_angle = 0.0
        self._active_layer = None
        self._is_rotated_resize = False
        self._mask_children = []
        self._mask_child_positions = {}
        self._mask_child_base_sx = {}
        self._mask_child_base_sy = {}
        self._mask_child_base_angle = {}
        self._group_children = []
        self._group_child_positions = {}
        self._group_child_pixels = {}
        self._group_orig_bbox = None
        self._group_child_base_sx = {}
        self._group_child_base_sy = {}
        self._group_child_base_angle = {}
        self._group_child_dims = {}

    # ------------------------------------------------------------------
    # Alignment helpers — delegate to align_ops module
    # ------------------------------------------------------------------

    @staticmethod
    def align_left(doc: Document) -> None:
        _align.align_left(doc)

    @staticmethod
    def align_center_h(doc: Document) -> None:
        _align.align_center_h(doc)

    @staticmethod
    def align_right(doc: Document) -> None:
        _align.align_right(doc)

    @staticmethod
    def align_top(doc: Document) -> None:
        _align.align_top(doc)

    @staticmethod
    def align_middle_v(doc: Document) -> None:
        _align.align_middle_v(doc)

    @staticmethod
    def align_bottom(doc: Document) -> None:
        _align.align_bottom(doc)

    # ------------------------------------------------------------------
    # Flip / Rotate helpers — delegate to align_ops module
    # ------------------------------------------------------------------

    @staticmethod
    def flip_horizontal(doc: Document) -> None:
        _align.flip_horizontal(doc)

    @staticmethod
    def flip_vertical(doc: Document) -> None:
        _align.flip_vertical(doc)

    @staticmethod
    def rotate_90_cw(doc: Document) -> None:
        _align.rotate_90_cw(doc)

    @staticmethod
    def rotate_90_ccw(doc: Document) -> None:
        _align.rotate_90_ccw(doc)
