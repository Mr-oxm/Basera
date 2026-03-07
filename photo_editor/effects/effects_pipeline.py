"""Chain multiple runtime effects into an ordered post-process pipeline.

Unlike adjustment and filter layers, this pipeline is not document-structure
state. It is a runtime processor chain that can enable, disable, reorder, and
apply effect processors sequentially to a rendered image.
"""

from __future__ import annotations

import numpy as np

from .effect_base import Effect


class EffectsPipeline:
    """Ordered list of runtime effects applied sequentially."""

    def __init__(self) -> None:
        self._effects: list[Effect] = []

    @property
    def effects(self) -> list[Effect]:
        return self._effects

    def add(self, effect: Effect) -> None:
        self._effects.append(effect)

    def remove(self, index: int) -> None:
        if 0 <= index < len(self._effects):
            self._effects.pop(index)

    def clear(self) -> None:
        self._effects.clear()

    def move(self, from_idx: int, to_idx: int) -> None:
        if 0 <= from_idx < len(self._effects) and 0 <= to_idx < len(self._effects):
            e = self._effects.pop(from_idx)
            self._effects.insert(to_idx, e)

    def process(self, image: np.ndarray) -> np.ndarray:
        """Apply enabled effects in order to an already-rendered image."""
        result = image.copy()
        for effect in self._effects:
            if effect.enabled:
                result = effect.apply(result)
        return result
