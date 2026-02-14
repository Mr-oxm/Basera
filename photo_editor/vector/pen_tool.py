"""Pen Tool — interactive Bézier path creation.

Behaviour model (matching Affinity Designer / Illustrator):
* **Click** — place a sharp anchor (no handles).
* **Click + drag** — place a smooth anchor, dragging out symmetric handles.
* **Click on first node** — close the path.
* **Click on last node** — continue extending the path.
* **Escape / double-click** — finish the open path.

The tool operates on a ``VectorObject`` attached to the active layer.
While drawing, a *preview* sub-path is maintained that shows the
uncommitted segment.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ..tools.tool_base import Tool
from ..core.enums import LayerType

from ..vector.geometry import Vec2, AffineTransform
from ..vector.path import (
    VectorPath, SubPath, PathNode, HandleMode,
)
from ..vector.scene import VectorObject, VectorLayer
from ..vector.style import VectorStyle, VectorFill, VectorStroke, SolidPaint

if TYPE_CHECKING:
    from ..core.document import Document

__all__ = ["PenTool"]


class PenTool(Tool):
    """Interactive cubic Bézier path creation tool."""

    def __init__(self) -> None:
        super().__init__("Pen")
        # Current drawing state
        self._drawing = False
        self._current_object: VectorObject | None = None
        self._current_subpath: SubPath | None = None
        self._drag_start: Vec2 | None = None
        self._dragging = False
        self._last_node: PathNode | None = None
        # Style for new paths
        self.fill_color: tuple[float, float, float, float] = (0.8, 0.8, 0.8, 1.0)
        self.stroke_color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
        self.stroke_width: float = 2.0
        # Preview state
        self.preview_point: Vec2 | None = None  # Mouse position for live preview

    # ---- Tool interface -----------------------------------------------------

    def on_press(self, doc: "Document", x: int, y: int, pressure: float = 1.0) -> None:
        pos = Vec2(float(x), float(y))
        self._drag_start = pos
        self._dragging = False

        if not self._drawing:
            self._start_new_path(doc, None, pos)
        else:
            # Check if clicking on the first node (close path)
            if self._current_subpath and self._current_subpath.node_count >= 3:
                first_node = self._current_subpath.nodes[0]
                if pos.distance_to(first_node.position) < 8.0:
                    self._close_path(doc)
                    return
            # Add new node
            self._add_node(pos)

    def on_move(self, doc: "Document", x: int, y: int, pressure: float = 1.0) -> None:
        pos = Vec2(float(x), float(y))
        self.preview_point = pos

        if self._drag_start is not None:
            dist = pos.distance_to(self._drag_start)
            if dist > 3.0:
                self._dragging = True

        if self._dragging and self._last_node is not None:
            # Drag out handles for the current node
            offset = pos - self._last_node.position
            self._last_node.out_handle = pos
            self._last_node.in_handle = self._last_node.position - offset
            self._last_node.mode = HandleMode.SYMMETRIC
            if self._current_subpath:
                self._current_subpath.invalidate()
            if self._current_object:
                self._current_object.invalidate()

    def on_release(self, doc: "Document", x: int, y: int) -> None:
        if self._dragging and self._last_node is not None:
            pos = Vec2(float(x), float(y))
            offset = pos - self._last_node.position
            self._last_node.out_handle = pos
            self._last_node.in_handle = self._last_node.position - offset
            self._last_node.mode = HandleMode.SYMMETRIC
            if self._current_subpath:
                self._current_subpath.invalidate()
            if self._current_object:
                self._current_object.invalidate()

        self._drag_start = None
        self._dragging = False

    def deactivate(self) -> None:
        if self._drawing:
            self._finish_path()
        super().deactivate()

    # ---- Path creation logic ------------------------------------------------

    def _start_new_path(self, doc: "Document", vl: VectorLayer, pos: Vec2) -> None:
        """Begin a new vector path on a fresh vector layer."""
        # Auto-create a new vector layer for each path
        layer = doc.add_vector_layer(name="Pen Path")
        vl = layer._vector_data
        doc.save_snapshot("Pen: new path")

        node = PathNode(position=pos, mode=HandleMode.SHARP)
        sp = SubPath([node], closed=False)
        path = VectorPath([sp])
        style = VectorStyle(
            fills=[VectorFill(SolidPaint(self.fill_color))],
            strokes=[VectorStroke(SolidPaint(self.stroke_color), width=self.stroke_width)],
        )
        obj = VectorObject(name="Path", path=path, style=style)
        vl.add(obj)
        obj.selected = True

        self._current_object = obj
        self._current_subpath = sp
        self._last_node = node
        self._drawing = True

    def _add_node(self, pos: Vec2) -> None:
        """Add a new anchor point to the current path."""
        node = PathNode(position=pos, mode=HandleMode.SHARP)
        if self._current_subpath:
            self._current_subpath.add_node(node)
        self._last_node = node
        if self._current_object:
            self._current_object.invalidate()

    def _close_path(self, doc: "Document") -> None:
        """Close the current sub-path and finish drawing."""
        if self._current_subpath:
            self._current_subpath.closed = True
            self._current_subpath.invalidate()
        if self._current_object:
            self._current_object.invalidate()
        self._finish_path()
        # Rasterise to layer pixels
        self._rasterize_to_layer(doc)

    def _finish_path(self) -> None:
        """End the current drawing session."""
        self._drawing = False
        self._current_object = None
        self._current_subpath = None
        self._last_node = None
        self._drag_start = None
        self._dragging = False
        self.preview_point = None

    def finish_open_path(self, doc: "Document") -> None:
        """Public method called by key handler (Escape/Enter) to finish open path."""
        if self._drawing:
            if self._current_object:
                self._current_object.invalidate()
            self._finish_path()
            self._rasterize_to_layer(doc)

    @staticmethod
    def _rasterize_to_layer(doc: "Document") -> None:
        """Update the layer's pixel cache and boundaries from vector data (tight bbox)."""
        from .rasterizer import rasterize_vector_layer_tight
        # Force re-rasterize to update layer position and size
        rasterize_vector_layer_tight(doc, force=True)

    # ---- State queries for UI overlay ---------------------------------------

    @property
    def is_drawing(self) -> bool:
        return self._drawing

    @property
    def current_path(self) -> VectorPath | None:
        if self._current_object:
            return self._current_object.effective_path()
        return None

    @property
    def current_nodes(self) -> list[PathNode]:
        if self._current_subpath:
            return self._current_subpath.nodes
        return []


# ---------------------------------------------------------------------------
#  Helper
# ---------------------------------------------------------------------------

def _ensure_vector_layer(doc: "Document") -> VectorLayer:
    """Ensure the active layer has vector data attached."""
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
