"""Reorder layers command."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document


class ReorderLayersCommand(Command):
    """Reorder layers by specifying the new stack order."""

    def __init__(self, ordered_layer_ids: list[str]) -> None:
        self.ordered_layer_ids = list(ordered_layer_ids)

    def execute(self, document: Document) -> None:
        old_order = [layer.id for layer in document.layers]
        changed_ids = [
            layer_id
            for index, layer_id in enumerate(self.ordered_layer_ids)
            if index < len(old_order) and old_order[index] != layer_id
        ]
        if not changed_ids:
            return
        before = document.layers_visual_bounds(changed_ids)
        document.layers.reorder_by_ids(self.ordered_layer_ids)
        document.save_metadata_snapshot("Reorder Layers")
        document.mark_dirty()
        after = document.layers_visual_bounds(changed_ids)
        document.mark_region_pair_dirty(before, after)
