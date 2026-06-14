"""Non-destructive resize helpers for the Move tool.

All resize operations modify the layer's ``transform_scale_x/y``
parameters and recompute display pixels from the stored source, so
quality is never degraded by repeated resizes (Affinity-style).

Exported symbol
---------------
ResizeMixin
    Mixin class providing:

    ``_setup_resize_anchor(layer)``
        Pre-compute and cache the screen position of the anchor corner
        (opposite the drag handle) for a rotated resize operation.

    ``_apply_resize(layer, dx, dy)``
        Single-layer non-destructive resize.

    ``_apply_group_resize(dx, dy)``
        Group non-destructive resize (scales each child relative to the
        group bounding box).
"""

from __future__ import annotations

import math

from ._enums import _Handle, _ANCHOR_SIGN
from ...core.enums import LayerType


class ResizeMixin:
    """Mixin that implements resize operations for the Move tool.

    Attribute contract (must be initialised by the host ``__init__``)::

        _handle: _Handle
        _orig_position: tuple[int, int]
        _orig_width: int
        _orig_height: int
        _is_rotated_resize: bool
        _anchor_screen: tuple[float, float]
        _anchor_sign: tuple[int, int]
        _group_orig_bbox: tuple[int, int, int, int] | None
        _group_children: list
        _group_child_positions: dict
        _group_child_base_sx: dict
        _group_child_base_sy: dict
    """

    # ------------------------------------------------------------------
    # Anchor pre-computation (for rotated resize)
    # ------------------------------------------------------------------

    def _setup_resize_anchor(self, layer) -> None:
        """Pre-compute the anchor screen position for a rotated resize.

        The anchor is the corner/edge *opposite* to the drag handle and
        must not move during the resize.  Its screen position is stored
        in ``self._anchor_screen`` so it can be used each frame in
        ``_apply_resize``.
        """
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

    # ------------------------------------------------------------------
    # Single-layer resize
    # ------------------------------------------------------------------

    def _apply_resize(self, layer, dx: int, dy: int, *, preview_only: bool = False) -> None:
        """Non-destructive resize: update scale params and recompute from source."""
        if layer._source_pixels is None:
            return

        angle = layer.transform_angle
        is_rot = self._is_rotated_resize

        # Convert screen delta to the box-local frame when the layer is rotated
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

        # Compute scale relative to the original source dimensions
        new_sx = new_w / max(layer.source_width, 1)
        new_sy = new_h / max(layer.source_height, 1)

        if preview_only:
            self._preview_scale_x = new_sx
            self._preview_scale_y = new_sy
            self._preview_w = int(round(new_w))
            self._preview_h = int(round(new_h))
            if is_rot:
                asx, asy = self._anchor_sign
                cos_a = math.cos(math.radians(angle))
                sin_a = math.sin(math.radians(angle))
                new_anchor_lx = asx * (new_w / 2.0)
                new_anchor_ly = asy * (new_h / 2.0)
                new_anchor_sx = new_anchor_lx * cos_a + new_anchor_ly * sin_a
                new_anchor_sy = -new_anchor_lx * sin_a + new_anchor_ly * cos_a
                new_cx = self._anchor_screen[0] - new_anchor_sx
                new_cy = self._anchor_screen[1] - new_anchor_sy
                self._preview_center = (new_cx, new_cy)
                self._preview_position = (int(new_cx - new_w / 2), int(new_cy - new_h / 2))
            else:
                ox, oy = self._orig_position
                new_x, new_y = float(ox), float(oy)
                if h in (_Handle.TL, _Handle.L, _Handle.BL):
                    new_x = ox + (ow - new_w)
                if h in (_Handle.TL, _Handle.T, _Handle.TR):
                    new_y = oy + (oh - new_h)
                self._preview_center = (new_x + new_w / 2.0, new_y + new_h / 2.0)
                self._preview_position = (int(new_x), int(new_y))
        else:
            layer.transform_scale_x = new_sx
            layer.transform_scale_y = new_sy
            layer.compute_display(fast=True)

            if is_rot:
                asx, asy = self._anchor_sign
                cos_a = math.cos(math.radians(angle))
                sin_a = math.sin(math.radians(angle))
                new_anchor_lx = asx * (new_w / 2.0)
                new_anchor_ly = asy * (new_h / 2.0)
                new_anchor_sx = new_anchor_lx * cos_a + new_anchor_ly * sin_a
                new_anchor_sy = -new_anchor_lx * sin_a + new_anchor_ly * cos_a

                new_cx = self._anchor_screen[0] - new_anchor_sx
                new_cy = self._anchor_screen[1] - new_anchor_sy

                layer.position = (int(new_cx - layer.width / 2),
                                  int(new_cy - layer.height / 2))
            else:
                ox, oy = self._orig_position
                new_x, new_y = float(ox), float(oy)
                if h in (_Handle.TL, _Handle.L, _Handle.BL):
                    new_x = ox + (ow - new_w)
                if h in (_Handle.TL, _Handle.T, _Handle.TR):
                    new_y = oy + (oh - new_h)
                layer.position = (int(new_x), int(new_y))

    # ------------------------------------------------------------------
    # Group resize
    # ------------------------------------------------------------------

    def _apply_group_resize(self, dx: int, dy: int, *, preview_only: bool = False) -> None:
        """Non-destructive group resize: scale each child relative to the group bbox."""
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

        # Bbox origin shifts when resizing from top/left handles
        new_bx, new_by = float(bx), float(by)
        if h in (_Handle.TL, _Handle.L, _Handle.BL):
            new_bx = bx + (ow - new_w)
        if h in (_Handle.TL, _Handle.T, _Handle.TR):
            new_by = by + (oh - new_h)

        if preview_only:
            self._group_preview_sx = sx
            self._group_preview_sy = sy
            self._group_preview_center = (new_bx + new_w / 2.0, new_by + new_h / 2.0)
        else:
            for child in self._group_children:
                if child.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER):
                    continue
                if child._source_pixels is None:
                    continue

                base_sx = self._group_child_base_sx[child.id]
                base_sy = self._group_child_base_sy[child.id]

                child.transform_scale_x = base_sx * sx
                child.transform_scale_y = base_sy * sy
                child.compute_display(fast=True)

                orig_cx, orig_cy = self._group_child_positions[child.id]
                rel_x = orig_cx - bx
                rel_y = orig_cy - by
                child.position = (int(new_bx + rel_x * sx), int(new_by + rel_y * sy))

    # ------------------------------------------------------------------
    # Multi-selection resize (virtual group)
    # ------------------------------------------------------------------

    def _apply_multi_resize(self, dx: int, dy: int, *, preview_only: bool = False) -> None:
        """Non-destructive multi-layer resize: scale each selected layer
        relative to their combined bounding box — same as group resize."""
        bbox = getattr(self, "_multi_orig_bbox", None)
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

        new_bx, new_by = float(bx), float(by)
        if h in (_Handle.TL, _Handle.L, _Handle.BL):
            new_bx = bx + (ow - new_w)
        if h in (_Handle.TL, _Handle.T, _Handle.TR):
            new_by = by + (oh - new_h)

        if preview_only:
            self._group_preview_sx = sx
            self._group_preview_sy = sy
            self._group_preview_center = (new_bx + new_w / 2.0, new_by + new_h / 2.0)
        else:
            for child in getattr(self, "_multi_layers", []):
                if child.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER):
                    continue
                if child._source_pixels is None:
                    continue

                base_sx = getattr(self, "_multi_base_sx", {}).get(child.id, 1.0)
                base_sy = getattr(self, "_multi_base_sy", {}).get(child.id, 1.0)

                child.transform_scale_x = base_sx * sx
                child.transform_scale_y = base_sy * sy
                child.compute_display(fast=True)

                orig_cx, orig_cy = self._multi_positions[child.id]
                rel_x = orig_cx - bx
                rel_y = orig_cy - by
                child.position = (int(new_bx + rel_x * sx), int(new_by + rel_y * sy))
