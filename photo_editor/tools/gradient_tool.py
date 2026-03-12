"""Gradient tool — real-time preview, interactive Affinity-style handles.

Draw a gradient by clicking and dragging.  While dragging the gradient
is rendered live on the canvas.  On release a control line with colour
stop circles appears; the endpoints can then be dragged to reshape the
gradient interactively.
"""

from __future__ import annotations

import math
from typing import Callable

import numpy as np

from .tool_base import Tool
from ..core.color import Color, GradientStop
from ..core.document import Document


class GradientTool(Tool):
    """Draws a gradient with real-time preview and interactive handles."""

    HANDLE_RADIUS: int = 14  # document-pixel hit radius

    def __init__(self) -> None:
        super().__init__("Gradient")

        # ---- configurable properties (synced from properties bar) -----------
        self.gradient_type: str = "linear"   # linear | radial | conical | diamond
        self.opacity: float = 1.0

        self._stops: list[GradientStop] = [
            GradientStop(0.0, Color.black()),
            GradientStop(1.0, Color.white()),
        ]

        # ---- drag state -----------------------------------------------------
        self._start_x: int = 0
        self._start_y: int = 0
        self._end_x: int = 0
        self._end_y: int = 0
        self._dragging: bool = False

        # ---- handle-editing state -------------------------------------------
        self._editing: bool = False
        self._dragging_handle: str | None = None   # "start" / "end" / None
        self._handle_drag_origin: tuple[int, int, int, int] | None = None
        self._saved_pixels: np.ndarray | None = None
        self._target_layer = None
        self._layer_pos: tuple[int, int] = (0, 0)

        # ---- callbacks (set by main_window) ---------------------------------
        self._preview_cb: Callable[[], None] | None = None
        self._handles_cb: Callable | None = None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def stops(self) -> list[GradientStop]:
        return list(self._stops)

    @stops.setter
    def stops(self, value: list[GradientStop]) -> None:
        self._stops = sorted(value, key=lambda s: s.position)
        if self._editing:
            self._reapply_gradient()

    @property
    def is_editing(self) -> bool:
        return self._editing

    def set_preview_callback(self, cb: Callable[[], None] | None) -> None:
        self._preview_cb = cb

    def set_handles_callback(self, cb: Callable | None) -> None:
        self._handles_cb = cb

    def reverse_gradient(self) -> None:
        """Reverse the gradient stop order."""
        self._stops = [
            GradientStop(1.0 - s.position, s.color)
            for s in reversed(self._stops)
        ]
        if self._editing:
            self._reapply_gradient()

    # ------------------------------------------------------------------
    # Gradient generators
    # ------------------------------------------------------------------

    @staticmethod
    def _linear_map(h: int, w: int, x0: int, y0: int,
                    x1: int, y1: int) -> np.ndarray:
        dx, dy = float(x1 - x0), float(y1 - y0)
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            return np.zeros((h, w), dtype=np.float32)
        yy, xx = np.mgrid[0:h, 0:w]
        t = ((xx - x0) * dx + (yy - y0) * dy) / length_sq
        return np.clip(t, 0.0, 1.0).astype(np.float32)

    @staticmethod
    def _radial_map(h: int, w: int, cx: int, cy: int,
                    ex: int, ey: int) -> np.ndarray:
        radius = max(1.0, np.hypot(float(ex - cx), float(ey - cy)))
        yy, xx = np.mgrid[0:h, 0:w]
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2).astype(np.float32)
        return np.clip(dist / radius, 0.0, 1.0)

    @staticmethod
    def _conical_map(h: int, w: int, cx: int, cy: int,
                     ex: int, ey: int) -> np.ndarray:
        base = math.atan2(ey - cy, ex - cx)
        yy, xx = np.mgrid[0:h, 0:w]
        angles = np.arctan2(yy - cy, xx - cx).astype(np.float32)
        t = (angles - base) / (2.0 * math.pi)
        return np.mod(t, 1.0).astype(np.float32)

    @staticmethod
    def _diamond_map(h: int, w: int, cx: int, cy: int,
                     ex: int, ey: int) -> np.ndarray:
        radius = max(1.0, float(abs(ex - cx) + abs(ey - cy)))
        yy, xx = np.mgrid[0:h, 0:w]
        dist = (np.abs(xx - cx) + np.abs(yy - cy)).astype(np.float32)
        return np.clip(dist / radius, 0.0, 1.0)

    def _render_gradient(self, h: int, w: int,
                         x0: int, y0: int,
                         x1: int, y1: int,
                         *, downsample: bool = False) -> np.ndarray:
        """Return [H, W, 4] float32 gradient image using current stops.

        When *downsample* is True (used during interactive drag), the
        gradient map is computed at a reduced resolution then upscaled.
        This is dramatically cheaper for large layers.
        """
        gtype = self.gradient_type

        # Compute at reduced size during drag for large canvases
        rh, rw = h, w
        if downsample and (h > 512 or w > 512):
            scale = max(h, w) / 512.0
            rh = max(1, int(h / scale))
            rw = max(1, int(w / scale))
            rx0, ry0 = int(x0 / scale), int(y0 / scale)
            rx1, ry1 = int(x1 / scale), int(y1 / scale)
        else:
            rx0, ry0, rx1, ry1 = x0, y0, x1, y1

        if gtype == "radial":
            t = self._radial_map(rh, rw, rx0, ry0, rx1, ry1)
        elif gtype == "conical":
            t = self._conical_map(rh, rw, rx0, ry0, rx1, ry1)
        elif gtype == "diamond":
            t = self._diamond_map(rh, rw, rx0, ry0, rx1, ry1)
        else:
            t = self._linear_map(rh, rw, rx0, ry0, rx1, ry1)

        positions = np.array([s.position for s in self._stops], dtype=np.float32)
        colours = np.array(
            [[s.color.r, s.color.g, s.color.b, s.color.a] for s in self._stops],
            dtype=np.float32,
        )
        gradient = np.empty((rh, rw, 4), dtype=np.float32)
        t_flat = t.ravel()
        for ch in range(4):
            gradient[..., ch] = np.interp(t_flat, positions, colours[:, ch]).reshape(rh, rw)

        # Upscale back to full resolution if we downsampled
        if downsample and (rh != h or rw != w):
            import cv2
            gradient = cv2.resize(gradient, (w, h), interpolation=cv2.INTER_LINEAR)

        return gradient

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_gradient(self, base: np.ndarray, gradient: np.ndarray) -> np.ndarray:
        """Blend *gradient* onto *base* while preserving existing shape alpha."""
        base_alpha = base[..., 3:4]
        gradient_alpha = gradient[..., 3:4]
        result = base.copy()
        if self.opacity < 1.0:
            result[..., :3] = base[..., :3] * (1.0 - self.opacity) + gradient[..., :3] * self.opacity
            result[..., 3:4] = base_alpha * ((1.0 - self.opacity) + gradient_alpha * self.opacity)
        else:
            result[..., :3] = gradient[..., :3]
            result[..., 3:4] = base_alpha * gradient_alpha
        np.clip(result, 0.0, 1.0, out=result)
        return result

    @staticmethod
    def _content_bounds(base: np.ndarray) -> tuple[int, int, int, int] | None:
        alpha = base[..., 3]
        rows = np.any(alpha > 1e-4, axis=1)
        cols = np.any(alpha > 1e-4, axis=0)
        if not np.any(rows) or not np.any(cols):
            return None
        y0 = int(np.where(rows)[0][0])
        y1 = int(np.where(rows)[0][-1]) + 1
        x0 = int(np.where(cols)[0][0])
        x1 = int(np.where(cols)[0][-1]) + 1
        return (x0, y0, x1, y1)

    def _render_applied_gradient(
        self,
        base: np.ndarray,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        *,
        downsample: bool = False,
    ) -> np.ndarray:
        bounds = self._content_bounds(base)
        if bounds is None:
            return base.copy()
        bx0, by0, bx1, by1 = bounds
        roi_base = base[by0:by1, bx0:bx1]
        grad = self._render_gradient(
            by1 - by0,
            bx1 - bx0,
            x0 - bx0,
            y0 - by0,
            x1 - bx0,
            y1 - by0,
            downsample=downsample,
        )
        result = base.copy()
        result[by0:by1, bx0:bx1] = self._apply_gradient(roi_base, grad)
        return result

    def _content_dirty_rect(self) -> tuple[int, int, int, int] | None:
        if self._saved_pixels is None:
            return None
        bounds = self._content_bounds(self._saved_pixels)
        if bounds is None:
            return None
        bx0, by0, bx1, by1 = bounds
        lx, ly = self._layer_pos
        return (lx + bx0, ly + by0, bx1 - bx0, by1 - by0)

    @staticmethod
    def _merge_bounds(
        first: tuple[int, int, int, int] | None,
        second: tuple[int, int, int, int] | None,
    ) -> tuple[int, int, int, int] | None:
        if first is None:
            return second
        if second is None:
            return first
        ax0, ay0, ax1, ay1 = first
        bx0, by0, bx1, by1 = second
        return (
            min(ax0, bx0),
            min(ay0, by0),
            max(ax1, bx1),
            max(ay1, by1),
        )

    def _gradient_support_bounds(
        self,
        bounds: tuple[int, int, int, int],
        x0: int,
        y0: int,
        x1: int,
        y1: int,
    ) -> tuple[int, int, int, int]:
        bx0, by0, bx1, by1 = bounds
        if self.gradient_type == "radial":
            radius = int(math.ceil(max(1.0, math.hypot(float(x1 - x0), float(y1 - y0)))))
        elif self.gradient_type == "diamond":
            radius = max(1, int(abs(x1 - x0) + abs(y1 - y0)))
        else:
            return bounds
        return (
            max(bx0, x0 - radius),
            max(by0, y0 - radius),
            min(bx1, x0 + radius + 1),
            min(by1, y0 + radius + 1),
        )

    def _preview_roi_bounds(
        self,
        base: np.ndarray,
        previous_handles: tuple[int, int, int, int] | None,
        next_handles: tuple[int, int, int, int],
    ) -> tuple[int, int, int, int] | None:
        content_bounds = self._content_bounds(base)
        if content_bounds is None:
            return None
        if self.gradient_type not in {"radial", "diamond"}:
            return content_bounds
        next_bounds = self._gradient_support_bounds(content_bounds, *next_handles)
        previous_bounds = None
        if previous_handles is not None:
            previous_bounds = self._gradient_support_bounds(content_bounds, *previous_handles)
        merged = self._merge_bounds(previous_bounds, next_bounds)
        if merged is None:
            return None
        x0, y0, x1, y1 = merged
        if x1 <= x0 or y1 <= y0:
            return None
        return merged

    def _apply_preview_gradient(
        self,
        layer,
        base: np.ndarray,
        previous_handles: tuple[int, int, int, int] | None,
        next_handles: tuple[int, int, int, int],
    ) -> tuple[int, int, int, int] | None:
        roi_bounds = self._preview_roi_bounds(base, previous_handles, next_handles)
        if roi_bounds is None:
            return None
        bx0, by0, bx1, by1 = roi_bounds
        layer.write_display_region_float(bx0, by0, base[by0:by1, bx0:bx1])
        grad = self._render_gradient(
            by1 - by0,
            bx1 - bx0,
            next_handles[0] - bx0,
            next_handles[1] - by0,
            next_handles[2] - bx0,
            next_handles[3] - by0,
            downsample=True,
        )
        layer.write_display_region_float(
            bx0,
            by0,
            self._apply_gradient(base[by0:by1, bx0:bx1], grad),
        )
        return (bx0, by0, bx1, by1)

    def _reapply_gradient(self) -> None:
        """Re-render gradient from saved pixels (handle-editing path)."""
        if self._saved_pixels is None or self._target_layer is None:
            return
        layer = self._target_layer
        if layer.locked:
            return
        lx, ly = self._layer_pos
        layer.write_display_region_float(
            0,
            0,
            self._render_applied_gradient(
                self._saved_pixels,
                self._start_x - lx, self._start_y - ly,
                self._end_x - lx, self._end_y - ly,
            ),
        )
        self._emit_handles(True)
        if self._preview_cb:
            self._preview_cb()

    def _emit_handles(self, visible: bool) -> None:
        if self._handles_cb:
            self._handles_cb(
                (self._start_x, self._start_y) if visible else None,
                (self._end_x, self._end_y) if visible else None,
                self._stops if visible else [],
                visible,
            )

    def _hit_handle(self, x: int, y: int) -> str | None:
        r2 = self.HANDLE_RADIUS ** 2
        if (x - self._start_x) ** 2 + (y - self._start_y) ** 2 <= r2:
            return "start"
        if (x - self._end_x) ** 2 + (y - self._end_y) ** 2 <= r2:
            return "end"
        return None

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    def on_press(self, doc: Document, x: int, y: int,
                 pressure: float = 1.0) -> None:
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return
        self._rasterize_if_needed(doc)

        # If already editing, check for handle grab first
        if self._editing:
            hit = self._hit_handle(x, y)
            if hit:
                self._dragging_handle = hit
                self._handle_drag_origin = (
                    self._start_x,
                    self._start_y,
                    self._end_x,
                    self._end_y,
                )
                return
            # Click away from handles → start a new gradient
            self._editing = False
            self._saved_pixels = None
            self._target_layer = None
            self._emit_handles(False)

        # Begin new gradient drag
        self._start_x, self._start_y = x, y
        self._end_x, self._end_y = x, y
        self._dragging = True
        self._target_layer = layer
        self._layer_pos = layer.position
        self._saved_pixels = layer.read_display_region_float(0, 0, int(layer.width), int(layer.height))[0]

    def on_move(self, doc: Document, x: int, y: int,
                pressure: float = 1.0) -> None:
        # Handle drag
        if self._dragging_handle:
            previous_handles = (self._start_x, self._start_y, self._end_x, self._end_y)
            if self._dragging_handle == "start":
                self._start_x, self._start_y = x, y
            else:
                self._end_x, self._end_y = x, y
            next_handles = (self._start_x, self._start_y, self._end_x, self._end_y)
            if self._saved_pixels is not None and self._target_layer is not None:
                lx, ly = self._layer_pos
                roi = self._apply_preview_gradient(
                    self._target_layer,
                    self._saved_pixels,
                    (previous_handles[0] - lx, previous_handles[1] - ly, previous_handles[2] - lx, previous_handles[3] - ly),
                    (next_handles[0] - lx, next_handles[1] - ly, next_handles[2] - lx, next_handles[3] - ly),
                )
                if roi is not None:
                    rx0, ry0, rx1, ry1 = roi
                    doc.mark_dirty_region(lx + rx0, ly + ry0, rx1 - rx0, ry1 - ry0)
                else:
                    dirty_rect = self._content_dirty_rect()
                    if dirty_rect is not None:
                        doc.mark_dirty_region(*dirty_rect)
                self._emit_handles(True)
                if self._preview_cb:
                    self._preview_cb()
            else:
                self._reapply_gradient()
            return

        if not self._dragging:
            return

        # Live preview — render gradient on layer from saved state
        layer = self._target_layer
        if layer is None or self._saved_pixels is None:
            return
        lx, ly = self._layer_pos
        previous_handles = (
            self._start_x - lx,
            self._start_y - ly,
            self._end_x - lx,
            self._end_y - ly,
        )
        next_handles = (
            self._start_x - lx,
            self._start_y - ly,
            x - lx,
            y - ly,
        )
        self._end_x, self._end_y = x, y
        roi = self._apply_preview_gradient(layer, self._saved_pixels, previous_handles, next_handles)
        if roi is not None:
            rx0, ry0, rx1, ry1 = roi
            doc.mark_dirty_region(lx + rx0, ly + ry0, rx1 - rx0, ry1 - ry0)
        else:
            layer.write_display_region_float(
                0,
                0,
                self._render_applied_gradient(
                    self._saved_pixels,
                    self._start_x - lx, self._start_y - ly,
                    x - lx, y - ly,
                    downsample=True,
                ),
            )
            dirty_rect = self._content_dirty_rect()
            if dirty_rect is not None:
                doc.mark_dirty_region(*dirty_rect)
        self._emit_handles(True)
        if self._preview_cb:
            self._preview_cb()

    def on_release(self, doc: Document, x: int, y: int) -> None:
        if self._dragging_handle:
            layer = self._target_layer
            if layer is not None and self._saved_pixels is not None and self._handle_drag_origin is not None:
                old_start_x, old_start_y, old_end_x, old_end_y = self._handle_drag_origin
                lx, ly = self._layer_pos
                previous = self._render_applied_gradient(
                    self._saved_pixels,
                    old_start_x - lx, old_start_y - ly,
                    old_end_x - lx, old_end_y - ly,
                )
                current = self._render_applied_gradient(
                    self._saved_pixels,
                    self._start_x - lx, self._start_y - ly,
                    self._end_x - lx, self._end_y - ly,
                )
                if not np.array_equal(previous, current):
                    self._begin_destructive_patch(doc, "Gradient Handle Edit")
                    doc.capture_layer_tile_pixels(
                        layer,
                        previous,
                        0,
                        0,
                        previous.shape[1],
                        previous.shape[0],
                        compare_pixels=current,
                    )
                    layer.write_display_region_float(0, 0, current)
                    self._commit_destructive_patch(doc)
            self._dragging_handle = None
            self._handle_drag_origin = None
            return

        if not self._dragging:
            return
        self._dragging = False
        self._end_x, self._end_y = x, y

        layer = self._target_layer
        if layer is None or self._saved_pixels is None:
            return

        # No actual drag — cancel
        if self._start_x == x and self._start_y == y:
            layer.write_display_region_float(0, 0, self._saved_pixels)
            self._saved_pixels = None
            self._target_layer = None
            self._emit_handles(False)
            return

        # Final render
        lx, ly = self._layer_pos
        final_pixels = self._render_applied_gradient(
            self._saved_pixels,
            self._start_x - lx, self._start_y - ly,
            x - lx, y - ly,
        )
        if not np.array_equal(self._saved_pixels, final_pixels):
            self._begin_destructive_patch(doc, "Gradient")
            doc.capture_layer_tile_pixels(
                layer,
                self._saved_pixels,
                0,
                0,
                final_pixels.shape[1],
                final_pixels.shape[0],
                compare_pixels=final_pixels,
            )
            layer.write_display_region_float(0, 0, final_pixels)
            self._commit_destructive_patch(doc)
        else:
            layer.write_display_region_float(0, 0, final_pixels)

        # Keep saved state for handle editing
        self._editing = True
        self._emit_handles(True)

    def deactivate(self) -> None:
        """Hide handles when switching away, but preserve editing state."""
        self._dragging = False
        self._dragging_handle = None
        # Only hide the overlay handles; keep _editing, _saved_pixels,
        # _target_layer, and start/end coords so they can be restored.
        self._emit_handles(False)
        super().deactivate()
