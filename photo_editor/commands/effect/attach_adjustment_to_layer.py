"""Attach adjustment/filter to layer command (drag-drop)."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document
from ...core.enums import LayerType


class AttachAdjustmentToLayerCommand(Command):
    """Attach an adjustment/filter layer to a target layer (reparent + reposition)."""

    def __init__(self, adj_id: str, target_id: str) -> None:
        self.adj_id = adj_id
        self.target_id = target_id

    def execute(self, document: Document) -> None:
        adj_layer = document.layers.get(self.adj_id)
        target = document.layers.get(self.target_id)
        if adj_layer is None or target is None:
            return
        if adj_layer.layer_type not in (LayerType.ADJUSTMENT, LayerType.FILTER):
            return
        if adj_layer.parent_id:
            old_parent = document.layers.get(adj_layer.parent_id)
            if old_parent and self.adj_id in old_parent.children:
                old_parent.children.remove(self.adj_id)
        adj_layer.parent_id = self.target_id
        if self.adj_id not in target.children:
            target.children.append(self.adj_id)
        document.layers.reposition_before(self.adj_id, self.target_id)
        document.save_snapshot("Attach Adjustment to Layer")
        document.mark_dirty()
