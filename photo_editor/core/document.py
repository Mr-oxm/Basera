"""Document model — represents a single open image project."""

from __future__ import annotations

import numpy as np

from .enums import BlendMode, LayerType
from .history import HistoryManager, HistoryState
from .layer import Layer
from .layer_stack import LayerStack
from .selection import Selection


class Document:
    """Top-level container for an editing session."""

    def __init__(self, width: int, height: int, name: str = "Untitled") -> None:
        self.name = name
        self.width = width
        self.height = height
        self.file_path: str | None = None
        self.dpi: int = 72
        self.layers = LayerStack()
        self.history = HistoryManager()
        self.selection = Selection(width, height)
        self._dirty = False

        bg = Layer(name="Background", width=width, height=height)
        bg.pixels[:] = np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float32)
        self.layers.add(bg)
        self._snapshot("New Document")

    # ---- Dirty flag ---------------------------------------------------------

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self) -> None:
        self._dirty = True

    def mark_clean(self) -> None:
        self._dirty = False

    # ---- Layer operations ---------------------------------------------------

    def add_layer(
        self, name: str = "Layer", layer_type: LayerType = LayerType.RASTER,
    ) -> Layer:
        layer = Layer(name=name, width=self.width, height=self.height, layer_type=layer_type)
        self.layers.add(layer)
        self._snapshot(f"Add {name}")
        self._dirty = True
        return layer

    def add_group(self, name: str = "Group") -> Layer:
        group = Layer(name=name, width=self.width, height=self.height, layer_type=LayerType.GROUP)
        self.layers.add(group)
        self._snapshot(f"Add Group {name}")
        self._dirty = True
        return group

    def place_image(self, pixels: np.ndarray, name: str = "Placed Image") -> Layer:
        """Import an RGBA image as a new layer."""
        h, w = pixels.shape[:2]
        layer = Layer(name=name, width=w, height=h)
        layer.pixels = pixels
        self.layers.add(layer)
        self._snapshot(f"Place {name}")
        self._dirty = True
        return layer

    def remove_layer(self, layer_id: str) -> None:
        removed = self.layers.remove(layer_id)
        if removed:
            self._snapshot(f"Delete {removed.name}")
            self._dirty = True

    def duplicate_layer(self, layer_id: str) -> Layer | None:
        dup = self.layers.duplicate(layer_id)
        if dup:
            self._snapshot(f"Duplicate {dup.name}")
            self._dirty = True
        return dup

    def flatten(self) -> None:
        """Merge all visible layers into the background."""
        from ..engine.render_pipeline import RenderPipeline
        pipeline = RenderPipeline()
        merged = pipeline.execute(self)
        # Remove all layers, create single flattened one
        self.layers = LayerStack()
        bg = Layer(name="Background", width=self.width, height=self.height)
        bg.pixels = merged
        bg.locked = True
        self.layers.add(bg)
        self._snapshot("Flatten Image")
        self._dirty = True

    # ---- History ------------------------------------------------------------

    def undo(self) -> None:
        state = self.history.undo()
        if state:
            self._restore(state)

    def redo(self) -> None:
        state = self.history.redo()
        if state:
            self._restore(state)

    def navigate_history(self, target_index: int) -> None:
        """Jump to a specific history state by index."""
        while self.history.current_index > target_index and self.history.can_undo:
            self.history.undo()
        while self.history.current_index < target_index and self.history.can_redo:
            self.history.redo()
        current = self.history.current()
        if current:
            self._restore(current)

    def save_snapshot(self, action: str) -> None:
        self._snapshot(action)

    def _snapshot(self, action: str) -> None:
        state = HistoryState(name=action)
        for layer in self.layers:
            state.layer_data[layer.id] = layer.pixels.copy()
        self.history.push(state)

    def _restore(self, state: HistoryState) -> None:
        for layer in self.layers:
            if layer.id in state.layer_data:
                layer.pixels = state.layer_data[layer.id].copy()
        self._dirty = True

    # ---- Canvas ops ---------------------------------------------------------

    def resize(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        self.selection.resize(width, height)
