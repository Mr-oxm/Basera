"""Merge down command."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document


class MergeDownCommand(Command):
    """Merge the active layer onto the layer below it."""

    def execute(self, document: Document) -> bool:
        return document.merge_down()
