"""Move tool — select, move, resize, and rotate the active layer via bounding-box handles.

Uses the Layer's non-destructive transform system: resize and rotate
operations modify transform parameters (``transform_scale_x/y``,
``transform_angle``) and recompute display pixels from the stored
original source, so quality is never lost regardless of how many times
the user transforms the layer (Affinity-style).

Alignment helpers align the active layer to the canvas (document)
boundaries: left, center-h, right, top, middle-v, bottom.
"""

from __future__ import annotations

import math
from enum import Enum, auto

import numpy as np

from .tool_base import Tool
from ..core.document import Document
from ..core.enums import LayerType
from ..transforms.transform_engine import TransformEngine


class _Mode(Enum):
    NONE = auto()
    MOVE = auto()
    RESIZE = auto()
    ROTATE = auto()


class _Handle(Enum):
    NONE = auto()
    TL = auto()
    T = auto()
    TR = auto()
    L = auto()
    R = auto()
    BL = auto()
    B = auto()
    BR = auto()


# For each resize handle, the *anchor* is the opposite corner / edge.
# The sign pair maps to ``(±half_w, ±half_h)`` in the box-local frame.
_ANCHOR_SIGN: dict[_Handle, tuple[int, int]] = {
    _Handle.TL: (1, 1),
    _Handle.T:  (0, 1),
    _Handle.TR: (-1, 1),
    _Handle.L:  (1, 0),
    _Handle.R:  (-1, 0),
    _Handle.BL: (1, -1),
    _Handle.B:  (0, -1),
    _Handle.BR: (-1, -1),
}


