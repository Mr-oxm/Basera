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

    # ---- Dunder -------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._layers)

    def __iter__(self):
        return iter(self._layers)

    def __getitem__(self, index: int) -> Layer:
        return self._layers[index]
