"""Resize (scale) layer command — non-destructive."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ..base import Command

if TYPE_CHECKING:
    from ...core.document import Document


class ResizeLayerCommand(Command):
    """Scale a layer around a pivot point.

    For raster layers, this updates non-destructive transform scale
    parameters and repositions so the pivot stays fixed.
    For vector/shape layers, the objects are transformed directly.

    Parameters
    ----------
    layer_id : str
        ID of the layer to resize.
    new_w : float
        Target width in pixels.
    new_h : float
        Target height in pixels.
    pivot : tuple[float, float]
        The (x, y) anchor point around which scaling occurs.
    """

    def __init__(
        self,
        layer_id: str,
        new_w: float,
        new_h: float,
        pivot: tuple[float, float],
    ) -> None:
        self.layer_id = layer_id
        self.new_w = new_w
        self.new_h = new_h
        self.pivot = pivot

    def execute(self, document: Document) -> None:
        from ...core.enums import LayerType

        layer = document.layers.get(self.layer_id)
        if layer is None or layer.locked:
            return
        before = document.layer_visual_bounds(layer.id)

        lx, ly = layer.position
        lw, lh = layer.width, layer.height
        pivot_x, pivot_y = self.pivot

        if layer.layer_type == LayerType.RASTER:
            # Non-destructive scale
            sx = self.new_w / max(layer.source_width, 1)
            sy = self.new_h / max(layer.source_height, 1)
            layer.transform_scale_x = sx
            layer.transform_scale_y = sy

            # Reposition so the pivot stays fixed
            scale_factor_x = self.new_w / lw if lw > 0 else 1
            scale_factor_y = self.new_h / lh if lh > 0 else 1

            new_lx = pivot_x + (lx - pivot_x) * scale_factor_x
            new_ly = pivot_y + (ly - pivot_y) * scale_factor_y

            layer.position = (int(new_lx), int(new_ly))
            layer.compute_display()

        elif layer.layer_type == LayerType.SHAPE:
            scale_x = self.new_w / lw if lw > 0 else 1
            scale_y = self.new_h / lh if lh > 0 else 1
            self._scale_vector_layer(document, layer, scale_x, scale_y,
                                     pivot_x, pivot_y)

        document.mark_region_pair_dirty(before, document.layer_visual_bounds(layer.id))

        # NOTE: snapshot / mark_dirty are the caller's responsibility so
        # that interactive use (e.g. drag-resize) doesn't pay the cost of
        # deep-copying all layer data on every frame.

    # -- vector helpers -------------------------------------------------------

    @staticmethod
    def _scale_vector_layer(document, layer, sx, sy, cx, cy) -> None:
        from ...vector.geometry import AffineTransform

        vl = getattr(layer, "_vector_data", None)
        if not vl:
            return

        xf = (
            AffineTransform.translation(cx, cy)
            .concat(AffineTransform.scaling(sx, sy))
            .concat(AffineTransform.translation(-cx, -cy))
        )

        for obj in vl.objects:
            obj.transform = xf.concat(obj.transform)
            obj.invalidate()

        from ...vector.rasterizer import rasterize_vector_layer_tight
        layer._pixels_dirty = True
        rasterize_vector_layer_tight(document, layer=layer, force=True)
