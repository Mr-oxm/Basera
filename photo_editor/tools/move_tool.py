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


# For each resize handle, the *anchor* is the opposite corner / edge.
# The sign pair maps to ``(±half_w, ±half_h)`` in the box-local frame.
_ANCHOR_SIGN: dict[_Handle, tuple[int, int]] = {
    _Handle.TL: (1, 1),
    _Handle.T:  (0, 1),
    _Handle.TR: (-1, 1),
    _Handle.L:  (1, 0),
    _Handle.R:  (-1, 0),
    _Handle.BL: (1, -1),
    _Handle.B:  (0, -1),
    _Handle.BR: (-1, -1),
}


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
        # Reference to the layer being transformed (for mid-drag writes)
        self._active_layer = None
        # Anchor state for rotated resize
        self._anchor_screen: tuple[float, float] = (0.0, 0.0)
        self._anchor_sign: tuple[int, int] = (0, 0)
        self._is_rotated_resize: bool = False

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
            return self._hit_test_rect(-layer.transform_base_w / 2,
                                       -layer.transform_base_h / 2,
                                       layer.transform_base_w,
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
        self._active_layer = layer
        self._is_rotated_resize = False

        if self._mode == _Mode.ROTATE:
            if layer.transform_base_w == 0:
                # First rotation — record the original (un-rotated) dims & pixels
                layer.transform_base_w = layer.width
                layer.transform_base_h = layer.height
                layer._transform_original = layer.pixels.copy()
            else:
                # Subsequent rotation — use pre-rotation original for quality
                if layer._transform_original is not None:
                    self._orig_pixels = layer._transform_original.copy()

        elif self._mode == _Mode.RESIZE:
            if (layer.transform_angle != 0.0
                    and layer.transform_base_w > 0
                    and layer._transform_original is not None):
                # Resizing a rotated layer: work with pre-rotation pixels
                self._is_rotated_resize = True
                self._orig_pixels = layer._transform_original.copy()
                self._orig_width = layer.transform_base_w
                self._orig_height = layer.transform_base_h
                # Compute the anchor (opposite point) in screen coordinates
                self._setup_resize_anchor(layer)
            else:
                # Plain resize — clear any stale rotation state
                layer.transform_angle = 0.0
                layer.transform_base_w = 0
                layer.transform_base_h = 0
                layer._transform_original = None

    def _setup_resize_anchor(self, layer) -> None:
        """Pre-compute the anchor screen position for a rotated resize."""
        lx, ly = layer.position
        cx = lx + layer.width / 2.0
        cy = ly + layer.height / 2.0
        hw = layer.transform_base_w / 2.0
        hh = layer.transform_base_h / 2.0

        asx, asy = _ANCHOR_SIGN.get(self._handle, (0, 0))
        anchor_lx = asx * hw
        anchor_ly = asy * hh

        rad = math.radians(layer.transform_angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        self._anchor_screen = (
            cx + anchor_lx * cos_a + anchor_ly * sin_a,
            cy - anchor_lx * sin_a + anchor_ly * cos_a,
        )
        self._anchor_sign = (asx, asy)

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
        if self._mode == _Mode.ROTATE and self._active_layer is not None:
            self._active_layer.transform_angle += self._current_angle
        self._dragging = False
        self._orig_pixels = None
        self._mode = _Mode.NONE
        self._handle = _Handle.NONE
        self._current_angle = 0.0
        self._active_layer = None
        self._is_rotated_resize = False

    # ------------------------------------------------------------------
    # Resize
    # ------------------------------------------------------------------

    def _apply_resize(self, layer, dx: int, dy: int) -> None:
        if self._orig_pixels is None:
            return

        angle = layer.transform_angle
        is_rot = self._is_rotated_resize

        # Convert screen delta to the local (box) frame when rotated
        if is_rot:
            rad = math.radians(angle)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)
            ldx = dx * cos_a - dy * sin_a
            ldy = dx * sin_a + dy * cos_a
        else:
            ldx, ldy = float(dx), float(dy)

        ow, oh = self._orig_width, self._orig_height
        new_w: float = float(ow)
        new_h: float = float(oh)

        h = self._handle
        # Horizontal (local frame)
        if h in (_Handle.TL, _Handle.L, _Handle.BL):
            new_w = max(4.0, ow - ldx)
        elif h in (_Handle.TR, _Handle.R, _Handle.BR):
            new_w = max(4.0, ow + ldx)

        # Vertical (local frame)
        if h in (_Handle.TL, _Handle.T, _Handle.TR):
            new_h = max(4.0, oh - ldy)
        elif h in (_Handle.BL, _Handle.B, _Handle.BR):
            new_h = max(4.0, oh + ldy)

        sx = new_w / max(ow, 1)
        sy = new_h / max(oh, 1)
        scaled = TransformEngine.scale(self._orig_pixels, sx, sy)

        if is_rot:
            # Re-apply rotation to the scaled original
            rotated = TransformEngine.rotate(scaled, angle, expand=True)
            rh, rw = rotated.shape[:2]

            # Position via anchor constraint: the anchor must stay fixed
            asx, asy = self._anchor_sign
            new_anchor_lx = asx * (new_w / 2.0)
            new_anchor_ly = asy * (new_h / 2.0)
            new_anchor_sx = new_anchor_lx * cos_a + new_anchor_ly * sin_a
            new_anchor_sy = -new_anchor_lx * sin_a + new_anchor_ly * cos_a

            new_cx = self._anchor_screen[0] - new_anchor_sx
            new_cy = self._anchor_screen[1] - new_anchor_sy

            layer.pixels = rotated
            layer.position = (int(new_cx - rw / 2), int(new_cy - rh / 2))
            layer.transform_base_w = max(4, int(new_w))
            layer.transform_base_h = max(4, int(new_h))
            layer._transform_original = scaled
        else:
            # Non-rotated: classic top-left positioning
            ox, oy = self._orig_position
            new_x, new_y = float(ox), float(oy)

            if h in (_Handle.TL, _Handle.L, _Handle.BL):
                new_x = ox + (ow - new_w)
            if h in (_Handle.TL, _Handle.T, _Handle.TR):
                new_y = oy + (oh - new_h)

            layer.pixels = scaled
            layer.position = (int(new_x), int(new_y))

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

        # When pre-rotation pixels exist, rotate from them with the
        # total angle for better quality (avoids compounding rotations).
        if layer._transform_original is not None:
            total = layer.transform_angle + angle_deg
            rotated = TransformEngine.rotate(layer._transform_original, total, expand=True)
        else:
            rotated = TransformEngine.rotate(self._orig_pixels, angle_deg, expand=True)

        rh, rw = rotated.shape[:2]
        layer.pixels = rotated
        layer.position = (int(cx - rw / 2), int(cy - rh / 2))
