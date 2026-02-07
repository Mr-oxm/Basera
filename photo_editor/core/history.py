"""Undo / redo history with smart state snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class HistoryState:
    """Single snapshot in the undo stack."""

    name: str
    layer_data: dict[str, np.ndarray] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class HistoryManager:
    """Linear undo/redo stack with configurable depth."""

    def __init__(self, max_states: int = 50) -> None:
        self._states: list[HistoryState] = []
        self._index: int = -1
        self._max = max_states

    # ---- Query --------------------------------------------------------------

    @property
    def can_undo(self) -> bool:
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        return self._index < len(self._states) - 1

    @property
    def current_index(self) -> int:
        return self._index

    @property
    def states(self) -> list[HistoryState]:
        return self._states

    # ---- Mutation -----------------------------------------------------------

    def push(self, state: HistoryState) -> None:
        self._states = self._states[: self._index + 1]
        self._states.append(state)
        if len(self._states) > self._max:
            self._states.pop(0)
        else:
            self._index += 1

    def undo(self) -> HistoryState | None:
        if self.can_undo:
            self._index -= 1
            return self._states[self._index]
        return None

    def redo(self) -> HistoryState | None:
        if self.can_redo:
            self._index += 1
            return self._states[self._index]
        return None

    def current(self) -> HistoryState | None:
        if 0 <= self._index < len(self._states):
            return self._states[self._index]
        return None

    def clear(self) -> None:
        self._states.clear()
        self._index = -1

    def names(self) -> list[str]:
        return [s.name for s in self._states]
