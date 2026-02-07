"""Shape tool — draws rectangles, ellipses, lines, and polygons on the active layer."""

import cv2
import numpy as np

from .tool_base import Tool
from ..core.document import Document


class ShapeTool(Tool):
    """Draw geometric shapes with fill and/or stroke."""

    def __init__(self) -> None:
        super().__init__("Shape")
        self.shape_type: str = "rect"  # "rect" | "ellipse" | "line" | "polygon"
        self.fill_color: np.ndarray | None = np.array(
            [0.0, 0.5, 1.0, 1.0], dtype=np.float32,
        )
        self.stroke_color: np.ndarray | None = np.array(
            [0.0, 0.0, 0.0, 1.0], dtype=np.float32,
        )
        self.stroke_width: int = 2
        self.polygon_sides: int = 5

        self._start_x: int = 0
        self._start_y: int = 0
        self._dragging: bool = False

    # ------------------------------------------------------------------
    # Colour helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_bgra_255(color: np.ndarray):
        """Convert float32 [R,G,B,A] → tuple (B,G,B,A) in 0-255 for cv2."""
        c = np.clip(color * 255, 0, 255).astype(np.uint8)
        return (int(c[2]), int(c[1]), int(c[0]), int(c[3]))

    # ------------------------------------------------------------------
    # Shape renderers — draw into an RGBA uint8 buffer then composite
    # ------------------------------------------------------------------

    def _draw_rect(self, buf: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> None:
        if self.fill_color is not None:
            cv2.rectangle(buf, (x0, y0), (x1, y1), self._to_bgra_255(self.fill_color), -1)
        if self.stroke_color is not None and self.stroke_width > 0:
            cv2.rectangle(buf, (x0, y0), (x1, y1),
                          self._to_bgra_255(self.stroke_color), self.stroke_width)

    def _draw_ellipse(self, buf: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> None:
        cx = (x0 + x1) // 2
        cy = (y0 + y1) // 2
        rx = abs(x1 - x0) // 2
        ry = abs(y1 - y0) // 2
        if self.fill_color is not None:
            cv2.ellipse(buf, (cx, cy), (rx, ry), 0, 0, 360,
                        self._to_bgra_255(self.fill_color), -1)
        if self.stroke_color is not None and self.stroke_width > 0:
            cv2.ellipse(buf, (cx, cy), (rx, ry), 0, 0, 360,
                        self._to_bgra_255(self.stroke_color), self.stroke_width)

    def _draw_line(self, buf: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> None:
        color = self.stroke_color if self.stroke_color is not None else self.fill_color
        if color is None:
            return
        thickness = max(1, self.stroke_width)
        cv2.line(buf, (x0, y0), (x1, y1), self._to_bgra_255(color), thickness)

    def _draw_polygon(self, buf: np.ndarray, x0: int, y0: int,
                      x1: int, y1: int) -> None:
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        rx = abs(x1 - x0) / 2.0
        ry = abs(y1 - y0) / 2.0
        n = max(3, self.polygon_sides)
        angles = np.linspace(- np.pi / 2, 2 * np.pi - np.pi / 2, n, endpoint=False)
        pts = np.column_stack([
            (cx + rx * np.cos(angles)).astype(np.int32),
            (cy + ry * np.sin(angles)).astype(np.int32),
        ]).reshape((-1, 1, 2))
        if self.fill_color is not None:
            cv2.fillPoly(buf, [pts], self._to_bgra_255(self.fill_color))
        if self.stroke_color is not None and self.stroke_width > 0:
            cv2.polylines(buf, [pts], True,
                          self._to_bgra_255(self.stroke_color), self.stroke_width)

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        doc.save_snapshot("Draw Shape")
        self._start_x, self._start_y = x, y
        self._dragging = True

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        pass  # Live preview could be rendered here

    def on_release(self, doc: Document, x: int, y: int) -> None:
        if not self._dragging:
            return
        self._dragging = False
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return

        h, w = layer.pixels.shape[:2]
        # Render shape into a BGRA uint8 buffer then convert to float RGBA
        buf = np.zeros((h, w, 4), dtype=np.uint8)
        sx, sy = self._start_x, self._start_y
        draw_fn = {
            "rect": self._draw_rect,
            "ellipse": self._draw_ellipse,
            "line": self._draw_line,
            "polygon": self._draw_polygon,
        }.get(self.shape_type, self._draw_rect)
        draw_fn(buf, sx, sy, x, y)

        # Convert BGRA uint8 → RGBA float32
        shape_rgba = np.zeros_like(buf, dtype=np.float32)
        shape_rgba[..., 0] = buf[..., 2] / 255.0  # R
        shape_rgba[..., 1] = buf[..., 1] / 255.0  # G
        shape_rgba[..., 2] = buf[..., 0] / 255.0  # B
        shape_rgba[..., 3] = buf[..., 3] / 255.0  # A

        # Alpha-composite shape onto layer
        alpha = shape_rgba[..., 3:4]
        layer.pixels[:] = layer.pixels * (1 - alpha) + shape_rgba * alpha
        np.clip(layer.pixels, 0, 1, out=layer.pixels)
