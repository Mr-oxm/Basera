"""Drop-as-shape-mask command — use a layer's alpha to clip the parent."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document


class DropAsMaskCommand(Command):
    """Attach *layer_id* as a clipping child of *target_id*.

    The dropped layer's alpha channel will limit the parent's visible
    area (parent clipped to child shape).  The layer type is NOT changed
    — the layer keeps its pixels and type, and is added to the target's
    ``children`` list with ``clips_parent = True`` so the compositor
    clips the parent to this child's alpha.
    """

    def __init__(self, layer_id: str, target_id: str) -> None:
        self.layer_id = layer_id
        self.target_id = target_id

    def execute(self, document: Document) -> None:
        layer = document.layers.get(self.layer_id)
        target = document.layers.get(self.target_id)
        if layer is None or target is None:
            return

        # Detach from old parent
        if layer.parent_id:
            old_parent = document.layers.get(layer.parent_id)
            if old_parent:
                if self.layer_id in old_parent.mask_layers:
                    old_parent.mask_layers.remove(self.layer_id)
                if self.layer_id in old_parent.children:
                    old_parent.children.remove(self.layer_id)

        # Attach as clipping child — the child's alpha clips the parent.
        layer.parent_id = self.target_id
        layer.ex_parent_id = None
        layer.clips_parent = True
        if self.layer_id not in target.children:
            target.children.append(self.layer_id)

        # Reposition in stack just before the target
        document.layers.reposition_before(self.layer_id, self.target_id)

        document.save_snapshot("Drop as Shape Mask")
        document.mark_dirty()
