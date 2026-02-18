"""Remove layer command."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document


class RemoveLayerCommand(Command):
    """Remove a layer by ID."""

    def __init__(self, layer_id: str) -> None:
        self.layer_id = layer_id

    def execute(self, document: Document) -> None:
        document.remove_layer(self.layer_id)
