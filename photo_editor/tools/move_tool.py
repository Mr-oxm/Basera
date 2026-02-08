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
        bbox = self._bbox(doc)
        if bbox is None:
            return _Mode.NONE, _Handle.NONE

        bx, by, bw, bh = bbox
        m = self.HANDLE_MARGIN
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
        self._dragging = False
        self._orig_pixels = None
        self._mode = _Mode.NONE
        self._handle = _Handle.NONE

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
        angle_deg = math.degrees(a1 - a0)

        rotated = TransformEngine.rotate(self._orig_pixels, angle_deg, expand=True)
        rh, rw = rotated.shape[:2]
        layer.pixels = rotated
        layer.position = (int(cx - rw / 2), int(cy - rh / 2))
