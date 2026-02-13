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
        self._start_x, self._start_y = x, y
        self._dragging = True

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        pass  # Live preview could be rendered here

    def on_release(self, doc: Document, x: int, y: int) -> None:
        if not self._dragging:
            return
        self._dragging = False

        sx, sy = self._start_x, self._start_y
        ex, ey = x, y
        # Determine bounding rect of the shape in document coords
        rx, ry = min(sx, ex), min(sy, ey)
        rw, rh = abs(ex - sx), abs(ey - sy)
        if rw < 2 or rh < 2:
            return

        # Add some padding for strokes
        pad = self.stroke_width + 2
        lx, ly = max(0, rx - pad), max(0, ry - pad)
        lw, lh = rw + pad * 2, rh + pad * 2

        # Create a new layer for the shape
        from ..core.layer import Layer
        from ..core.enums import LayerType
        layer = Layer(name=f"Shape", width=lw, height=lh,
                      layer_type=LayerType.RASTER)
        layer.position = (lx, ly)
        # pixels start as transparent zeros — perfect

        # Render shape into a BGRA uint8 buffer then convert to float RGBA
        buf = np.zeros((lh, lw, 4), dtype=np.uint8)
        # Convert document coords to layer-local coords
        draw_sx, draw_sy = sx - lx, sy - ly
        draw_ex, draw_ey = ex - lx, ey - ly
        draw_fn = {
            "rect": self._draw_rect,
            "ellipse": self._draw_ellipse,
            "line": self._draw_line,
            "polygon": self._draw_polygon,
        }.get(self.shape_type, self._draw_rect)
        draw_fn(buf, draw_sx, draw_sy, draw_ex, draw_ey)

        # Convert BGRA uint8 → RGBA float32
        shape_rgba = np.zeros((lh, lw, 4), dtype=np.float32)
        shape_rgba[..., 0] = buf[..., 2] / 255.0  # R
        shape_rgba[..., 1] = buf[..., 1] / 255.0  # G
        shape_rgba[..., 2] = buf[..., 0] / 255.0  # B
        shape_rgba[..., 3] = buf[..., 3] / 255.0  # A

        layer.pixels = shape_rgba
        doc.layers.add(layer)
        doc.save_snapshot("Draw Shape")
        doc.mark_dirty()