class MoveTool(Tool):
    """Click-drag to move; drag handles to resize; drag outside box to rotate."""

    HANDLE_MARGIN = 10  # hit-test radius in document pixels

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
        # Floating selection: when an active selection exists and the user
        # drags with the move tool, only the selected pixels move.
        self._floating: bool = False
        self._float_pixels: np.ndarray | None = None
        self._float_base: np.ndarray | None = None   # base layer with hole
        self._float_orig: np.ndarray | None = None    # full original pixels (pre-cut)
        self._float_dx: int = 0
        self._float_dy: int = 0
        self._float_committed_dx: int = 0   # accumulated offset from prior drags
        self._float_committed_dy: int = 0
        # Vector transform pivot
        self._orig_center: tuple[float, float] = (0.0, 0.0)

    # ------------------------------------------------------------------
    # Floating selection helpers
    # ------------------------------------------------------------------

    def commit_float(self, doc: Document | None = None) -> None:
        """Permanently apply the floating selection to the layer pixels.

        Called when switching tools or starting a non-float interaction.
        The base pixels under the float's new position are replaced.
        """
        if not self._floating or self._float_pixels is None or self._active_layer is None:
            self._clear_float()
            return
        layer = self._active_layer
        total_dx = self._float_committed_dx
        total_dy = self._float_committed_dy
        # Restore base-with-hole, then composite float at final position
        layer.pixels[:] = self._float_base
        self._composite_float(layer.pixels, total_dx, total_dy)
        # Translate the selection mask
        if doc is not None and doc.selection.active and (total_dx != 0 or total_dy != 0):
            doc.selection.translate(int(total_dx), int(total_dy))
        self._clear_float()

    def _clear_float(self) -> None:
        self._floating = False
        self._float_pixels = None
        self._float_base = None
        self._float_orig = None
        self._float_dx = 0
        self._float_dy = 0
        self._float_committed_dx = 0
        self._float_committed_dy = 0

    def _composite_float(self, target: np.ndarray, dx: int, dy: int) -> None:
        """Composite floating pixels onto target at offset (dx, dy)."""
        fp = self._float_pixels
        if fp is None:
            return
        h, w = target.shape[:2]
        fh, fw = fp.shape[:2]
        sy0 = max(0, -dy)
        sx0 = max(0, -dx)
        sy1 = min(fh, h - dy)
        sx1 = min(fw, w - dx)
        d_y0 = max(0, dy)
        d_x0 = max(0, dx)
        d_y1 = d_y0 + (sy1 - sy0)
        d_x1 = d_x0 + (sx1 - sx0)
        if sy1 > sy0 and sx1 > sx0:
            src = fp[sy0:sy1, sx0:sx1]
            roi = target[d_y0:d_y1, d_x0:d_x1]
            alpha = src[..., 3:4]
            roi[:] = roi * (1.0 - alpha) + src * alpha
            np.clip(roi, 0, 1, out=roi)

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
    # Hit testing
    # ------------------------------------------------------------------

    @staticmethod
    def _bbox(doc: Document) -> tuple[int, int, int, int] | None:
        """Return (x, y, w, h) bounding box of the active layer in doc coords.

        For groups, the box encompasses all child layers.
        """
        layer = doc.layers.active_layer
        if layer is None:
            return None
        if layer.layer_type == LayerType.GROUP:
            return MoveTool._group_bbox(doc, layer)
        lx, ly = layer.position
        return (lx, ly, layer.width, layer.height)

    @staticmethod
    def _group_bbox(doc: Document, group) -> tuple[int, int, int, int] | None:
        """Compute a bounding box that encompasses all children of *group*."""
        min_x, min_y = float("inf"), float("inf")
        max_x, max_y = float("-inf"), float("-inf")
        found = False
        for child in doc.layers:
            if child.parent_id != group.id:
                continue
            cx, cy = child.position
            min_x = min(min_x, cx)
            min_y = min(min_y, cy)
            max_x = max(max_x, cx + child.width)
            max_y = max(max_y, cy + child.height)
            found = True
        if not found:
            lx, ly = group.position
            return (lx, ly, group.width, group.height)
        return (int(min_x), int(min_y), int(max_x - min_x), int(max_y - min_y))

    def _hit_test(self, doc: Document, x: int, y: int) -> tuple[_Mode, _Handle]:
        layer = doc.layers.active_layer
        if layer is None:
            return _Mode.NONE, _Handle.NONE

        total_angle = layer.transform_angle + self._current_angle

        # When there is accumulated rotation, test against the rotated
        # (original-sized) box by inverse-rotating the click point.
        if total_angle != 0.0 and layer.transform_base_w > 0:
            lx, ly = layer.position
            cx = lx + layer.width / 2
            cy = ly + layer.height / 2
            rad = math.radians(total_angle)
            dx, dy = x - cx, y - cy
            # Inverse of the QPainter rotation applied to the box
            rx = dx * math.cos(rad) - dy * math.sin(rad)
            ry = dx * math.sin(rad) + dy * math.cos(rad)
            return self._hit_test_rect(-layer.transform_base_w / 2,
                                       -layer.transform_base_h / 2,
                                       layer.transform_base_w,
                                       layer.transform_base_h, rx, ry)

        # Normal (no rotation) hit-test on current layer bounds
        bbox = self._bbox(doc)
        if bbox is None:
            return _Mode.NONE, _Handle.NONE
        bx, by, bw, bh = bbox
        return self._hit_test_rect(bx, by, bw, bh, x, y)

    @staticmethod
    def _hit_test_rect(bx: float, by: float, bw: float, bh: float,
                       x: float, y: float) -> tuple[_Mode, _Handle]:
        """Hit-test a point against a rectangle and its handles."""
        m = MoveTool.HANDLE_MARGIN
        mx, my = bx + bw / 2, by + bh / 2

        handles = [
            (_Handle.TL, bx, by),
            (_Handle.T, mx, by),
            (_Handle.TR, bx + bw, by),
            (_Handle.L, bx, my),
            (_Handle.R, bx + bw, my),
            (_Handle.BL, bx, by + bh),
            (_Handle.B, mx, by + bh),
            (_Handle.BR, bx + bw, by + bh),
        ]
        for hid, hx, hy in handles:
            if abs(x - hx) <= m and abs(y - hy) <= m:
                return _Mode.RESIZE, hid

        if bx <= x <= bx + bw and by <= y <= by + bh:
            return _Mode.MOVE, _Handle.NONE

        return _Mode.ROTATE, _Handle.NONE

    # ------------------------------------------------------------------
    # Auto-select helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _point_on_layer(layer, x: int, y: int, alpha_threshold: float = 0.01) -> bool:
        """Return True if (x, y) doc-coords hits a non-transparent pixel on *layer*.

        For text layers the hit-test uses the text bounding box instead of
        alpha, so clicking anywhere inside the text area selects it.
        """
        import math
        lx, ly = layer.position

        # --- Text layers: bounding-box hit-test (including rotation) ---
        if layer.layer_type == LayerType.TEXT:
            td = getattr(layer, "_text_data", None)
            if td is not None:
                angle = layer.transform_angle
                bw, bh = td.box_width, td.box_height
                if angle != 0.0:
                    cx = lx + bw / 2
                    cy = ly + bh / 2
                    rad = math.radians(angle)
                    dx, dy = x - cx, y - cy
                    rx = dx * math.cos(rad) + dy * math.sin(rad)
                    ry = -dx * math.sin(rad) + dy * math.cos(rad)
                    return abs(rx) <= bw / 2 and abs(ry) <= bh / 2
                return lx <= x <= lx + bw and ly <= y <= ly + bh

        # --- Normal alpha hit-test for raster / shape layers ---
        px, py = x - lx, y - ly
        h, w = layer.pixels.shape[:2]
        if px < 0 or px >= w or py < 0 or py >= h:
            return False
        return float(layer.pixels[py, px, 3]) >= alpha_threshold

    @staticmethod
    def _find_layer_at(doc: Document, x: int, y: int,
                       exclude_id: str | None = None,
                       alpha_threshold: float = 0.01) -> int | None:
        """Return the *stack index* of the topmost visible layer hit at (x, y).

        Iterates from top to bottom (highest index first) and returns
        the first layer whose non-transparent pixel is under the cursor.
        Groups and adjustment layers are skipped.
        """
        for i in range(len(doc.layers) - 1, -1, -1):
            layer = doc.layers.layers[i]
            if not layer.visible or layer.locked:
                continue
            if layer.layer_type in (LayerType.GROUP, LayerType.ADJUSTMENT, LayerType.FILTER, LayerType.MASK):
                continue
            if exclude_id is not None and layer.id == exclude_id:
                continue
            if MoveTool._point_on_layer(layer, x, y, alpha_threshold):
                return i
        return None

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        layer = doc.layers.active_layer

        # --- Auto-select: always pick the topmost visible layer at the
        #     click point.  If it differs from the current active layer,
        #     switch to it before doing anything else.  This ensures you
        #     always interact with what you visually click on. -------------
        #     EXCEPTION: if the click lands on a resize/rotate handle of
        #     the active layer's bounding box, skip auto-select so the
        #     user can transform the layer without unwanted switches.
        if self.auto_select:
            skip_autoselect = False
            if layer is not None:
                mode_hit, _ = self._hit_test(doc, x, y)
                if mode_hit == _Mode.RESIZE:
                    skip_autoselect = True

            if not skip_autoselect:
                topmost_idx = self._find_layer_at(doc, x, y)
                if topmost_idx is not None:
                    topmost = doc.layers.layers[topmost_idx]
                    if layer is None or topmost.id != layer.id:
                        doc.layers.active_index = topmost_idx
                        if self.on_layer_auto_selected:
                            self.on_layer_auto_selected(topmost_idx)
                        layer = doc.layers.active_layer

        if layer is None or layer.locked:
            return

        self._mode, self._handle = self._hit_test(doc, x, y)

        # If the click lands in the ROTATE zone (outside the bbox) with
        # auto-select on, only promote to MOVE if the click actually hit
        # the layer's opaque pixels (so dragging empty space / ruler
        # guides doesn't move the layer).
        if self.auto_select and self._mode == _Mode.ROTATE:
            if self._point_on_layer(layer, x, y):
                self._mode = _Mode.MOVE
                self._handle = _Handle.NONE
            else:
                self._mode = _Mode.NONE

        if self._mode == _Mode.NONE:
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

            # If we already have a float in progress, continue dragging it
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
                return  # skip normal setup — we handle everything

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
                if child.parent_id == layer.id:
                    self._group_children.append(child)
                    self._group_child_positions[child.id] = child.position
                    # Non-destructive: snapshot source and record base transforms
                    if child.layer_type not in (LayerType.ADJUSTMENT, LayerType.FILTER):
                        child.init_non_destructive()
                        self._group_child_base_sx[child.id] = child.transform_scale_x
                        self._group_child_base_sy[child.id] = child.transform_scale_y
                        self._group_child_base_angle[child.id] = child.transform_angle
                        self._group_child_dims[child.id] = (child.width, child.height)
            bbox = self._group_bbox(doc, layer)
            self._group_orig_bbox = bbox
            if bbox:
                self._orig_width = bbox[2]
                self._orig_height = bbox[3]
            else:
                self._orig_width = layer.width
                self._orig_height = layer.height
            self._orig_pixels = None  # not used for groups
            return  # skip single-layer setup below

        # -- Single-layer non-destructive setup ----------------------------
        # Initialise ND source (idempotent — only snapshots on first call)
        layer.init_non_destructive()

        # --- Collect mask children so transforms propagate to them ---
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
            # Dimensions for center computation: current display size
            self._orig_width = layer.width
            self._orig_height = layer.height
            # orig_pixels not needed — recompute goes through source

        elif self._mode == _Mode.RESIZE:
            if layer.transform_angle != 0.0 and layer.transform_base_w > 0:
                # Rotated resize: visible unrotated dims from base
                self._is_rotated_resize = True
                self._orig_width = layer.transform_base_w
                self._orig_height = layer.transform_base_h
                self._setup_resize_anchor(layer)
            else:
                # Non-rotated resize: visible dims = current pixel dims
                self._orig_width = layer.width
                self._orig_height = layer.height

        # Record original center (bbox center) for vector transform calculation
        # Must be done for ALL modes so commit knows the pivot
        self._orig_center = (
            layer.position[0] + layer.width / 2.0,
            layer.position[1] + layer.height / 2.0,
        )

    def _setup_resize_anchor(self, layer) -> None:
        """Pre-compute the anchor screen position for a rotated resize."""
        lx, ly = layer.position
        cx = lx + layer.width / 2.0
        cy = ly + layer.height / 2.0
        hw = layer.transform_base_w / 2.0
        hh = layer.transform_base_h / 2.0

        asx, asy = _ANCHOR_SIGN.get(self._handle, (0, 0))
        anchor_lx = asx * hw
        anchor_ly = asy * hh

        rad = math.radians(layer.transform_angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        self._anchor_screen = (
            cx + anchor_lx * cos_a + anchor_ly * sin_a,
            cy - anchor_lx * sin_a + anchor_ly * cos_a,
        )
        self._anchor_sign = (asx, asy)

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
            # Move mask children together with the parent
            for mc in getattr(self, '_mask_children', []):
                mcox, mcoy = self._mask_child_positions[mc.id]
                mc.position = (mcox + dx, mcoy + dy)

        elif self._mode == _Mode.RESIZE:
            if is_group:
                self._apply_group_resize(dx, dy)
            else:
                self._apply_resize(layer, dx, dy)
                # Propagate scale to mask children
                self._sync_mask_transforms(layer)

        elif self._mode == _Mode.ROTATE:
            if is_group:
                self._apply_group_rotate(x, y)
            else:
                self._apply_rotate(layer, x, y)
                # Propagate rotation to mask children
                self._sync_mask_transforms(layer)

    def on_release(self, doc: Document, x: int, y: int) -> None:
        # Floating selection: keep the float alive, just commit the offset
        if self._floating and self._active_layer is not None:
            self._float_committed_dx = self._float_dx
            self._float_committed_dy = self._float_dy
            self._dragging = False
            self._mode = _Mode.NONE
            self._handle = _Handle.NONE
            # Don't clear _active_layer — we need it for re-drags and commit
            return

        if self._mode == _Mode.ROTATE and self._active_layer is not None:
            if self._active_layer.layer_type != LayerType.GROUP:
                # ND system: angle already committed during drag via
                # compute_display; _current_angle is 0 — no-op addition.
                self._active_layer.transform_angle += self._current_angle
                
        # --- Vector Layer Commit ---
        if self._active_layer is not None and self._mode != _Mode.NONE:
            from ..core.enums import LayerType
            if self._active_layer.layer_type == LayerType.SHAPE:
                vl = getattr(self._active_layer, "_vector_data", None)
                if vl:
                    self._commit_vector_transform(doc, self._active_layer, vl)

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

    def _commit_vector_transform(self, doc: Document, layer, vl: object) -> None:
        """Bake the temporary layer transform into the vector objects."""
        from ..vector.geometry import AffineTransform, Vec2
        from ..vector.rasterizer import rasterize_vector_layer_tight, set_auto_rasterize

        mode = self._mode
        
        # 1. Calculate transformation components
        
        # Center translation
        old_cx, old_cy = self._orig_center
        new_cx = layer.position[0] + layer.width / 2.0
        new_cy = layer.position[1] + layer.height / 2.0
        
        # Scale factor
        sx, sy = 1.0, 1.0
        if mode == _Mode.RESIZE:
            if self._is_rotated_resize:
                # Rotated: compare base (unrotated) dimensions
                old_w = self._orig_width
                old_h = self._orig_height
                # Current base dimension = source_dim * scale
                cur_w = layer.transform_scale_x * layer.source_width
                cur_h = layer.transform_scale_y * layer.source_height
                sx = cur_w / max(old_w, 1.0)
                sy = cur_h / max(old_h, 1.0)
            else:
                # Non-rotated: compare visible dimensions
                sx = layer.width / max(self._orig_width, 1.0)
                sy = layer.height / max(self._orig_height, 1.0)

        # Rotation
        angle_deg = 0.0
        if mode == _Mode.ROTATE:
            angle_deg = layer.transform_angle - self._base_angle

        # 2. Build AffineTransform
        # T(-Old) * Scale * Rotate * T(New)
        # Note: MoveTool Rotate keeps center fixed (New == Old), Resize moves center.
        
        xf = AffineTransform.translation(new_cx, new_cy)
        
        if angle_deg != 0.0:
            xf = xf.rotate(math.radians(angle_deg))
            
        if sx != 1.0 or sy != 1.0:
            xf = xf.scale(sx, sy)
            
        xf = xf.translate(-old_cx, -old_cy)

        # 3. Apply to all vector objects
        # We need to treat 'vl' as VectorLayer. It has .objects list.
        # But we accept 'object' because type hints might be loose or circular logic.
        for obj in getattr(vl, "objects", []):
            # Apply xf AFTER obj.transform (obj.transform maps Local->OldWorld, xf maps OldWorld->NewWorld)
            # AffineTransform.concat(other) means self @ other (self after other)
            # So we want xf.concat(obj.transform) -> xf @ obj.transform
            obj.transform = xf.concat(obj.transform)
            obj.invalidate()

        # 4. Reset layer raster transform logic
        # Clear non-destructive source so rasterizer regenerates fresh
        layer._source_pixels = None
        layer._source_mask = None
        layer.transform_scale_x = 1.0
        layer.transform_scale_y = 1.0
        layer.transform_angle = 0.0
        layer.transform_base_w = 0
        layer.transform_base_h = 0
        layer._pixels_dirty = False
        
        # 5. Rasterize at new location
        # Force rasterize to update layer.position/pixels
        rasterize_vector_layer_tight(doc, layer=layer, force=True)



    # ------------------------------------------------------------------
    # Resize
    # ------------------------------------------------------------------

    def _apply_resize(self, layer, dx: int, dy: int) -> None:
        """Non-destructive resize: update scale params and recompute from source."""
        if layer._source_pixels is None:
            return

        angle = layer.transform_angle
        is_rot = self._is_rotated_resize

        # Convert screen delta to the local (box) frame when rotated
        if is_rot:
            rad = math.radians(angle)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)
            ldx = dx * cos_a - dy * sin_a
            ldy = dx * sin_a + dy * cos_a
        else:
            ldx, ldy = float(dx), float(dy)

        ow, oh = self._orig_width, self._orig_height
        new_w: float = float(ow)
        new_h: float = float(oh)

        h = self._handle
        # Horizontal (local frame)
        if h in (_Handle.TL, _Handle.L, _Handle.BL):
            new_w = max(4.0, ow - ldx)
        elif h in (_Handle.TR, _Handle.R, _Handle.BR):
            new_w = max(4.0, ow + ldx)

        # Vertical (local frame)
        if h in (_Handle.TL, _Handle.T, _Handle.TR):
            new_h = max(4.0, oh - ldy)
        elif h in (_Handle.BL, _Handle.B, _Handle.BR):
            new_h = max(4.0, oh + ldy)

        # Compute scale relative to the original source data
        new_sx = new_w / max(layer.source_width, 1)
        new_sy = new_h / max(layer.source_height, 1)

        # Commit scale and recompute display from source
        layer.transform_scale_x = new_sx
        layer.transform_scale_y = new_sy
        layer.compute_display()

        if is_rot:
            # Position via anchor constraint: the anchor must stay fixed
            asx, asy = self._anchor_sign
            new_anchor_lx = asx * (new_w / 2.0)
            new_anchor_ly = asy * (new_h / 2.0)
            new_anchor_sx = new_anchor_lx * cos_a + new_anchor_ly * sin_a
            new_anchor_sy = -new_anchor_lx * sin_a + new_anchor_ly * cos_a

            new_cx = self._anchor_screen[0] - new_anchor_sx
            new_cy = self._anchor_screen[1] - new_anchor_sy

            layer.position = (int(new_cx - layer.width / 2),
                              int(new_cy - layer.height / 2))
        else:
            # Non-rotated: classic top-left positioning
            ox, oy = self._orig_position
            new_x, new_y = float(ox), float(oy)

            if h in (_Handle.TL, _Handle.L, _Handle.BL):
                new_x = ox + (ow - new_w)
            if h in (_Handle.TL, _Handle.T, _Handle.TR):
                new_y = oy + (oh - new_h)

            layer.position = (int(new_x), int(new_y))

    # ------------------------------------------------------------------
    # Rotate (single layer)
    # ------------------------------------------------------------------

    def _apply_rotate(self, layer, x: int, y: int) -> None:
        """Non-destructive rotate: update angle and recompute from source."""
        if layer._source_pixels is None:
            return

        ox, oy = self._orig_position
        ow, oh = self._orig_width, self._orig_height
        cx = ox + ow / 2
        cy = oy + oh / 2

        a0 = math.atan2(self._start_y - cy, self._start_x - cx)
        a1 = math.atan2(y - cy, x - cx)
        # Negate: screen coords are y-down, so atan2 gives the
        # opposite sign from the visual rotation direction.
        delta_deg = -math.degrees(a1 - a0)

        # Total angle = committed base + current drag delta
        total_angle = self._base_angle + delta_deg

        # Commit angle and recompute display from source
        layer.transform_angle = total_angle
        layer.compute_display()

        # Reposition so the center stays fixed
        layer.position = (int(cx - layer.width / 2),
                          int(cy - layer.height / 2))

        # _current_angle = 0 because the angle is already committed
        # on the layer.  rotation_info_for / _hit_test read
        # layer.transform_angle directly.
        self._current_angle = 0.0

    # ------------------------------------------------------------------
    # Sync mask children transforms
    # ------------------------------------------------------------------

    def _sync_mask_transforms(self, parent) -> None:
        """Propagate the parent layer's scale and angle to its mask children.

        Each mask child mirrors the parent's transform so it always
        aligns with the parent's visual output.
        """
        for mc in getattr(self, '_mask_children', []):
            if mc._source_pixels is None:
                continue
            mc.transform_scale_x = parent.transform_scale_x
            mc.transform_scale_y = parent.transform_scale_y
            mc.transform_angle = parent.transform_angle
            mc.compute_display()
            # Keep the mask co-located with the parent
            mc.position = parent.position

    # ------------------------------------------------------------------
    # Group resize
    # ------------------------------------------------------------------

    def _apply_group_resize(self, dx: int, dy: int) -> None:
        """Non-destructive group resize: update child scale params and recompute."""
        bbox = self._group_orig_bbox
        if bbox is None:
            return

        bx, by, bw, bh = bbox
        ow, oh = float(bw), float(bh)
        ldx, ldy = float(dx), float(dy)

        new_w, new_h = ow, oh
        h = self._handle

        if h in (_Handle.TL, _Handle.L, _Handle.BL):
            new_w = max(4.0, ow - ldx)
        elif h in (_Handle.TR, _Handle.R, _Handle.BR):
            new_w = max(4.0, ow + ldx)

        if h in (_Handle.TL, _Handle.T, _Handle.TR):
            new_h = max(4.0, oh - ldy)
        elif h in (_Handle.BL, _Handle.B, _Handle.BR):
            new_h = max(4.0, oh + ldy)

        sx = new_w / max(ow, 1)
        sy = new_h / max(oh, 1)

        # New bbox origin shifts when resizing from top/left handles
        new_bx, new_by = float(bx), float(by)
        if h in (_Handle.TL, _Handle.L, _Handle.BL):
            new_bx = bx + (ow - new_w)
        if h in (_Handle.TL, _Handle.T, _Handle.TR):
            new_by = by + (oh - new_h)

        for child in self._group_children:
            if child.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER):
                continue
            if child._source_pixels is None:
                continue

            base_sx = self._group_child_base_sx[child.id]
            base_sy = self._group_child_base_sy[child.id]

            child.transform_scale_x = base_sx * sx
            child.transform_scale_y = base_sy * sy
            child.compute_display()

            orig_cx, orig_cy = self._group_child_positions[child.id]
            rel_x = orig_cx - bx
            rel_y = orig_cy - by
            child.position = (int(new_bx + rel_x * sx), int(new_by + rel_y * sy))

    # ------------------------------------------------------------------
    # Group rotate
    # ------------------------------------------------------------------

    def _apply_group_rotate(self, x: int, y: int) -> None:
        """Non-destructive group rotate: update child angle and recompute."""
        bbox = self._group_orig_bbox
        if bbox is None:
            return

        bx, by, bw, bh = bbox
        gcx = bx + bw / 2.0
        gcy = by + bh / 2.0

        a0 = math.atan2(self._start_y - gcy, self._start_x - gcx)
        a1 = math.atan2(y - gcy, x - gcx)
        angle_deg = -math.degrees(a1 - a0)
        self._current_angle = angle_deg

        rad = math.radians(angle_deg)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)

        for child in self._group_children:
            if child.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER):
                continue
            if child._source_pixels is None:
                continue

            base_angle = self._group_child_base_angle[child.id]
            child.transform_angle = base_angle + angle_deg
            child.compute_display()

            # Rotate child center around the group center
            orig_cx, orig_cy = self._group_child_positions[child.id]
            orig_cw, orig_ch = self._group_child_dims[child.id]

            child_mid_x = orig_cx + orig_cw / 2.0
            child_mid_y = orig_cy + orig_ch / 2.0
            dx_c = child_mid_x - gcx
            dy_c = child_mid_y - gcy
            new_dx = dx_c * cos_a + dy_c * sin_a
            new_dy = -dx_c * sin_a + dy_c * cos_a

            child.position = (
                int(gcx + new_dx - child.width / 2),
                int(gcy + new_dy - child.height / 2),
            )

    # ------------------------------------------------------------------
    # Alignment helpers (relative to canvas)
    # ------------------------------------------------------------------

    @staticmethod
    def align_left(doc: Document) -> None:
        """Align active layer's left edge to the canvas left edge."""
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return
        doc.save_snapshot("Align Left")
        _, ly = layer.position
        layer.position = (0, ly)

    @staticmethod
    def align_center_h(doc: Document) -> None:
        """Horizontally centre the active layer on the canvas."""
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return
        doc.save_snapshot("Align Center H")
        _, ly = layer.position
        layer.position = ((doc.width - layer.width) // 2, ly)

    @staticmethod
    def align_right(doc: Document) -> None:
        """Align active layer's right edge to the canvas right edge."""
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return
        doc.save_snapshot("Align Right")
        _, ly = layer.position
        layer.position = (doc.width - layer.width, ly)

    @staticmethod
    def align_top(doc: Document) -> None:
        """Align active layer's top edge to the canvas top edge."""
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return
        doc.save_snapshot("Align Top")
        lx, _ = layer.position
        layer.position = (lx, 0)

    @staticmethod
    def align_middle_v(doc: Document) -> None:
        """Vertically centre the active layer on the canvas."""
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return
        doc.save_snapshot("Align Middle V")
        lx, _ = layer.position
        layer.position = (lx, (doc.height - layer.height) // 2)

    @staticmethod
    def align_bottom(doc: Document) -> None:
        """Align active layer's bottom edge to the canvas bottom edge."""
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return
        doc.save_snapshot("Align Bottom")
        lx, _ = layer.position
        layer.position = (lx, doc.height - layer.height)

    # ------------------------------------------------------------------
    # Flip / Rotate helpers
    # ------------------------------------------------------------------

    @staticmethod
    def flip_horizontal(doc: Document) -> None:
        """Flip the active layer horizontally."""
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return
        doc.save_snapshot("Flip Horizontal")
        layer.pixels = TransformEngine.flip_h(layer.pixels)

    @staticmethod
    def flip_vertical(doc: Document) -> None:
        """Flip the active layer vertically."""
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return
        doc.save_snapshot("Flip Vertical")
        layer.pixels = TransformEngine.flip_v(layer.pixels)

    @staticmethod
    def rotate_90_cw(doc: Document) -> None:
        """Rotate the active layer 90° clockwise, keeping the centre in place."""
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return
        doc.save_snapshot("Rotate 90° CW")
        px, py = layer.position
        old_w, old_h = layer.width, layer.height
        layer.pixels = TransformEngine.rotate(layer.pixels, -90, expand=True)
        new_w, new_h = layer.width, layer.height
        # Adjust position so the layer centre stays at the same spot
        layer.position = (px + (old_w - new_w) // 2, py + (old_h - new_h) // 2)

    @staticmethod
    def rotate_90_ccw(doc: Document) -> None:
        """Rotate the active layer 90° counter-clockwise, keeping the centre in place."""
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return
        doc.save_snapshot("Rotate 90° CCW")
        px, py = layer.position
        old_w, old_h = layer.width, layer.height
        layer.pixels = TransformEngine.rotate(layer.pixels, 90, expand=True)
        new_w, new_h = layer.width, layer.height
        layer.position = (px + (old_w - new_w) // 2, py + (old_h - new_h) // 2)
