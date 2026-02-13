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

    @staticmethod
    def _rasterize_if_needed(doc: Document) -> None:
        """If the active layer has a non-destructive transform, bake it.

        Destructive tools (brush, eraser, paint bucket, …) must call
        this before modifying pixel data so that the source is consistent.
        """
        layer = doc.layers.active_layer
        if layer is not None and layer._source_pixels is not None:
            layer.rasterize_transform()

    @staticmethod
    def _get_sel_mask(doc: Document) -> np.ndarray | None:
        """Return a layer-local selection mask for the active layer, or None.

        The returned array has shape (lh, lw) float32 in [0,1] and is
        aligned to the layer's pixel grid.
        """
        if doc is None or not doc.selection.active:
            return None
        layer = doc.layers.active_layer
        if layer is None:
            return None
        mask = doc.selection._mask
        lx, ly = layer.position
        lh, lw = layer.pixels.shape[:2]
        dh, dw = mask.shape[:2]

        dy0 = max(0, ly)
        dy1 = min(dh, ly + lh)
        dx0 = max(0, lx)
        dx1 = min(dw, lx + lw)
        if dy1 <= dy0 or dx1 <= dx0:
            return np.zeros((lh, lw), dtype=np.float32)

        out = np.zeros((lh, lw), dtype=np.float32)
        sy0, sy1 = dy0 - ly, dy1 - ly
        sx0, sx1 = dx0 - lx, dx1 - lx
        out[sy0:sy1, sx0:sx1] = mask[dy0:dy1, dx0:dx1]
        return out

    def generate_preview_dab(self) -> np.ndarray | None:
        """Return an RGBA uint8 array showing what a single dab looks like.

        Override in subclasses to provide a real-time preview stamp.
        Returns ``None`` if this tool has no preview.
        """
        return None

    def _stamp_circle(
        self, target: np.ndarray, cx: int, cy: int,
        radius: int, color: np.ndarray, hardness: float = 1.0,
        opacity: float = 1.0, sel_mask: np.ndarray | None = None,
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
        # Clip to selection
        if sel_mask is not None:
            mask *= sel_mask[y0:y1, x0:x1]
        mask = mask[..., np.newaxis]
        # In-place compositing on the target slice
        roi = target[y0:y1, x0:x1]
        inv_mask = 1.0 - mask
        np.multiply(roi, inv_mask, out=roi)
        roi += color * mask
        np.clip(roi, 0, 1, out=roi)
