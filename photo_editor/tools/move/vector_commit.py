"""Vector-layer transform commit helpers for the Move tool.

When the user finishes transforming a vector (SHAPE) layer the
non-destructive layer transform (scale / rotate stored on the layer) must
be *baked* back into the underlying vector objects so the layer is clean
(``transform_scale = 1, transform_angle = 0``) after the operation.  The
layer is then re-rasterized from the updated vector data.

This module handles three cases:

1. A single ``SHAPE`` layer  (``VectorCommitMixin._commit_vector_transform``).
2. A ``GROUP`` layer whose children include ``SHAPE`` layers
   (``VectorCommitMixin._commit_group_vector_transforms``).
3. Nested groups, handled recursively via
   ``VectorCommitMixin._bake_transform_into_descendants``.

Exported symbol
---------------
VectorCommitMixin
    Mixin class containing the three commit methods listed above.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ._enums import _Mode
from ...core.enums import LayerType

if TYPE_CHECKING:
    from ...core.document import Document


class VectorCommitMixin:
    """Mixin that bakes non-destructive layer transforms into vector objects.

    Attribute contract (must be initialised by the host ``__init__``)::

        _mode: _Mode
        _orig_center: tuple[float, float]
        _orig_width: int
        _orig_height: int
        _is_rotated_resize: bool
        _base_angle: float
        _group_children: list
        _group_child_positions: dict
        _group_child_base_sx: dict
        _group_child_base_sy: dict
        _group_child_base_angle: dict
        _group_child_dims: dict
    """

    # ------------------------------------------------------------------
    # Single SHAPE layer
    # ------------------------------------------------------------------

    def _commit_vector_transform(
        self, doc: "Document", layer, vl: object
    ) -> None:
        """Bake the temporary layer transform into all vector objects on *layer*.

        Steps
        -----
        1. Derive translation, scale, and rotation from the layer state.
        2. Build a combined ``AffineTransform``:
           ``T(new_center) · R(delta) · S(sx,sy) · T(-old_center)``.
        3. Apply it to every ``VectorObject`` in *vl*.
        4. Reset the layer's non-destructive transform fields to identity.
        5. Re-rasterize the layer from the updated vector data.
        """
        from ...vector.geometry import AffineTransform
        from ...vector.rasterizer import rasterize_vector_layer_tight

        mode = self._mode

        # 1. Translation: old centre → new centre
        old_cx, old_cy = self._orig_center
        new_cx = layer.position[0] + layer.width / 2.0
        new_cy = layer.position[1] + layer.height / 2.0

        # 1b. Scale factor
        sx, sy = 1.0, 1.0
        if mode == _Mode.RESIZE:
            if self._is_rotated_resize:
                old_w = self._orig_width
                old_h = self._orig_height
                cur_w = layer.transform_scale_x * layer.source_width
                cur_h = layer.transform_scale_y * layer.source_height
                sx = cur_w / max(old_w, 1.0)
                sy = cur_h / max(old_h, 1.0)
            else:
                sx = layer.width / max(self._orig_width, 1.0)
                sy = layer.height / max(self._orig_height, 1.0)

        # 1c. Rotation delta
        angle_deg = 0.0
        if mode == _Mode.ROTATE:
            angle_deg = layer.transform_angle - self._base_angle

        # 2. Build combined affine transform:
        #    T(new_center) · R(angle) · S(sx, sy) · T(-old_center)
        #
        # NOTE: layer.transform_angle follows the cv2 convention where positive
        # angle means counter-clockwise rotation visually (y-down screen space).
        # AffineTransform.rotation uses the opposite sign convention (positive =
        # clockwise in y-down screen space), so the angle must be negated here.
        xf = AffineTransform.translation(new_cx, new_cy)
        if angle_deg != 0.0:
            xf = xf.rotate(-math.radians(angle_deg))
        if sx != 1.0 or sy != 1.0:
            xf = xf.scale(sx, sy)
        xf = xf.translate(-old_cx, -old_cy)

        # 3. Apply to all vector objects
        for obj in getattr(vl, "objects", []):
            obj.transform = xf.concat(obj.transform)
            obj.invalidate()

        # 4. Reset non-destructive transform to identity
        layer._source_pixels = None
        layer._source_mask = None
        layer.transform_scale_x = 1.0
        layer.transform_scale_y = 1.0
        layer.transform_angle = 0.0
        layer.transform_base_w = 0
        layer.transform_base_h = 0
        layer._pixels_dirty = False

        # 5. Re-rasterize
        rasterize_vector_layer_tight(doc, layer=layer, force=True)

    # ------------------------------------------------------------------
    # GROUP layer
    # ------------------------------------------------------------------

    def _commit_group_vector_transforms(self, doc: "Document") -> None:
        """Bake group move/resize/rotate into all SHAPE children and sub-groups.

        For each SHAPE child the transform delta is computed relative to
        the child's base state (captured at drag-start) and baked into
        its vector objects.  Nested GROUP children are handled
        recursively via ``_bake_transform_into_descendants``.
        """
        from ...vector.geometry import AffineTransform
        from ...vector.rasterizer import rasterize_vector_layer_tight

        # --- SHAPE direct children ---
        for child in self._group_children:
            if child.layer_type != LayerType.SHAPE:
                continue
            vl = getattr(child, "_vector_data", None)
            if vl is None:
                continue

            orig_pos = self._group_child_positions.get(child.id)
            if orig_pos is None:
                continue

            base_sx = self._group_child_base_sx.get(child.id, 1.0)
            base_sy = self._group_child_base_sy.get(child.id, 1.0)
            base_angle = self._group_child_base_angle.get(child.id, 0.0)
            orig_dims = self._group_child_dims.get(child.id, (child.width, child.height))
            orig_w, orig_h = orig_dims

            orig_cx = orig_pos[0] + orig_w / 2.0
            orig_cy = orig_pos[1] + orig_h / 2.0
            new_cx = child.position[0] + child.width / 2.0
            new_cy = child.position[1] + child.height / 2.0

            xf = AffineTransform.translation(new_cx, new_cy)

            angle_deg = child.transform_angle - base_angle
            if angle_deg != 0.0:
                # Negate: layer.transform_angle uses cv2 sign convention
                # (positive = CCW visually); AffineTransform uses opposite.
                xf = xf.rotate(-math.radians(angle_deg))

            sx = child.transform_scale_x / max(base_sx, 1e-6)
            sy = child.transform_scale_y / max(base_sy, 1e-6)
            if sx != 1.0 or sy != 1.0:
                xf = xf.scale(sx, sy)

            xf = xf.translate(-orig_cx, -orig_cy)

            for obj in getattr(vl, "objects", []):
                obj.transform = xf.concat(obj.transform)
                obj.invalidate()

            # Reset ND transform to identity
            child._source_pixels = None
            child._source_mask = None
            child.transform_scale_x = 1.0
            child.transform_scale_y = 1.0
            child.transform_angle = 0.0
            child.transform_base_w = 0
            child.transform_base_h = 0
            child._pixels_dirty = False

            rasterize_vector_layer_tight(doc, layer=child, force=True)

        # --- GROUP direct children (recursive) ---
        for child in self._group_children:
            if child.layer_type != LayerType.GROUP:
                continue
            orig_pos = self._group_child_positions.get(child.id)
            if orig_pos is None:
                continue
            base_sx = self._group_child_base_sx.get(child.id, 1.0)
            base_sy = self._group_child_base_sy.get(child.id, 1.0)
            base_angle = self._group_child_base_angle.get(child.id, 0.0)
            orig_dims = self._group_child_dims.get(child.id, (child.width, child.height))
            orig_w, orig_h = orig_dims
            orig_cx = orig_pos[0] + orig_w / 2.0
            orig_cy = orig_pos[1] + orig_h / 2.0
            new_cx = child.position[0] + child.width / 2.0
            new_cy = child.position[1] + child.height / 2.0

            xf = AffineTransform.translation(new_cx, new_cy)
            angle_deg = child.transform_angle - base_angle
            if angle_deg != 0.0:
                # Negate to match cv2 sign convention used by transform_angle.
                xf = xf.rotate(-math.radians(angle_deg))
            sx = child.transform_scale_x / max(base_sx, 1e-6)
            sy = child.transform_scale_y / max(base_sy, 1e-6)
            if sx != 1.0 or sy != 1.0:
                xf = xf.scale(sx, sy)
            xf = xf.translate(-orig_cx, -orig_cy)

            self._bake_transform_into_descendants(doc, child, xf, sx, sy)

            child._source_pixels = None
            child._source_mask = None
            child.transform_scale_x = 1.0
            child.transform_scale_y = 1.0
            child.transform_angle = 0.0
            child.transform_base_w = 0
            child.transform_base_h = 0
            child._pixels_dirty = False

    # ------------------------------------------------------------------
    # Recursive descendant baking
    # ------------------------------------------------------------------

    def _bake_transform_into_descendants(
        self,
        doc: "Document",
        group: object,
        xf: object,
        sx: float = 1.0,
        sy: float = 1.0,
    ) -> None:
        """Recursively apply *xf* to every descendant of *group*.

        For SHAPE layers the transform is baked into vector objects.
        For raster layers the ND scale is multiplied in and display is
        recomputed.  Nested groups are traversed recursively.
        """
        from ...vector.geometry import Vec2
        from ...vector.rasterizer import rasterize_vector_layer_tight

        for layer in doc.layers:
            if layer.parent_id != group.id:
                continue
            if layer.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER, LayerType.MASK):
                continue

            # Update position of every child to follow the transform
            lx, ly = layer.position
            new_pt = xf.apply(Vec2(float(lx), float(ly)))
            layer.position = (int(new_pt.x), int(new_pt.y))

            if layer.layer_type == LayerType.GROUP:
                self._bake_transform_into_descendants(doc, layer, xf, sx, sy)

            elif layer.layer_type == LayerType.SHAPE:
                vl = getattr(layer, "_vector_data", None)
                if vl is not None:
                    for obj in getattr(vl, "objects", []):
                        obj.transform = xf.concat(obj.transform)
                        obj.invalidate()
                layer._source_pixels = None
                layer._source_mask = None
                layer.transform_scale_x = 1.0
                layer.transform_scale_y = 1.0
                layer.transform_angle = 0.0
                layer.transform_base_w = 0
                layer.transform_base_h = 0
                layer._pixels_dirty = False
                rasterize_vector_layer_tight(doc, layer=layer, force=True)

            else:
                # Raster layer: scale the ND transform and recompute
                if getattr(layer, "_source_pixels", None) is not None:
                    layer.transform_scale_x *= sx
                    layer.transform_scale_y *= sy
                    layer.compute_display(fast=True)
                layer.rasterize_transform()
