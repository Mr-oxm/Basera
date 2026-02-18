"""Reorder layers command."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document


class ReorderLayersCommand(Command):
    """Reorder layers by specifying the new stack order."""

    def __init__(self, ordered_layer_ids: list[str]) -> None:
        self.ordered_layer_ids = list(ordered_layer_ids)

    def execute(self, document: Document) -> None:
        document.layers.reorder_by_ids(self.ordered_layer_ids)
        document.save_snapshot("Reorder Layers")
        document.mark_dirty()
