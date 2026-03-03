"""Add mask layer command."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document


class AddMaskLayerCommand(Command):
    """Add a mask layer to a target layer or as standalone."""

    def __init__(
        self,
        target_id: str | None = None,
        fill_white: bool = True,
        name: str | None = None,
        standalone: bool = False,
    ) -> None:
        self.target_id = "__standalone__" if standalone else target_id
        self.fill_white = fill_white
        self.name = name

    def execute(self, document: Document) -> None:
        document.add_mask_layer(
            target_id=self.target_id,
            fill_white=self.fill_white,
            name=self.name,
        )
