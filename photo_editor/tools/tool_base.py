"""Abstract base for all interactive tools."""

from abc import ABC, abstractmethod

import numpy as np

from ..core.document import Document


class Tool(ABC):
    """Base class for interactive canvas tools."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def activate(self) -> None:
        self._active = True

    def deactivate(self) -> None:
        self._active = False

    @abstractmethod
    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        ...

    @abstractmethod
    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        ...

    @abstractmethod
    def on_release(self, doc: Document, x: int, y: int) -> None:
        ...

    def _stamp_circle(
        self, target: np.ndarray, cx: int, cy: int,
        radius: int, color: np.ndarray, hardness: float = 1.0,
        opacity: float = 1.0,
    ) -> None:
        """Stamp a circular brush dab onto *target*."""
        h, w = target.shape[:2]
        y0, y1 = max(0, cy - radius), min(h, cy + radius + 1)
        x0, x1 = max(0, cx - radius), min(w, cx + radius + 1)
        if y1 <= y0 or x1 <= x0:
            return
        yy, xx = np.mgrid[y0:y1, x0:x1]
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2).astype(np.float32)
        mask = np.clip(1.0 - dist / max(radius, 1), 0, 1) ** (1.0 / max(hardness, 0.01))
        mask *= opacity
        mask = mask[..., np.newaxis]
        target[y0:y1, x0:x1] = target[y0:y1, x0:x1] * (1 - mask) + color * mask
