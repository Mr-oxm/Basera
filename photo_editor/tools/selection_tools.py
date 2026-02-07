"""Selection tools — Rect, Ellipse, Lasso, and Magic Wand selections."""

import cv2
import numpy as np

from .tool_base import Tool
from ..core.document import Document


# ======================================================================
# Rectangular selection
# ======================================================================


class RectSelectTool(Tool):
    """Drag to create a rectangular selection."""

    def __init__(self) -> None:
        super().__init__("Rectangular Select")
        self.feather: int = 0
        self._start_x: int = 0
        self._start_y: int = 0
        self._dragging: bool = False

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        self._start_x, self._start_y = x, y
        self._dragging = True

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        pass  # Could show live preview

    def on_release(self, doc: Document, x: int, y: int) -> None:
        if not self._dragging:
            return
        self._dragging = False
        rx = min(self._start_x, x)
        ry = min(self._start_y, y)
        rw = abs(x - self._start_x)
        rh = abs(y - self._start_y)
        if rw == 0 or rh == 0:
            doc.selection.deselect()
            return
        doc.selection.select_rect(rx, ry, rw, rh)
        if self.feather > 0:
            doc.selection.feather(self.feather)


# ======================================================================
# Elliptical selection
# ======================================================================


class EllipseSelectTool(Tool):
    """Drag to create an elliptical selection."""

    def __init__(self) -> None:
        super().__init__("Elliptical Select")
        self.feather: int = 0
        self._start_x: int = 0
        self._start_y: int = 0
        self._dragging: bool = False

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        self._start_x, self._start_y = x, y
        self._dragging = True

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        pass

    def on_release(self, doc: Document, x: int, y: int) -> None:
        if not self._dragging:
            return
        self._dragging = False
        cx = (self._start_x + x) // 2
        cy = (self._start_y + y) // 2
        rx = abs(x - self._start_x) // 2
        ry = abs(y - self._start_y) // 2
        if rx == 0 or ry == 0:
            doc.selection.deselect()
            return
        doc.selection.select_ellipse(cx, cy, rx, ry)
        if self.feather > 0:
            doc.selection.feather(self.feather)


# ======================================================================
# Free-hand lasso selection
# ======================================================================


class LassoTool(Tool):
    """Free-hand selection by collecting points along a drag path."""

    def __init__(self) -> None:
        super().__init__("Lasso")
        self.feather: int = 0
        self._points: list[tuple[int, int]] = []
        self._drawing: bool = False

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        self._points = [(x, y)]
        self._drawing = True

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        if self._drawing:
            self._points.append((x, y))

    def on_release(self, doc: Document, x: int, y: int) -> None:
        if not self._drawing:
            return
        self._drawing = False
        self._points.append((x, y))

        if len(self._points) < 3:
            doc.selection.deselect()
            return

        # Rasterise polygon into a mask
        h, w = doc.height, doc.width
        mask = np.zeros((h, w), dtype=np.float32)
        pts = np.array(self._points, dtype=np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(mask, [pts], 1.0)

        doc.selection._mask = mask
        if self.feather > 0:
            doc.selection.feather(self.feather)
        self._points.clear()


# ======================================================================
# Magic Wand (flood-fill tolerance selection)
# ======================================================================


class MagicWandTool(Tool):
    """Selects connected pixels similar to the clicked colour."""

    def __init__(self) -> None:
        super().__init__("Magic Wand")
        self.tolerance: int = 32  # 0–255 scale
        self.contiguous: bool = True
        self.feather: int = 0

    def _flood_mask(self, pixels: np.ndarray, sx: int, sy: int) -> np.ndarray:
        h, w = pixels.shape[:2]
        seed = pixels[sy, sx].copy()
        tol = self.tolerance / 255.0
        visited = np.zeros((h, w), dtype=np.bool_)
        mask = np.zeros((h, w), dtype=np.float32)
        stack = [(sx, sy)]
        while stack:
            cx, cy = stack.pop()
            if cx < 0 or cx >= w or cy < 0 or cy >= h:
                continue
            if visited[cy, cx]:
                continue
            visited[cy, cx] = True
            if np.abs(pixels[cy, cx] - seed).max() > tol:
                continue
            mask[cy, cx] = 1.0
            stack.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])
        return mask

    def _global_mask(self, pixels: np.ndarray, sx: int, sy: int) -> np.ndarray:
        seed = pixels[sy, sx]
        diff = np.abs(pixels - seed).max(axis=-1)
        return (diff <= self.tolerance / 255.0).astype(np.float32)

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        layer = doc.layers.active_layer
        if layer is None:
            return
        h, w = layer.pixels.shape[:2]
        if x < 0 or x >= w or y < 0 or y >= h:
            return

        if self.contiguous:
            mask = self._flood_mask(layer.pixels, x, y)
        else:
            mask = self._global_mask(layer.pixels, x, y)

        doc.selection._mask = mask
        if self.feather > 0:
            doc.selection.feather(self.feather)

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        pass

    def on_release(self, doc: Document, x: int, y: int) -> None:
        pass
