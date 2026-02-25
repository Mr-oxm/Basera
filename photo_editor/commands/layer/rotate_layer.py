"""Rotate layer command — non-destructive."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ..base import Command

if TYPE_CHECKING:
    from ...core.document import Document


class RotateLayerCommand(Command):
    """Rotate a layer around a pivot point.

    For raster layers the rotation is stored as a non-destructive
    ``transform_angle`` and display pixels are recomputed.
    For vector/shape layers the rotation is applied directly to each
    object's affine transform.

    Parameters
    ----------
    layer_id : str
        ID of the layer to rotate.
    angle : float
        New absolute angle in degrees (raster) or delta angle (vector).
    pivot : tuple[float, float]
        The (x, y) anchor point around which rotation occurs.
    absolute : bool
        If *True* (default), ``angle`` is the new absolute angle for
        raster layers.  If *False*, ``angle`` is treated as a delta.
    """

    def __init__(
        self,
        layer_id: str,
        angle: float,
        pivot: tuple[float, float],
        absolute: bool = True,
    ) -> None:
        self.layer_id = layer_id
        self.angle = angle
        self.pivot = pivot
        self.absolute = absolute

    def execute(self, document: Document) -> None:
        from ...core.enums import LayerType

        layer = document.layers.get(self.layer_id)
        if layer is None or layer.locked:
            return

        if layer.layer_type == LayerType.RASTER:
            if self.absolute:
                layer.transform_angle = self.angle
            else:
                layer.transform_angle += self.angle
            layer.compute_display()

        elif layer.layer_type == LayerType.SHAPE:
            delta = self.angle if not self.absolute else (
                self.angle - getattr(layer, "transform_angle", 0.0)
            )
            self._rotate_vector_layer(document, layer, delta,
                                      self.pivot[0], self.pivot[1])

        # NOTE: snapshot / mark_dirty are the caller's responsibility so
        # that interactive use doesn't deep-copy all layers on every frame.

    # -- vector helpers -------------------------------------------------------

    @staticmethod
    def _rotate_vector_layer(document, layer, angle_deg, cx, cy) -> None:
        from ...vector.geometry import AffineTransform

        vl = getattr(layer, "_vector_data", None)
        if not vl:
            return

        rad = math.radians(angle_deg)
        xf = (
            AffineTransform.translation(cx, cy)
            .concat(AffineTransform.rotation(rad))
            .concat(AffineTransform.translation(-cx, -cy))
        )

        for obj in vl.objects:
            obj.transform = xf.concat(obj.transform)
            obj.invalidate()

        from ...vector.rasterizer import rasterize_vector_layer_tight
        layer._pixels_dirty = True
        rasterize_vector_layer_tight(document, layer=layer, force=True)
