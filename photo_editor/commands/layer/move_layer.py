"""Move/reorder layer command."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document


class MoveLayerCommand(Command):
    """Reparent layers to a group (or unparent)."""

    def __init__(
        self,
        layer_ids: list[str],
        target_parent_id: str | None = None,
    ) -> None:
        """Reparent layers.

        Parameters
        ----------
        layer_ids : list[str]
            Layers to move.
        target_parent_id : str | None
            New parent group ID, or None to unparent (top level).
        """
        self.layer_ids = list(layer_ids)
        self.target_parent_id = target_parent_id

    def execute(self, document: Document) -> None:
        document.layers.reparent(self.layer_ids, self.target_parent_id)
        action = "Move to Group" if self.target_parent_id else "Remove from Group"
        document.save_snapshot(action)
        document.mark_dirty()
