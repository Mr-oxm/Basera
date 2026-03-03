"""Attach mask to layer command (drag-drop)."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document
from ...core.enums import LayerType


class AttachMaskToLayerCommand(Command):
    """Attach a mask layer to a target layer (reparent + reposition)."""

    def __init__(self, mask_id: str, target_id: str) -> None:
        self.mask_id = mask_id
        self.target_id = target_id

    def execute(self, document: Document) -> None:
        mask = document.layers.get(self.mask_id)
        target = document.layers.get(self.target_id)
        if mask is None or target is None:
            return
        if mask.layer_type != LayerType.MASK:
            return
        if mask.parent_id:
            old_parent = document.layers.get(mask.parent_id)
            if old_parent and self.mask_id in old_parent.mask_layers:
                old_parent.mask_layers.remove(self.mask_id)
        mask.parent_id = self.target_id
        mask.ex_parent_id = None
        if self.mask_id not in target.mask_layers:
            target.mask_layers.append(self.mask_id)
        document.layers.reposition_before(self.mask_id, self.target_id)
        document.save_snapshot("Attach Mask to Layer")
        document.mark_dirty()
