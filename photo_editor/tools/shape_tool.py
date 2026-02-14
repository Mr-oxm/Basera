
import math
from .tool_base import Tool
from ..core.document import Document
from ..core.enums import LayerType
from ..vector.geometry import Vec2
from ..vector.path import VectorPath, SubPath, PathNode, HandleMode
from ..vector.scene import VectorObject, VectorLayer
from ..vector.style import VectorStyle, VectorFill, VectorStroke, SolidPaint
from ..vector.rasterizer import rasterize_vector_layer_tight

class ShapeTool(Tool):
    """Draw geometric shapes as VectorObjects."""

    def __init__(self) -> None:
        super().__init__("Shape")
        self.shape_type: str = "rect"  # "rect" | "ellipse" | "line" | "polygon"
        self.fill_color: list[float] | None = [0.0, 0.5, 1.0, 1.0]
        self.stroke_color: list[float] | None = [0.0, 0.0, 0.0, 1.0]
        self.stroke_width: float = 2.0
        self.polygon_sides: int = 5

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

        sx, sy = float(self._start_x), float(self._start_y)
        ex, ey = float(x), float(y)
        
        if abs(ex - sx) < 2 and abs(ey - sy) < 2:
            return

        # 1. Generate VectorPath based on shape type
        path = self._create_path(sx, sy, ex, ey)
        if not path:
            return

        # 2. Create Style
        fills = []
        if self.fill_color is not None:
            # Assuming fill_color is [r, g, b, a]
            c = self.fill_color
            # Opacity is c[3]
            paint = SolidPaint(color=(c[0], c[1], c[2]))
            fills.append(VectorFill(paint, opacity=c[3]))
            
        strokes = []
        if self.stroke_color is not None and self.stroke_width > 0:
            c = self.stroke_color
            paint = SolidPaint(color=(c[0], c[1], c[2]))
            strokes.append(VectorStroke(paint, width=self.stroke_width, opacity=c[3]))

        style = VectorStyle(fills=fills, strokes=strokes)

        # 3. Create VectorObject
        obj = VectorObject(name=f"{self.shape_type.capitalize()}", path=path, style=style)
        obj.selected = True

        # 4. Add to Vector Layer (ensure one exists)
        vl = self._ensure_vector_layer(doc)
        vl.add(obj)

        doc.save_snapshot("Draw Shape")
        
        # 5. Force update bounds and pixels
        rasterize_vector_layer_tight(doc, force=True)

    def _ensure_vector_layer(self, doc: Document) -> VectorLayer:
        layer = doc.layers.active_layer
        if layer is None or layer.layer_type != LayerType.SHAPE:
            layer = doc.add_vector_layer(name="Shapes")
        
        vl = getattr(layer, "_vector_data", None)
        if vl is None:
            vl = VectorLayer()
            layer._vector_data = vl
        return vl

    def _create_path(self, x0: float, y0: float, x1: float, y1: float) -> VectorPath | None:
        # Normalize bounds
        left, right = min(x0, x1), max(x0, x1)
        top, bottom = min(y0, y1), max(y0, y1)
        w, h = right - left, bottom - top
        
        if self.shape_type == "rect":
            # TL -> TR -> BR -> BL
            nodes = [
                PathNode(Vec2(left, top), mode=HandleMode.SHARP),
                PathNode(Vec2(right, top), mode=HandleMode.SHARP),
                PathNode(Vec2(right, bottom), mode=HandleMode.SHARP),
                PathNode(Vec2(left, bottom), mode=HandleMode.SHARP),
            ]
            sp = SubPath(nodes, closed=True)
            return VectorPath([sp])
            
        elif self.shape_type == "ellipse":
            # Approximation with 4 bezier curves (kappa = 0.55228)
            cx, cy = left + w/2, top + h/2
            rx, ry = w/2, h/2
            k = 0.55228475
            ox, oy = rx * k, ry * k
            
            # 4 points: Right, Bottom, Left, Top
            # 0: Right (cx+rx, cy)
            p0 = PathNode(Vec2(cx + rx, cy), mode=HandleMode.SMOOTH)
            p0.in_handle = Vec2(cx + rx, cy - oy)
            p0.out_handle = Vec2(cx + rx, cy + oy)
            
            # 1: Bottom (cx, cy+ry)
            p1 = PathNode(Vec2(cx, cy + ry), mode=HandleMode.SMOOTH)
            p1.in_handle = Vec2(cx + ox, cy + ry)
            p1.out_handle = Vec2(cx - ox, cy + ry)
            
            # 2: Left (cx-rx, cy)
            p2 = PathNode(Vec2(cx - rx, cy), mode=HandleMode.SMOOTH)
            p2.in_handle = Vec2(cx - rx, cy + oy)
            p2.out_handle = Vec2(cx - rx, cy - oy)
            
            # 3: Top (cx, cy-ry)
            p3 = PathNode(Vec2(cx, cy - ry), mode=HandleMode.SMOOTH)
            p3.in_handle = Vec2(cx - ox, cy - ry)
            p3.out_handle = Vec2(cx + ox, cy - ry)
            
            sp = SubPath([p0, p1, p2, p3], closed=True)
            return VectorPath([sp])

        elif self.shape_type == "line":
            nodes = [
                PathNode(Vec2(x0, y0), mode=HandleMode.SHARP),
                PathNode(Vec2(x1, y1), mode=HandleMode.SHARP)
            ]
            sp = SubPath(nodes, closed=False)
            return VectorPath([sp])

        elif self.shape_type == "polygon":
             cx, cy = left + w/2, top + h/2
             rx, ry = w/2, h/2
             n = max(3, self.polygon_sides)
             import numpy as np # Keep locally if needed or rely on math
             nodes = []
             # Start angle -90 deg
             start_angle = -math.pi / 2
             for i in range(n):
                 angle = start_angle + (2 * math.pi * i) / n
                 px = cx + rx * math.cos(angle)
                 py = cy + ry * math.sin(angle)
                 nodes.append(PathNode(Vec2(px, py), mode=HandleMode.SHARP))
             
             sp = SubPath(nodes, closed=True)
             return VectorPath([sp])
             
        return None

