"""Move/reorder layer command."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document
from ...core.enums import LayerType
from ...core.layer_stack import LayerStack


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
        before = document.layers_visual_bounds(self.layer_ids)
        parent_ids = set()
        for layer_id in self.layer_ids:
            layer = document.layers.get(layer_id)
            if layer is not None and layer.parent_id is not None:
                parent_ids.add(layer.parent_id)
        if self.target_parent_id is not None:
            parent_ids.add(self.target_parent_id)
        for parent_id in parent_ids:
            parent = document.layers.get(parent_id)
            if parent is None:
                continue
            if parent.layer_type == LayerType.GROUP:
                before = document._merge_rects(
                    before,
                    document._rect_from_bounds(LayerStack._content_bounds(parent, document.layers)),
                )
            else:
                before = document._merge_rects(before, document.layer_visual_bounds(parent_id, include_related=False))

        document.layers.reparent(self.layer_ids, self.target_parent_id)
        action = "Move to Group" if self.target_parent_id else "Remove from Group"
        document.save_snapshot(action)
        document.mark_dirty()
        after = document.layers_visual_bounds(self.layer_ids)
        for parent_id in parent_ids:
            parent = document.layers.get(parent_id)
            if parent is None:
                continue
            if parent.layer_type == LayerType.GROUP:
                after = document._merge_rects(
                    after,
                    document._rect_from_bounds(LayerStack._content_bounds(parent, document.layers)),
                )
            else:
                after = document._merge_rects(after, document.layer_visual_bounds(parent_id, include_related=False))
        document.mark_region_pair_dirty(before, after)
