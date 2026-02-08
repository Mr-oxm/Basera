"""Ordered layer collection with group support."""

from __future__ import annotations

from .layer import Layer


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
        sit just before (below) their new group.
        """
        new_parent = self.get(new_parent_id) if new_parent_id else None
        for lid in layer_ids:
            layer = self.get(lid)
            if layer is None or lid == new_parent_id:
                continue
            # Remove from old parent's children list
            if layer.parent_id:
                old_parent = self.get(layer.parent_id)
                if old_parent and lid in old_parent.children:
                    old_parent.children.remove(lid)
            # Set new parent
            layer.parent_id = new_parent_id
            if new_parent and lid not in new_parent.children:
                new_parent.children.append(lid)

        # Reposition layers in the stack just before the group so that
        # compositing order is correct.
        if new_parent_id:
            moved: list[Layer] = []
            for lid in layer_ids:
                for i, layer in enumerate(self._layers):
                    if layer.id == lid:
                        moved.append(self._layers.pop(i))
                        break
            # Find the group's current index
            group_idx = 0
            for i, layer in enumerate(self._layers):
                if layer.id == new_parent_id:
                    group_idx = i
                    break
            # Insert just before the group
            for j, layer in enumerate(moved):
                self._layers.insert(group_idx + j, layer)

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

    # ---- Dunder -------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._layers)

    def __iter__(self):
        return iter(self._layers)

    def __getitem__(self, index: int) -> Layer:
        return self._layers[index]
