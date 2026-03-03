"""Flatten image command."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document


class FlattenCommand(Command):
    """Merge all visible layers into the background."""

    def execute(self, document: Document) -> None:
        document.flatten()
