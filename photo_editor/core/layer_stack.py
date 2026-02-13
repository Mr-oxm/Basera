"""Ordered layer collection with group support."""

from __future__ import annotations

import numpy as np

from .layer import Layer
from .enums import LayerType


class LayerStack:
    """Manages the ordered list of layers in a document."""

    def __init__(self) -> None:
        self._layers: list[Layer] = []
        self._active_index: int = -1

    # ---- Properties ---------------------------------------------------------

    @property
    def layers(self) -> list[Layer]:
        return self._layers

    @property
    def active_layer(self) -> Layer | None:
        if 0 <= self._active_index < len(self._layers):
            return self._layers[self._active_index]
        return None

    @property
    def active_index(self) -> int:
        return self._active_index

    @active_index.setter
    def active_index(self, value: int) -> None:
        if -1 <= value < len(self._layers):
            self._active_index = value

    # ---- Mutations ----------------------------------------------------------

    def add(self, layer: Layer, index: int = -1) -> None:
        if index < 0:
            self._layers.append(layer)
            self._active_index = len(self._layers) - 1
        else:
            self._layers.insert(index, layer)
            self._active_index = index

    def remove(self, layer_id: str) -> Layer | None:
        for i, layer in enumerate(self._layers):
            if layer.id == layer_id:
                removed = self._layers.pop(i)
                self._active_index = min(self._active_index, len(self._layers) - 1)
                return removed
        return None

    def get(self, layer_id: str) -> Layer | None:
        for layer in self._layers:
            if layer.id == layer_id:
                return layer
        return None

    def move(self, from_index: int, to_index: int) -> None:
        if 0 <= from_index < len(self._layers) and 0 <= to_index < len(self._layers):
            layer = self._layers.pop(from_index)
            self._layers.insert(to_index, layer)
            self._active_index = to_index

    def duplicate(self, layer_id: str) -> Layer | None:
        original = self.get(layer_id)
        if original is None:
            return None
        copy = original.duplicate()
        idx = self._layers.index(original)
        self.add(copy, idx + 1)
        return copy

    # ---- Group / reparent ---------------------------------------------------

    def reparent(self, layer_ids: list[str], new_parent_id: str | None) -> None:
        """Move *layer_ids* into the group identified by *new_parent_id*.

        Pass ``None`` to un-parent (move to top level).
        The layers are also repositioned in the stack so that children
        sit just before (below) their new group, or at the top of the
        stack when un-parenting.
        """
        new_parent = self.get(new_parent_id) if new_parent_id else None
        for lid in layer_ids:
            layer = self.get(lid)
            if layer is None or lid == new_parent_id:
                continue
            # Remove from old parent's children / mask_layers list
            if layer.parent_id:
                old_parent = self.get(layer.parent_id)
                if old_parent:
                    if lid in old_parent.children:
                        old_parent.children.remove(lid)
                    if lid in old_parent.mask_layers:
                        old_parent.mask_layers.remove(lid)
            # When a mask layer is explicitly unparented (made standalone),
            # clear ex_parent_id so it acts as a true standalone mask.
            if layer.layer_type == LayerType.MASK and new_parent_id is None:
                layer.ex_parent_id = None
            # Set new parent
            layer.parent_id = new_parent_id
            if new_parent and lid not in new_parent.children:
                new_parent.children.append(lid)

        # Reposition layers in the stack.
        # First, pull the affected layers out of the list.
        moved: list[Layer] = []
        for lid in layer_ids:
            for i, layer in enumerate(self._layers):
                if layer.id == lid:
                    moved.append(self._layers.pop(i))
                    break

        if new_parent_id:
            # Insert just before the group so compositing order is correct.
            group_idx = 0
            for i, layer in enumerate(self._layers):
                if layer.id == new_parent_id:
                    group_idx = i
                    break
            for j, layer in enumerate(moved):
                self._layers.insert(group_idx + j, layer)
        else:
            # Un-parenting: append at the end (top of the stack).
            self._layers.extend(moved)

    def create_group_from(self, layer_ids: list[str], group_name: str = "Group") -> "Layer | None":
        """Create a new group layer containing *layer_ids*."""
        from .enums import LayerType

        indices = []
        for lid in layer_ids:
            for i, layer in enumerate(self._layers):
                if layer.id == lid:
                    indices.append(i)
                    break
        if not indices:
            return None

        # Insert the group above the topmost selected layer
        top_idx = max(indices)
        first = self._layers[indices[0]]
        group = Layer(
            name=group_name,
            width=first.width,
            height=first.height,
            layer_type=LayerType.GROUP,
        )
        self._layers.insert(top_idx + 1, group)

        # Reparent the selected layers into the new group
        for lid in layer_ids:
            layer = self.get(lid)
            if layer is None:
                continue
            # Remove from any previous parent
            if layer.parent_id:
                old_parent = self.get(layer.parent_id)
                if old_parent and lid in old_parent.children:
                    old_parent.children.remove(lid)
            layer.parent_id = group.id
            group.children.append(lid)

        self._active_index = self._layers.index(group)
        return group

    def reorder_by_ids(self, ordered_ids: list[str]) -> None:
        """Reorder the internal list to match *ordered_ids* (bottom → top).

        Any IDs not present in *ordered_ids* are appended at the end.
        """
        id_to_layer = {layer.id: layer for layer in self._layers}
        new_order: list[Layer] = []
        for lid in ordered_ids:
            if lid in id_to_layer:
                new_order.append(id_to_layer.pop(lid))
        # Append any remaining layers that weren't mentioned
        for layer in self._layers:
            if layer.id in id_to_layer:
                new_order.append(layer)
                del id_to_layer[layer.id]
        self._layers = new_order
        # Keep active_index in bounds
        if self._active_index >= len(self._layers):
            self._active_index = max(0, len(self._layers) - 1)

    def reposition_before(self, layer_id: str, target_id: str) -> None:
        """Move *layer_id* to the position just before *target_id* in the stack."""
        layer = self.get(layer_id)
        target = self.get(target_id)
        if layer is None or target is None:
            return
        self._layers = [l for l in self._layers if l.id != layer_id]
        for i, l in enumerate(self._layers):
            if l.id == target_id:
                self._layers.insert(i, layer)
                return
        # Fallback: append
        self._layers.append(layer)

    # ---- Dunder -------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._layers)

    def __iter__(self):
        return iter(self._layers)

    def __getitem__(self, index: int) -> Layer:
        return self._layers[index]

    # ---- Mask layer operations ----------------------------------------------

    def add_mask_layer(
        self,
        target_id: str | None,
        width: int,
        height: int,
        fill_white: bool = True,
        name: str | None = None,
    ) -> Layer | None:
        """Create a new MASK layer and optionally attach it to *target_id*.

        Parameters
        ----------
        target_id : str | None
            Parent layer ID.  ``None`` creates a standalone mask layer.
        width, height : int
            Canvas dimensions for the mask.
        fill_white : bool
            If *True* the mask starts fully white (opaque); otherwise black.
        name : str | None
            Custom name — auto-generated if *None*.

        Returns the newly created mask layer.
        """
        target = self.get(target_id) if target_id else None
        idx_name = 1
        if target:
            idx_name = len(target.mask_layers) + 1
        auto_name = name or (
            f"Mask {idx_name}" if target else "Mask Layer"
        )
        mask_layer = Layer(
            name=auto_name,
            width=width,
            height=height,
            layer_type=LayerType.MASK,
        )
        # Fill with white (fully visible) or black (fully hidden)
        fill_val = 1.0 if fill_white else 0.0
        mask_layer._pixels[:] = np.array(
            [fill_val, fill_val, fill_val, 1.0], dtype=np.float32
        )

        if target:
            mask_layer.parent_id = target_id
            target.mask_layers.append(mask_layer.id)
            # Insert just before the target so that compositing order works
            target_idx = 0
            for i, layer in enumerate(self._layers):
                if layer.id == target_id:
                    target_idx = i
                    break
            self._layers.insert(target_idx, mask_layer)
            self._active_index = target_idx
        else:
            # Standalone mask layer — add at the top
            self._layers.append(mask_layer)
            self._active_index = len(self._layers) - 1

        return mask_layer

    def remove_mask_layer(self, mask_layer_id: str) -> Layer | None:
        """Remove a mask layer, detaching it from any parent."""
        mask_layer = self.get(mask_layer_id)
        if mask_layer is None:
            return None
        # Detach from parent — record the ex-parent so compositing
        # can scope the now-standalone mask to only its former parent.
        if mask_layer.parent_id:
            mask_layer.ex_parent_id = mask_layer.parent_id
            parent = self.get(mask_layer.parent_id)
            if parent and mask_layer_id in parent.mask_layers:
                parent.mask_layers.remove(mask_layer_id)
        return self.remove(mask_layer_id)

    def convert_layer_to_mask(self, layer_id: str, target_id: str) -> Layer | None:
        """Convert an existing raster layer into a mask layer for *target_id*.

        The layer's pixel data is preserved — its luminance will be used
        as the mask intensity.
        """
        layer = self.get(layer_id)
        target = self.get(target_id)
        if layer is None or target is None:
            return None
        if layer.layer_type == LayerType.MASK:
            return layer  # already a mask

        layer.layer_type = LayerType.MASK
        # Remove from any previous group parent
        if layer.parent_id:
            old_parent = self.get(layer.parent_id)
            if old_parent and layer_id in old_parent.children:
                old_parent.children.remove(layer_id)
        layer.parent_id = target_id
        target.mask_layers.append(layer_id)

        # Reposition just before the target
        for i, l in enumerate(self._layers):
            if l.id == layer_id:
                self._layers.pop(i)
                break
        target_idx = 0
        for i, l in enumerate(self._layers):
            if l.id == target_id:
                target_idx = i
                break
        self._layers.insert(target_idx, layer)
        return layer

    def get_mask_layers(self, layer_id: str) -> list[Layer]:
        """Return all MASK layers attached to *layer_id*, in order."""
        layer = self.get(layer_id)
        if layer is None:
            return []
        result: list[Layer] = []
        for mid in layer.mask_layers:
            mask = self.get(mid)
            if mask is not None:
                result.append(mask)
        return result

    def selection_to_mask_layer(
        self,
        target_id: str | None,
        selection_mask: np.ndarray,
        width: int,
        height: int,
    ) -> Layer | None:
        """Create a MASK layer from a selection mask array.

        *selection_mask* should be a float32 (H,W) array in [0,1].
        """
        mask_layer = self.add_mask_layer(
            target_id, width, height, fill_white=False,
            name="Mask from Selection",
        )
        if mask_layer is None:
            return None
        # Broadcast the grayscale selection into RGB channels, keep alpha=1
        mask_layer._pixels[..., 0] = selection_mask
        mask_layer._pixels[..., 1] = selection_mask
        mask_layer._pixels[..., 2] = selection_mask
        mask_layer._pixels[..., 3] = 1.0
        return mask_layer
