"""Invert mask layer command."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document
from ...core.enums import LayerType
from ...masks.mask_manager import MaskManager


class InvertMaskLayerCommand(Command):
    """Invert a mask layer's grayscale values."""

    def __init__(self, mask_layer_id: str) -> None:
        self.mask_layer_id = mask_layer_id

    def execute(self, document: Document) -> None:
        layer = document.layers.get(self.mask_layer_id)
        if layer is not None and layer.layer_type == LayerType.MASK:
            document.save_snapshot("Invert Mask Layer")
            MaskManager.invert_mask_layer(layer)
            document.mark_dirty()
