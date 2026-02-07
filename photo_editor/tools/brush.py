"""Brush tool — paints color onto the active layer with configurable strokes."""

import numpy as np

from .tool_base import Tool
from ..core.document import Document


class BrushTool(Tool):
    """Round pixel brush with pressure-sensitive size and opacity."""

    def __init__(self) -> None:
        super().__init__("Brush")
        self.color: np.ndarray = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
        self.size: int = 20
        self.hardness: float = 0.8
        self.opacity: float = 1.0
        self.flow: float = 1.0
        self.spacing: float = 0.25  # fraction of size between dabs
        self._last_x: int = 0
        self._last_y: int = 0
        self._drawing: bool = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _effective_radius(self, pressure: float) -> int:
        return max(1, int((self.size / 2) * pressure))

    def _effective_opacity(self, pressure: float) -> float:
        return self.opacity * self.flow * pressure

    def _stroke_points(self, x0: int, y0: int, x1: int, y1: int, step: float):
        """Yield (x, y) points along the line at *step* pixel intervals."""
        dx = x1 - x0
        dy = y1 - y0
        dist = max(1.0, np.hypot(dx, dy))
        steps = int(dist / max(step, 1))
        for i in range(steps + 1):
            t = i / max(steps, 1)
            yield int(x0 + dx * t), int(y0 + dy * t)

    def _stamp_along(self, doc: Document, x0: int, y0: int, x1: int, y1: int,
                     pressure: float) -> None:
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return
        radius = self._effective_radius(pressure)
        eff_opacity = self._effective_opacity(pressure)
        step = max(1.0, radius * 2 * self.spacing)
        for px, py in self._stroke_points(x0, y0, x1, y1, step):
            self._stamp_circle(layer.pixels, px, py, radius,
                               self.color, self.hardness, eff_opacity)

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        doc.save_snapshot("Brush Stroke")
        self._drawing = True
        self._last_x, self._last_y = x, y
        # Initial dab at the press point
        self._stamp_along(doc, x, y, x, y, pressure)

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        if not self._drawing:
            return
        self._stamp_along(doc, self._last_x, self._last_y, x, y, pressure)
        self._last_x, self._last_y = x, y

    def on_release(self, doc: Document, x: int, y: int) -> None:
        self._drawing = False
