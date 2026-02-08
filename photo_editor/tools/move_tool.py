"""Move tool — select, move, resize, and rotate the active layer via bounding-box handles."""

from __future__ import annotations

import math
from enum import Enum, auto

import numpy as np

from .tool_base import Tool
from ..core.document import Document
from ..transforms.transform_engine import TransformEngine


class _Mode(Enum):
    NONE = auto()
    MOVE = auto()
    RESIZE = auto()
    ROTATE = auto()


class _Handle(Enum):
    NONE = auto()
    TL = auto()
    T = auto()
    TR = auto()
    L = auto()
    R = auto()
    BL = auto()
    B = auto()
    BR = auto()


class MoveTool(Tool):
    """Click-drag to move; drag handles to resize; drag outside box to rotate."""

    HANDLE_MARGIN = 10  # hit-test radius in document pixels

    def __init__(self) -> None:
        super().__init__("Move")
        self._mode = _Mode.NONE
        self._handle = _Handle.NONE
        self._start_x: int = 0
        self._start_y: int = 0
        self._orig_position: tuple[int, int] = (0, 0)
        self._orig_pixels: np.ndarray | None = None
        self._orig_width: int = 0
        self._orig_height: int = 0
        self._dragging: bool = False
        self._current_angle: float = 0.0
        # Reference to the layer being rotated (for mid-drag writes)
        self._active_layer = None

    # ------------------------------------------------------------------
    # Public query (used by MainWindow for bounding-box overlay)
    # ------------------------------------------------------------------

    def rotation_info_for(self, layer) -> tuple[int, int, float] | None:
        """Return ``(base_w, base_h, total_angle)`` for *layer*.

        The total angle includes any mid-drag rotation that has not yet
        been committed.  Returns ``None`` when the layer has no rotation.
        """
        if layer is None:
            return None
        extra = self._current_angle if (layer is self._active_layer) else 0.0
        total = layer.transform_angle + extra
        if total != 0.0 and layer.transform_base_w > 0:
            return (layer.transform_base_w, layer.transform_base_h, total)
        return None

    # ------------------------------------------------------------------
    # Hit testing
    # ------------------------------------------------------------------

    @staticmethod
    def _bbox(doc: Document) -> tuple[int, int, int, int] | None:
        """Return (x, y, w, h) bounding box of the active layer in doc coords."""
        layer = doc.layers.active_layer
        if layer is None:
            return None
        lx, ly = layer.position
        return (lx, ly, layer.width, layer.height)

    def _hit_test(self, doc: Document, x: int, y: int) -> tuple[_Mode, _Handle]:
        layer = doc.layers.active_layer
        if layer is None:
            return _Mode.NONE, _Handle.NONE

        total_angle = layer.transform_angle + self._current_angle

        # When there is accumulated rotation, test against the rotated
        # (original-sized) box by inverse-rotating the click point.
        if total_angle != 0.0 and layer.transform_base_w > 0:
            lx, ly = layer.position
            cx = lx + layer.width / 2
            cy = ly + layer.height / 2
            rad = math.radians(total_angle)
            dx, dy = x - cx, y - cy
            # Inverse of the QPainter rotation applied to the box
            rx = dx * math.cos(rad) - dy * math.sin(rad)
            ry = dx * math.sin(rad) + dy * math.cos(rad)
            hw = layer.transform_base_w / 2
            hh = layer.transform_base_h / 2
            return self._hit_test_rect(-hw, -hh, layer.transform_base_w,
                                       layer.transform_base_h, rx, ry)

        # Normal (no rotation) hit-test on current layer bounds
        bbox = self._bbox(doc)
        if bbox is None:
            return _Mode.NONE, _Handle.NONE
        bx, by, bw, bh = bbox
        return self._hit_test_rect(bx, by, bw, bh, x, y)

    @staticmethod
    def _hit_test_rect(bx: float, by: float, bw: float, bh: float,
                       x: float, y: float) -> tuple[_Mode, _Handle]:
        """Hit-test a point against a rectangle and its handles."""
        m = MoveTool.HANDLE_MARGIN
        mx, my = bx + bw / 2, by + bh / 2

        handles = [
            (_Handle.TL, bx, by),
            (_Handle.T, mx, by),
            (_Handle.TR, bx + bw, by),
            (_Handle.L, bx, my),
            (_Handle.R, bx + bw, my),
            (_Handle.BL, bx, by + bh),
            (_Handle.B, mx, by + bh),
            (_Handle.BR, bx + bw, by + bh),
        ]
        for hid, hx, hy in handles:
            if abs(x - hx) <= m and abs(y - hy) <= m:
                return _Mode.RESIZE, hid

        if bx <= x <= bx + bw and by <= y <= by + bh:
            return _Mode.MOVE, _Handle.NONE

        return _Mode.ROTATE, _Handle.NONE

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return

        self._mode, self._handle = self._hit_test(doc, x, y)
        if self._mode == _Mode.NONE:
            return

        label = {_Mode.MOVE: "Move", _Mode.RESIZE: "Resize", _Mode.ROTATE: "Rotate"}
        doc.save_snapshot(label.get(self._mode, "Transform"))

        self._start_x, self._start_y = x, y
        self._orig_position = layer.position
        self._orig_pixels = layer.pixels.copy()
        self._orig_width = layer.width
        self._orig_height = layer.height
        self._dragging = True

        # Rotation tracking
        if self._mode == _Mode.ROTATE and self._base_width == 0:
            # First rotation — record the original (un-rotated) dimensions
            self._base_width = layer.width
            self._base_height = layer.height
        elif self._mode == _Mode.RESIZE:
            # Resize resets accumulated rotation (shape fundamentally changes)
            self._accumulated_angle = 0.0
            self._base_width = 0
            self._base_height = 0

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        if not self._dragging:
            return
        layer = doc.layers.active_layer
        if layer is None:
            return

        dx = x - self._start_x
        dy = y - self._start_y

        if self._mode == _Mode.MOVE:
            ox, oy = self._orig_position
            layer.position = (ox + dx, oy + dy)

        elif self._mode == _Mode.RESIZE:
            self._apply_resize(layer, dx, dy)

        elif self._mode == _Mode.ROTATE:
            self._apply_rotate(layer, x, y)

    def on_release(self, doc: Document, x: int, y: int) -> None:
        if self._mode == _Mode.ROTATE:
            self._accumulated_angle += self._current_angle
        self._dragging = False
        self._orig_pixels = None
        self._mode = _Mode.NONE
        self._handle = _Handle.NONE
        self._current_angle = 0.0

    # ------------------------------------------------------------------
    # Resize
    # ------------------------------------------------------------------

    def _apply_resize(self, layer, dx: int, dy: int) -> None:
        if self._orig_pixels is None:
            return

        ow, oh = self._orig_width, self._orig_height
        ox, oy = self._orig_position
        new_x, new_y = ox, oy
        new_w, new_h = ow, oh

        h = self._handle
        # Horizontal
        if h in (_Handle.TL, _Handle.L, _Handle.BL):
            new_w = max(4, ow - dx)
            new_x = ox + (ow - new_w)
        elif h in (_Handle.TR, _Handle.R, _Handle.BR):
            new_w = max(4, ow + dx)

        # Vertical
        if h in (_Handle.TL, _Handle.T, _Handle.TR):
            new_h = max(4, oh - dy)
            new_y = oy + (oh - new_h)
        elif h in (_Handle.BL, _Handle.B, _Handle.BR):
            new_h = max(4, oh + dy)

        sx = new_w / max(ow, 1)
        sy = new_h / max(oh, 1)

        scaled = TransformEngine.scale(self._orig_pixels, sx, sy)
        layer.pixels = scaled
        layer.position = (new_x, new_y)

    # ------------------------------------------------------------------
    # Rotate
    # ------------------------------------------------------------------

    def _apply_rotate(self, layer, x: int, y: int) -> None:
        if self._orig_pixels is None:
            return

        ox, oy = self._orig_position
        ow, oh = self._orig_width, self._orig_height
        cx = ox + ow / 2
        cy = oy + oh / 2

        a0 = math.atan2(self._start_y - cy, self._start_x - cx)
        a1 = math.atan2(y - cy, x - cx)
        # Negate: screen coords are y-down, so atan2 gives the
        # opposite sign from the visual rotation direction.
        angle_deg = -math.degrees(a1 - a0)
        self._current_angle = angle_deg

        rotated = TransformEngine.rotate(self._orig_pixels, angle_deg, expand=True)
        rh, rw = rotated.shape[:2]
        layer.pixels = rotated
        layer.position = (int(cx - rw / 2), int(cy - rh / 2))
