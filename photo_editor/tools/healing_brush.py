"""Healing Brush tool — clones source pixels while blending luminance to match the destination."""

import cv2
import numpy as np

from .tool_base import Tool
from ..core.document import Document


class HealingBrushTool(Tool):
    """Copies texture from a source area and adapts luminance to the destination."""

    def __init__(self) -> None:
        super().__init__("Healing Brush")
        self.size: int = 30

        # Source (set via alt-click, same workflow as CloneStamp)
        self.source_x: int = 0
        self.source_y: int = 0
        self.source_set: bool = False

        self._offset_x: int = 0
        self._offset_y: int = 0
        self._last_x: int = 0
        self._last_y: int = 0
        self._drawing: bool = False
        self._offset_locked: bool = False

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_source(self, x: int, y: int) -> None:
        self.source_x = x
        self.source_y = y
        self.source_set = True
        self._offset_locked = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rgb_to_luminance(rgb: np.ndarray) -> np.ndarray:
        """Return single-channel luminance (float32) from RGB channels."""
        return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]

    def _heal_patch(self, target: np.ndarray, cx: int, cy: int, radius: int) -> None:
        h, w = target.shape[:2]
        sx, sy = cx + self._offset_x, cy + self._offset_y

        y0d, y1d = max(0, cy - radius), min(h, cy + radius + 1)
        x0d, x1d = max(0, cx - radius), min(w, cx + radius + 1)
        y0s, y1s = y0d + (sy - cy), y1d + (sy - cy)
        x0s, x1s = x0d + (sx - cx), x1d + (sx - cx)

        # Clip source
        if y0s < 0:
            y0d -= y0s; y0s = 0
        if x0s < 0:
            x0d -= x0s; x0s = 0
        if y1s > h:
            y1d -= (y1s - h); y1s = h
        if x1s > w:
            x1d -= (x1s - w); x1s = w

        ph = min(y1d - y0d, y1s - y0s)
        pw = min(x1d - x0d, x1s - x0s)
        if ph <= 0 or pw <= 0:
            return

        src_patch = target[y0s:y0s + ph, x0s:x0s + pw].copy()
        dst_patch = target[y0d:y0d + ph, x0d:x0d + pw].copy()

        # Luminance adaptation: shift source luminance to match destination
        src_lum = self._rgb_to_luminance(src_patch)
        dst_lum = self._rgb_to_luminance(dst_patch)
        src_mean = src_lum.mean() + 1e-6
        dst_mean = dst_lum.mean() + 1e-6
        lum_ratio = dst_mean / src_mean

        healed = src_patch.copy()
        healed[..., :3] = np.clip(healed[..., :3] * lum_ratio, 0, 1)
        # Keep destination alpha
        healed[..., 3] = dst_patch[..., 3]

        # Circular falloff mask
        yy, xx = np.mgrid[y0d:y0d + ph, x0d:x0d + pw]
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2).astype(np.float32)
        mask = np.clip(1.0 - dist / max(radius, 1), 0, 1)
        mask = mask[..., np.newaxis]

        # Blend with Poisson-like smooth falloff (Gaussian on mask)
        ksize = max(3, (radius // 2) * 2 + 1)
        mask_2d = mask[..., 0]
        mask_2d = cv2.GaussianBlur(mask_2d, (ksize, ksize), radius / 3.0)
        mask = mask_2d[..., np.newaxis]

        target[y0d:y0d + ph, x0d:x0d + pw] = (
            dst_patch * (1 - mask) + healed * mask
        )

    def _stroke_points(self, x0: int, y0: int, x1: int, y1: int, step: float):
        dx, dy = x1 - x0, y1 - y0
        dist = max(1.0, np.hypot(dx, dy))
        steps = int(dist / max(step, 1))
        for i in range(steps + 1):
            t = i / max(steps, 1)
            yield int(x0 + dx * t), int(y0 + dy * t)

    def _heal_along(self, doc: Document, x0: int, y0: int,
                    x1: int, y1: int) -> None:
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return
        lx, ly = layer.position
        radius = max(1, self.size // 2)
        step = max(1.0, radius * 0.5)
        for px, py in self._stroke_points(x0, y0, x1, y1, step):
            self._heal_patch(layer.pixels, px - lx, py - ly, radius)

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        if not self.source_set:
            return
        doc.save_snapshot("Healing Brush")
        if not self._offset_locked:
            self._offset_x = self.source_x - x
            self._offset_y = self.source_y - y
            self._offset_locked = True
        self._drawing = True
        self._last_x, self._last_y = x, y
        self._heal_along(doc, x, y, x, y)

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        if not self._drawing:
            return
        self._heal_along(doc, self._last_x, self._last_y, x, y)
        self._last_x, self._last_y = x, y

    def on_release(self, doc: Document, x: int, y: int) -> None:
        self._drawing = False
