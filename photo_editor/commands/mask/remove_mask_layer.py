"""Remove mask layer command."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document


class RemoveMaskLayerCommand(Command):
    """Remove a mask layer by ID."""

    def __init__(self, mask_layer_id: str) -> None:
        self.mask_layer_id = mask_layer_id

    def execute(self, document: Document) -> None:
        document.remove_mask_layer(self.mask_layer_id)
