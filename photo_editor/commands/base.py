"""Base command interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.document import Document


class Command(ABC):
    """Base for document-modifying commands.

    Commands are executed by a handler; they call document methods
    which perform _snapshot for undo. Commands decouple UI from engine.
    execute() may return a value (e.g. bool for MergeDownCommand).
    """

    @abstractmethod
    def execute(self, document: Document) -> object:
        """Apply the command to the document. Return value is optional."""
        ...
