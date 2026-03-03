"""Vector Shape Tool — non-destructive parametric shape creation.

Unlike the existing raster ``ShapeTool``, this tool creates live
``VectorObject`` instances backed by ``ShapePrimitive`` data.
Parameters (corner radius, number of sides, inner radius, etc.)
remain editable after creation.

Supports all 15 shape primitives:
  Rectangle, Ellipse, Polygon, Star, Line, Triangle, Arrow, Heart,
  Diamond, Cross, Ring, Trapezoid, Parallelogram, Crescent, SpeechBubble
"""

from __future__ import annotations

import math
import time
from enum import Enum, auto
from typing import TYPE_CHECKING

from ..tools.tool_base import Tool
from ..core.enums import LayerType

from ..vector.geometry import Vec2, AffineTransform
from ..vector.shapes import (
    RectangleShape, EllipseShape, PolygonShape, StarShape, LineShape,
    TriangleShape, ArrowShape, HeartShape, DiamondShape, CrossShape,
    RingShape, TrapezoidShape, ParallelogramShape, CrescentShape,
    SpeechBubbleShape,
)
from ..vector.scene import VectorObject, VectorLayer
from ..vector.style import (
    VectorStyle, VectorFill, VectorStroke, SolidPaint,
)

if TYPE_CHECKING:
    from ..core.document import Document

__all__ = ["VectorShapeTool", "VectorShapeType"]


class VectorShapeType(Enum):
    RECTANGLE = auto()
    ELLIPSE = auto()
    POLYGON = auto()
    STAR = auto()
    LINE = auto()
    TRIANGLE = auto()
    ARROW = auto()
    HEART = auto()
    DIAMOND = auto()
    CROSS = auto()
    RING = auto()
    TRAPEZOID = auto()
    PARALLELOGRAM = auto()
    CRESCENT = auto()
    SPEECH_BUBBLE = auto()


