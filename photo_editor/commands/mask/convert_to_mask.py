"""Convert layer to mask command."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document


class ConvertToMaskCommand(Command):
    """Convert a layer to a mask layer attached to the layer above."""

    def __init__(self, layer_id: str, target_id: str | None = None) -> None:
        self.layer_id = layer_id
        self.target_id = target_id

    def execute(self, document: Document) -> None:
        document.convert_layer_to_mask(self.layer_id, self.target_id)
