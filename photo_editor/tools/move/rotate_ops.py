"""Non-destructive rotate helpers for the Move tool.

All rotate operations modify ``layer.transform_angle`` and recompute
display pixels from the stored source, so quality is never degraded by
repeated rotations (Affinity-style).

Exported symbol
---------------
RotateMixin
    Mixin class providing:

    ``_apply_rotate(layer, x, y)``
        Single-layer non-destructive rotation.  The layer centre is kept
        fixed; only the angle changes.

    ``_apply_group_rotate(x, y)``
        Group rotation: every child is rotated around the group-bbox
        centre by the same delta angle.

    ``_sync_mask_transforms(parent)``
        Propagate the parent layer's current scale and angle to all its
        mask children so they remain aligned with the parent.
"""

from __future__ import annotations

import math

from ...core.enums import LayerType


class RotateMixin:
    """Mixin that implements rotate (and mask-sync) operations for the Move tool.

    Attribute contract (must be initialised by the host ``__init__``)::

        _start_x: int
        _start_y: int
        _orig_position: tuple[int, int]
        _orig_width: int
        _orig_height: int
        _base_angle: float
        _current_angle: float
        _group_orig_bbox: tuple[int, int, int, int] | None
        _group_children: list
        _group_child_positions: dict
        _group_child_base_angle: dict
        _group_child_dims: dict
    """

    # ------------------------------------------------------------------
    # Single-layer rotate
    # ------------------------------------------------------------------

    def _apply_rotate(self, layer, x: int, y: int, *, preview_only: bool = False) -> None:
        """Non-destructive rotate: update angle and recompute display from source.

        The layer centre is kept stationary; the position is adjusted
        after every call so the expanded bounding box is always centred
        on the same point.
        """
        if layer._source_pixels is None:
            return

        ox, oy = self._orig_position
        ow, oh = self._orig_width, self._orig_height
        cx = ox + ow / 2
        cy = oy + oh / 2

        a0 = math.atan2(self._start_y - cy, self._start_x - cx)
        a1 = math.atan2(y - cy, x - cx)
        # Negate because screen coords are y-down (atan2 gives the
        # opposite sign from the visual rotation direction).
        delta_deg = -math.degrees(a1 - a0)

        # Total angle = angle at drag start + delta this drag
        total_angle = self._base_angle + delta_deg

        if preview_only:
            self._preview_angle = total_angle
            self._preview_center = (cx, cy)
            self._current_angle = 0.0
        else:
            layer.transform_angle = total_angle
            layer.compute_display(fast=True)

            # Reposition so the visual centre stays fixed
            layer.position = (int(cx - layer.width / 2),
                              int(cy - layer.height / 2))

            # The angle is already committed to the layer, so the mid-drag
            # accumulator stays at 0.  rotation_info_for / hit_test both
            # read layer.transform_angle directly.
            self._current_angle = 0.0

    # ------------------------------------------------------------------
    # Group rotate
    # ------------------------------------------------------------------

    def _apply_group_rotate(self, x: int, y: int, *, preview_only: bool = False) -> None:
        """Non-destructive group rotate: rotate every child around the group centre."""
        bbox = self._group_orig_bbox
        if bbox is None:
            return

        bx, by, bw, bh = bbox
        gcx = bx + bw / 2.0
        gcy = by + bh / 2.0

        a0 = math.atan2(self._start_y - gcy, self._start_x - gcx)
        a1 = math.atan2(y - gcy, x - gcx)
        angle_deg = -math.degrees(a1 - a0)
        # The full angle is committed to each child's transform_angle below,
        # so the mid-drag accumulator must stay at 0 — same as _apply_rotate.
        # Otherwise rotation_info_for() double-counts the delta (BB at 2×).
        self._current_angle = 0.0

        if preview_only:
            self._group_preview_angle = angle_deg
            self._group_preview_center = (gcx, gcy)
        else:
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
                child.compute_display(fast=True)

                # Rotate child centre around the group centre
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
    # Multi-selection rotate (virtual group)
    # ------------------------------------------------------------------

    def _apply_multi_rotate(self, x: int, y: int, *, preview_only: bool = False) -> None:
        """Non-destructive multi-layer rotate: rotate every selected layer
        around their combined bounding-box centre — same as group rotate."""
        bbox = getattr(self, "_multi_orig_bbox", None)
        if bbox is None:
            return

        bx, by, bw, bh = bbox
        gcx = bx + bw / 2.0
        gcy = by + bh / 2.0

        a0 = math.atan2(self._start_y - gcy, self._start_x - gcx)
        a1 = math.atan2(y - gcy, x - gcx)
        angle_deg = -math.degrees(a1 - a0)
        self._current_angle = 0.0

        if preview_only:
            self._group_preview_angle = angle_deg
            self._group_preview_center = (gcx, gcy)
        else:
            rad = math.radians(angle_deg)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)

            for child in getattr(self, "_multi_layers", []):
                if child.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER):
                    continue
                if child._source_pixels is None:
                    continue

                multi_base_angle = getattr(self, "_multi_base_angle", {})
                multi_dims = getattr(self, "_multi_dims", {})
                multi_positions = getattr(self, "_multi_positions", {})

                base_angle = multi_base_angle.get(child.id, 0.0)
                child.transform_angle = base_angle + angle_deg
                child.compute_display(fast=True)

                orig_cx, orig_cy = multi_positions[child.id]
                orig_cw, orig_ch = multi_dims[child.id]

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
    # Mask-children sync
    # ------------------------------------------------------------------

    def _sync_mask_transforms(self, parent, *, preview_only: bool = False) -> None:
        """Mirror the parent layer's scale / angle onto all its mask children.

        Each mask child tracks the parent transform so it always aligns
        with the parent's rendered output.
        """
        if preview_only:
            return
        for mc in getattr(self, "_mask_children", []):
            if mc._source_pixels is None:
                continue
            mc.transform_scale_x = parent.transform_scale_x
            mc.transform_scale_y = parent.transform_scale_y
            mc.transform_angle = parent.transform_angle
            mc.compute_display(fast=True)
            # Keep the mask co-located with the parent
            mc.position = parent.position
