"""Eraser tool — removes pixel data by reducing alpha on the active layer."""

import numpy as np

from .tool_base import Tool
from ..core.document import Document


class EraserTool(Tool):
    """Round eraser that reduces alpha (opacity) of existing pixels."""

    def __init__(self) -> None:
        super().__init__("Eraser")
        self.size: int = 20
        self.hardness: float = 0.8
        self.opacity: float = 1.0
        self.spacing: float = 0.25
        self._last_x: int = 0
        self._last_y: int = 0
        self._drawing: bool = False

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def generate_preview_dab(self) -> np.ndarray | None:
        """Return an alpha-mask dab showing eraser intensity.

        The returned image has R=G=B=255 with alpha representing the
        erase strength.  The canvas view uses this to composite the
        eraser preview (pixels fading to transparency).
        """
        d = max(self.size, 1)
        r = d / 2.0
        center = r - 0.5
        dab = np.zeros((d, d, 4), dtype=np.uint8)
        yy, xx = np.mgrid[0:d, 0:d]
        dist = np.sqrt((xx - center) ** 2 + (yy - center) ** 2).astype(np.float32)
        mask = np.clip(1.0 - dist / max(r, 1), 0, 1)
        mask = mask ** (1.0 / max(self.hardness, 0.01))
        mask *= self.opacity
        dab[..., 0] = 255
        dab[..., 1] = 255
        dab[..., 2] = 255
        dab[..., 3] = np.clip(mask * 255, 0, 255).astype(np.uint8)
        return dab

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _effective_radius(self, pressure: float) -> int:
        return max(1, int((self.size / 2) * pressure))

    def _stroke_points(self, x0: int, y0: int, x1: int, y1: int, step: float):
        dx = x1 - x0
        dy = y1 - y0
        dist = max(1.0, np.hypot(dx, dy))
        steps = int(dist / max(step, 1))
        for i in range(steps + 1):
            t = i / max(steps, 1)
            yield int(x0 + dx * t), int(y0 + dy * t)

    def _erase_circle(self, target: np.ndarray, cx: int, cy: int,
                      radius: int, hardness: float, opacity: float) -> None:
        """Reduce alpha in a circular region."""
        h, w = target.shape[:2]
        y0, y1 = max(0, cy - radius), min(h, cy + radius + 1)
        x0, x1 = max(0, cx - radius), min(w, cx + radius + 1)
        if y1 <= y0 or x1 <= x0:
            return
        yy, xx = np.mgrid[y0:y1, x0:x1]
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2).astype(np.float32)
        mask = np.clip(1.0 - dist / max(radius, 1), 0, 1)
        mask = mask ** (1.0 / max(hardness, 0.01))
        mask *= opacity
        # Reduce the alpha channel
        target[y0:y1, x0:x1, 3] *= (1.0 - mask)
        # Also fade RGB towards transparent to avoid colour fringing
        for c in range(3):
            target[y0:y1, x0:x1, c] *= (1.0 - mask)
        np.clip(target[y0:y1, x0:x1], 0, 1, out=target[y0:y1, x0:x1])

    def _erase_along(self, doc: Document, x0: int, y0: int, x1: int, y1: int,
                     pressure: float) -> None:
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return
        lx, ly = layer.position
        radius = self._effective_radius(pressure)
        eff_opacity = self.opacity * pressure
        step = max(1.0, radius * 2 * self.spacing)
        for px, py in self._stroke_points(x0, y0, x1, y1, step):
            self._erase_circle(layer.pixels, px - lx, py - ly, radius,
                               self.hardness, eff_opacity)

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        doc.save_snapshot("Eraser Stroke")
        self._drawing = True
        self._last_x, self._last_y = x, y
        self._erase_along(doc, x, y, x, y, pressure)

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        if not self._drawing:
            return
        self._erase_along(doc, self._last_x, self._last_y, x, y, pressure)
        self._last_x, self._last_y = x, y

    def on_release(self, doc: Document, x: int, y: int) -> None:
        self._drawing = False
