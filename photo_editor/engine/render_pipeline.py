"""Render pipeline — orchestrates engine + adjustment layers."""

import numpy as np

from ..core.document import Document
from ..core.enums import LayerType
from .render_engine import RenderEngine


class RenderPipeline:
    """Full pipeline: layer compositing → adjustment layers → output."""

    def __init__(self) -> None:
        self._engine = RenderEngine()

    @property
    def engine(self) -> RenderEngine:
        return self._engine

    def execute(self, document: Document) -> np.ndarray:
        result = self._engine.render(document)
        result = self._apply_adjustments(document, result)
        return result

    def execute_to_uint8(self, document: Document) -> np.ndarray:
        return (np.clip(self.execute(document), 0, 1) * 255).astype(np.uint8)

    def invalidate(self, layer_id: str | None = None) -> None:
        self._engine.invalidate(layer_id)

    @staticmethod
    def _apply_adjustments(document: Document, image: np.ndarray) -> np.ndarray:
        for layer in document.layers:
            if not layer.visible or layer.layer_type != LayerType.ADJUSTMENT:
                continue
            adj = layer.adjustment
            if adj is not None:
                image = adj.apply(image, layer.adjustment_params)
        return image