class VectorShapeTool(Tool):
    """Create live-parameter vector shapes by click-drag."""

    def __init__(self) -> None:
        super().__init__("Vector Shape")
        self.shape_type: VectorShapeType = VectorShapeType.RECTANGLE
        # Style defaults
        self.fill_color: tuple[float, float, float, float] = (0.7, 0.7, 0.9, 1.0)
        self.stroke_color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
        self.stroke_width: float = 2.0
        # Shape parameters
        self.corner_radius: float = 0.0
        self.polygon_sides: int = 6
        self.star_points: int = 5
        self.star_inner_ratio: float = 0.5
        self.arrow_head_length: float = 0.4
        self.arrow_shaft_width: float = 0.4
        self.cross_arm_ratio: float = 0.33
        self.ring_thickness: float = 0.3
        self.trapezoid_top_ratio: float = 0.6
        self.parallelogram_skew: float = 0.25
        self.crescent_offset: float = 0.35
        self.speech_tail_position: float = 0.3
        # Throttle rasterize during drag (~12 fps)
        self._last_rasterize_time: float = 0.0
        self._rasterize_interval: float = 0.08
        # Constrain to equal aspect (Shift behaviour)
        self.constrain_aspect: bool = False
        # State
        self._drag_start: Vec2 | None = None
        self._drag_current: Vec2 | None = None
        self._current_object: VectorObject | None = None

    # ---- Tool interface -----------------------------------------------------

    def on_press(self, doc: "Document", x: int, y: int, pressure: float = 1.0) -> None:
        self._drag_start = Vec2(float(x), float(y))
        self._drag_current = self._drag_start

        # Auto-create a new vector layer for each shape
        layer = doc.add_vector_layer(name=f"{self.shape_type.name.capitalize()} Shape")
        vl = layer._vector_data
        doc.save_snapshot(f"Shape: create {self.shape_type.name.lower()}")
        # Create placeholder object
        shape = self._make_shape(1.0, 1.0)
        
        import copy
        fill_paint = copy.deepcopy(getattr(self, "fill_paint", None))
        if fill_paint is None:
            fill_paint = SolidPaint(self.fill_color)
        stroke_paint = copy.deepcopy(getattr(self, "stroke_paint", None))
        if stroke_paint is None:
            stroke_paint = SolidPaint(self.stroke_color)

        style = VectorStyle(
            fills=[VectorFill(fill_paint)],
            strokes=[VectorStroke(stroke_paint, width=self.stroke_width)],
        )
        obj = VectorObject(
            name=self.shape_type.name.capitalize(),
            shape=shape,
            style=style,
            transform=AffineTransform.translation(float(x), float(y)),
        )
        vl.add(obj)
        obj.selected = True
        self._current_object = obj

    def on_move(self, doc: "Document", x: int, y: int, pressure: float = 1.0) -> None:
        if self._drag_start is None or self._current_object is None:
            return
        pos = Vec2(float(x), float(y))
        self._drag_current = pos
        dx = pos.x - self._drag_start.x
        dy = pos.y - self._drag_start.y

        if self.constrain_aspect:
            side = max(abs(dx), abs(dy))
            dx = math.copysign(side, dx)
            dy = math.copysign(side, dy)

        w = abs(dx)
        h = abs(dy)
        if w < 1.0:
            w = 1.0
        if h < 1.0:
            h = 1.0

        # Update shape parameters
        shape = self._make_shape(w, h)
        self._current_object.shape = shape
        self._current_object.invalidate()

        # Position: center of the drag rectangle
        cx = self._drag_start.x + dx * 0.5
        cy = self._drag_start.y + dy * 0.5
        self._current_object.transform = AffineTransform.translation(cx, cy)

        # Live preview — rasterise (throttled)
        self._throttled_rasterize(doc)

    def on_release(self, doc: "Document", x: int, y: int) -> None:
        if self._current_object is not None:
            self._rasterize_to_layer(doc)
        self._drag_start = None
        self._drag_current = None
        self._current_object = None

    # ---- Shape factories ----------------------------------------------------

    def _make_shape(self, w: float, h: float):
        st = self.shape_type
        if st == VectorShapeType.RECTANGLE:
            r = self.corner_radius
            return RectangleShape(width=w, height=h, corner_radii=(r, r, r, r))
        elif st == VectorShapeType.ELLIPSE:
            return EllipseShape(rx=w * 0.5, ry=h * 0.5)
        elif st == VectorShapeType.POLYGON:
            radius = min(w, h) * 0.5
            return PolygonShape(sides=max(3, self.polygon_sides), radius=radius)
        elif st == VectorShapeType.STAR:
            outer = min(w, h) * 0.5
            inner = outer * self.star_inner_ratio
            return StarShape(points=max(3, self.star_points), outer_radius=outer, inner_radius=inner)
        elif st == VectorShapeType.LINE:
            return LineShape(start=Vec2(-w * 0.5, 0.0), end=Vec2(w * 0.5, 0.0))
        elif st == VectorShapeType.TRIANGLE:
            return TriangleShape(width=w, height=h)
        elif st == VectorShapeType.ARROW:
            return ArrowShape(
                width=w, height=h,
                head_length=self.arrow_head_length,
                shaft_width=self.arrow_shaft_width,
            )
        elif st == VectorShapeType.HEART:
            return HeartShape(width=w, height=h)
        elif st == VectorShapeType.DIAMOND:
            return DiamondShape(width=w, height=h)
        elif st == VectorShapeType.CROSS:
            return CrossShape(width=w, height=h, arm_ratio=self.cross_arm_ratio)
        elif st == VectorShapeType.RING:
            return RingShape(rx=w * 0.5, ry=h * 0.5, thickness=self.ring_thickness)
        elif st == VectorShapeType.TRAPEZOID:
            return TrapezoidShape(width=w, height=h, top_ratio=self.trapezoid_top_ratio)
        elif st == VectorShapeType.PARALLELOGRAM:
            return ParallelogramShape(width=w, height=h, skew=self.parallelogram_skew)
        elif st == VectorShapeType.CRESCENT:
            return CrescentShape(radius=min(w, h) * 0.5, offset=self.crescent_offset)
        elif st == VectorShapeType.SPEECH_BUBBLE:
            return SpeechBubbleShape(
                width=w, height=h,
                corner_radius=self.corner_radius,
                tail_position=self.speech_tail_position,
            )
        return RectangleShape(width=w, height=h)

    # ---- Helpers ------------------------------------------------------------

    @staticmethod
    def _ensure_vector_layer(doc: "Document") -> VectorLayer:
        layer = doc.layers.active_layer
        if layer is None:
            raise RuntimeError("No active layer")
        if layer.layer_type != LayerType.SHAPE:
            layer.layer_type = LayerType.SHAPE
        vl = getattr(layer, "_vector_data", None)
        if vl is None:
            vl = VectorLayer()
            layer._vector_data = vl  # type: ignore[attr-defined]
        return vl

    @staticmethod
    def _rasterize_to_layer(doc: "Document") -> None:
        from .rasterizer import rasterize_vector_layer_tight
        rasterize_vector_layer_tight(doc)

    def _throttled_rasterize(self, doc: "Document") -> None:
        """Rasterize at most once per ``_rasterize_interval`` during drag."""
        now = time.monotonic()
        if now - self._last_rasterize_time >= self._rasterize_interval:
            self._rasterize_to_layer(doc)
            self._last_rasterize_time = now

    # ---- State queries for overlay ------------------------------------------

    @property
    def is_drawing(self) -> bool:
        return self._current_object is not None

    @property
    def drag_rect(self) -> tuple[Vec2, Vec2] | None:
        """Return (start, current) of the drag for overlay rendering."""
        if self._drag_start and self._drag_current and self._current_object:
            return (self._drag_start, self._drag_current)
        return None
