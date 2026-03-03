"""Rename layer command."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document


class RenameLayerCommand(Command):
    """Rename a layer."""

    def __init__(self, layer_id: str, new_name: str) -> None:
        self.layer_id = layer_id
        self.new_name = new_name

    def execute(self, document: Document) -> None:
        layer = document.layers.get(self.layer_id)
        if layer is not None:
            layer.name = self.new_name
            document.save_snapshot(f"Rename to {self.new_name}")
            document.mark_dirty()
