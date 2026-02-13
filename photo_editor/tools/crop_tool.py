"""Crop tool — interactive bounding-box crop with Canvas / Layer modes.

The user drags to define or adjust a crop region.  While the crop box
is visible, a dimmed overlay is drawn outside the region.  The user can
resize the box via corner/edge handles or drag the interior to move it.
Pressing *Apply* (Enter) commits the crop, *Cancel* (Escape) discards it.
"""

from __future__ import annotations

from enum import Enum, auto

import numpy as np

from .tool_base import Tool
from ..core.document import Document


class CropMode(Enum):
    """Whether the crop trims the canvas or the active layer."""
    CANVAS = auto()
    LAYER = auto()


# Handle hit-test radius in document pixels (scaled by zoom in the view)
_HANDLE_DOC_PX = 6


class CropTool(Tool):
    """Interactive bounding-box crop with Canvas / Layer modes."""

    def __init__(self) -> None:
        super().__init__("Crop")
        self.mode: CropMode = CropMode.CANVAS

        # Bounding box in document coordinates (x, y, w, h) — None = no box
        self._box: tuple[int, int, int, int] | None = None

        # Interaction state
        self._dragging: bool = False
        self._drag_action: str | None = None   # "new", "move", or handle name
        self._drag_start: tuple[int, int] = (0, 0)
        self._box_at_drag_start: tuple[int, int, int, int] | None = None

        # Callbacks
        self._crop_callback = None          # cb(x, y, w, h, mode)
        self._overlay_callback = None       # cb(box | None)  — update canvas overlay
        self._cancel_callback = None        # cb()

    # ---- Callbacks ----------------------------------------------------------

    def set_crop_callback(self, cb) -> None:
        """cb(x, y, w, h, mode: CropMode) — called when the crop is applied."""
        self._crop_callback = cb

    def set_overlay_callback(self, cb) -> None:
        """cb(box | None) — called whenever the bounding box changes."""
        self._overlay_callback = cb

    def set_cancel_callback(self, cb) -> None:
        """cb() — called when the crop is cancelled."""
        self._cancel_callback = cb

    # ---- Box state ----------------------------------------------------------

    @property
    def box(self) -> tuple[int, int, int, int] | None:
        return self._box

    @box.setter
    def box(self, value: tuple[int, int, int, int] | None) -> None:
        self._box = value
        self._notify_overlay()

    def has_box(self) -> bool:
        return self._box is not None

    def reset_box(self) -> None:
        """Clear the crop box without applying."""
        self._box = None
        self._dragging = False
        self._drag_action = None
        self._notify_overlay()

    # ---- Apply / Cancel -----------------------------------------------------

    def apply(self, doc: Document) -> None:
        """Commit the current crop box."""
        if self._box is None:
            return
        x, y, w, h = self._box
        if w < 1 or h < 1:
            self.reset_box()
            return
        if self._crop_callback is not None:
            self._crop_callback(x, y, w, h, self.mode)
        self.reset_box()

    def cancel(self) -> None:
        """Discard the crop box."""
        self.reset_box()
        if self._cancel_callback is not None:
            self._cancel_callback()

    # ---- Handle helpers -----------------------------------------------------

    def _handle_positions(self) -> list[tuple[str, int, int]]:
        """Return (name, cx, cy) for the 8 resize handles in doc coords."""
        if self._box is None:
            return []
        x, y, w, h = self._box
        return [
            ("TL", x, y),       ("T", x + w // 2, y),       ("TR", x + w, y),
            ("L", x, y + h // 2),                             ("R", x + w, y + h // 2),
            ("BL", x, y + h),   ("B", x + w // 2, y + h),   ("BR", x + w, y + h),
        ]

    def hit_test(self, dx: int, dy: int) -> str | None:
        """Return the handle name, ``'move'``, or ``None``."""
        if self._box is None:
            return None
        for name, hx, hy in self._handle_positions():
            if abs(dx - hx) <= _HANDLE_DOC_PX and abs(dy - hy) <= _HANDLE_DOC_PX:
                return name
        x, y, w, h = self._box
        if x <= dx <= x + w and y <= dy <= y + h:
            return "move"
        return None

    # ---- Tool events --------------------------------------------------------

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        hit = self.hit_test(x, y)
        self._drag_start = (x, y)
        self._dragging = True

        if hit is not None and self._box is not None:
            self._drag_action = hit
            self._box_at_drag_start = self._box
        else:
            # Start drawing a new box
            self._drag_action = "new"
            self._box = (x, y, 0, 0)
            self._box_at_drag_start = self._box

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        if not self._dragging or self._box_at_drag_start is None:
            return

        sx, sy = self._drag_start
        bx, by, bw, bh = self._box_at_drag_start
        dx, dy = x - sx, y - sy
        dw, dh = doc.width, doc.height
        action = self._drag_action

        if action == "new":
            nx = min(sx, x)
            ny = min(sy, y)
            nw = abs(x - sx)
            nh = abs(y - sy)
            self._box = (max(0, nx), max(0, ny), min(nw, dw), min(nh, dh))

        elif action == "move":
            nx = max(0, min(bx + dx, dw - bw))
            ny = max(0, min(by + dy, dh - bh))
            self._box = (nx, ny, bw, bh)

        else:
            # Handle resizing
            nx, ny, nw, nh = bx, by, bw, bh
            if "L" in action:
                nx = min(bx + bw - 1, bx + dx)
                nw = bw - (nx - bx)
            if "R" in action:
                nw = max(1, bw + dx)
            if "T" in action:
                ny = min(by + bh - 1, by + dy)
                nh = bh - (ny - by)
            if "B" in action:
                nh = max(1, bh + dy)
            # Clamp to document bounds
            nx = max(0, nx)
            ny = max(0, ny)
            nw = min(nw, dw - nx)
            nh = min(nh, dh - ny)
            self._box = (nx, ny, max(1, nw), max(1, nh))

        self._notify_overlay()

    def on_release(self, doc: Document, x: int, y: int) -> None:
        if not self._dragging:
            return
        self._dragging = False
        # If the box is too small, discard
        if self._box is not None:
            _, _, w, h = self._box
            if w < 2 or h < 2:
                self.reset_box()
        self._drag_action = None
        self._box_at_drag_start = None

    # ---- Internal -----------------------------------------------------------

    def _notify_overlay(self) -> None:
        if self._overlay_callback is not None:
            self._overlay_callback(self._box)

    # ---- Activation ---------------------------------------------------------

    def auto_box_for_layer(self, doc: Document) -> None:
        """Set the crop box to the active layer's bounding rect.

        If there is no active layer, falls back to the full canvas.
        """
        layer = doc.layers.active_layer
        if layer is not None:
            px, py = layer.position
            lh, lw = layer.pixels.shape[:2]
            self._box = (px, py, lw, lh)
        else:
            self._box = (0, 0, doc.width, doc.height)
        self._notify_overlay()

    def deactivate(self) -> None:
        """Clear the crop box when switching away from the tool."""
        self.reset_box()
        super().deactivate()
