"""Apply mask layer command."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document


class ApplyMaskLayerCommand(Command):
    """Burn a mask layer into its parent's alpha, then remove it."""

    def __init__(self, mask_layer_id: str) -> None:
        self.mask_layer_id = mask_layer_id

    def execute(self, document: Document) -> None:
        document.apply_mask_layer(self.mask_layer_id)
