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

    def generate_preview_dab(self) -> np.ndarray | None:
        """Return an RGBA uint8 array showing what a single dab looks like.

        Override in subclasses to provide a real-time preview stamp.
        Returns ``None`` if this tool has no preview.
        """
        return None

    def _stamp_circle(
        self, target: np.ndarray, cx: int, cy: int,
        radius: int, color: np.ndarray, hardness: float = 1.0,
        opacity: float = 1.0,
    ) -> None:
        """Stamp a circular brush dab onto *target* (region-optimised)."""
        h, w = target.shape[:2]
        y0, y1 = max(0, cy - radius), min(h, cy + radius + 1)
        x0, x1 = max(0, cx - radius), min(w, cx + radius + 1)
        if y1 <= y0 or x1 <= x0:
            return
        # Use arange + broadcasting — half the memory of mgrid
        yy = np.arange(y0, y1, dtype=np.float32)[:, np.newaxis]
        xx = np.arange(x0, x1, dtype=np.float32)[np.newaxis, :]
        dist_sq = (xx - cx) ** 2 + (yy - cy) ** 2
        r = max(radius, 1)
        mask = np.clip(1.0 - np.sqrt(dist_sq) / r, 0, 1)
        np.power(mask, 1.0 / max(hardness, 0.01), out=mask)
        mask *= opacity
        mask = mask[..., np.newaxis]
        # In-place compositing on the target slice
        roi = target[y0:y1, x0:x1]
        inv_mask = 1.0 - mask
        np.multiply(roi, inv_mask, out=roi)
        roi += color * mask
        np.clip(roi, 0, 1, out=roi)
