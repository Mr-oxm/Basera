"""Add layer command."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document
from ...core.enums import LayerType


class AddLayerCommand(Command):
    """Add a new layer to the document."""

    def __init__(
        self,
        name: str = "Layer",
        layer_type: LayerType = LayerType.RASTER,
    ) -> None:
        self.name = name
        self.layer_type = layer_type

    def execute(self, document: Document) -> None:
        document.add_layer(name=self.name, layer_type=self.layer_type)
