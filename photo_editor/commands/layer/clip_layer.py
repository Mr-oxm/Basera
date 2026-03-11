"""Clip-to-layer command — set a layer as a clipping mask for another."""

from __future__ import annotations

from ..base import Command
from ...core.document import Document


class ClipToLayerCommand(Command):
    """Set *layer_id* as a clipping mask for *target_id*.

    In Affinity/Photoshop, ``clipping_mask = True`` means the layer clips
    to the alpha channel of the layer **immediately below** it in the stack.
    We do NOT reparent — just set the flag and reposition the layer so it sits
    directly above the target in the stack order.
    """

    def __init__(self, layer_id: str, target_id: str) -> None:
        self.layer_id = layer_id
        self.target_id = target_id

    def execute(self, document: Document) -> None:
        layer = document.layers.get(self.layer_id)
        target = document.layers.get(self.target_id)
        if layer is None or target is None:
            return

        layer.clipping_mask = True

        # Position layer directly above the target in the stack.
        # The compositor iterates bottom→top; the clipping layer must be
        # the next visible layer after the target it clips to.
        stack = document.layers
        stack_list = list(stack)
        target_idx = None
        for i, l in enumerate(stack_list):
            if l.id == self.target_id:
                target_idx = i
                break
        if target_idx is not None:
            # Remove drag layer from its current position
            stack._layers = [l for l in stack._layers if l.id != self.layer_id]
            # Insert right after the target (higher in stack = above)
            new_idx = 0
            for i, l in enumerate(stack._layers):
                if l.id == self.target_id:
                    new_idx = i + 1
                    break
            stack._layers.insert(new_idx, layer)

            # If layer was a child of something, unparent it
            if layer.parent_id:
                old_parent = stack.get(layer.parent_id)
                if old_parent:
                    if layer.id in old_parent.children:
                        old_parent.children.remove(layer.id)
                    if layer.id in old_parent.mask_layers:
                        old_parent.mask_layers.remove(layer.id)
                layer.parent_id = None

        document.save_snapshot("Clip to Layer")
        document.mark_dirty()
