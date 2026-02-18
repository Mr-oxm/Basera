"""Update effect/adjustment params command."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document


class UpdateEffectCommand(Command):
    """Update adjustment or filter layer parameters."""

    def __init__(self, layer_id: str, params: dict) -> None:
        self.layer_id = layer_id
        self.params = dict(params)

    def execute(self, document: Document) -> None:
        layer = document.layers.get(self.layer_id)
        if layer is None:
            return
        if layer.adjustment is None:
            return
        layer.adjustment_params = self.params.copy()
        document.save_snapshot("Update Effect")
        document.mark_dirty()
