"""Add group command."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document


class AddGroupCommand(Command):
    """Add a group or group selected layers."""

    def __init__(self, name: str = "Group", layer_ids: list[str] | None = None) -> None:
        self.name = name
        self.layer_ids = layer_ids  # If set, group these; else add empty group

    def execute(self, document: Document) -> None:
        if self.layer_ids and len(self.layer_ids) >= 1:
            document.group_selected_layers(self.layer_ids, self.name)
        else:
            document.add_group(name=self.name)
