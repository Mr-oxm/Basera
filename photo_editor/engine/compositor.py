"""Layer compositor with clipping-mask and group support."""

import numpy as np

from ..blending.blending_engine import BlendingEngine
from ..core.enums import LayerType
from ..core.layer import Layer
from ..core.layer_stack import LayerStack


class Compositor:
    """Composites a LayerStack into a flat RGBA image."""

    def __init__(self) -> None:
        self._blending = BlendingEngine()

    def composite(self, stack: LayerStack, width: int, height: int) -> np.ndarray:
        canvas = np.zeros((height, width, 4), dtype=np.float32)
        layers = list(stack)
        prev_img: np.ndarray | None = None

        for layer in layers:
            if not layer.visible:
                continue
            # Skip children — they're composited within their group
            if layer.parent_id is not None:
                continue
            if layer.layer_type == LayerType.GROUP:
                group_img = self._composite_group(layer, stack, width, height)
                canvas = self._blending.blend(canvas, group_img, layer.blend_mode, layer.opacity)
                prev_img = group_img
                continue

            img = self._place(layer, width, height)
            if layer.clipping_mask and prev_img is not None:
                img = img.copy()
                img[..., 3:4] *= prev_img[..., 3:4]
            mask = self._place_mask(layer, width, height) if layer.mask_enabled else None
            canvas = self._blending.blend_with_mask(
                canvas, img, mask, layer.blend_mode, layer.opacity,
            )
            prev_img = img
        return canvas

    def _composite_group(
        self, group: Layer, stack: LayerStack, w: int, h: int,
    ) -> np.ndarray:
        canvas = np.zeros((h, w, 4), dtype=np.float32)
        for layer in stack:
            if layer.parent_id != group.id or not layer.visible:
                continue
            img = self._place(layer, w, h)
            mask = self._place_mask(layer, w, h) if layer.mask_enabled else None
            canvas = self._blending.blend_with_mask(
                canvas, img, mask, layer.blend_mode, layer.opacity,
            )
        return canvas

    @staticmethod
    def _place(layer: Layer, cw: int, ch: int) -> np.ndarray:
        canvas = np.zeros((ch, cw, 4), dtype=np.float32)
        lx, ly = layer.position
        lh, lw = layer.pixels.shape[:2]
        sx, sy = max(0, -lx), max(0, -ly)
        dx, dy = max(0, lx), max(0, ly)
        w = min(lw - sx, cw - dx)
        h = min(lh - sy, ch - dy)
        if w > 0 and h > 0:
            canvas[dy : dy + h, dx : dx + w] = layer.pixels[sy : sy + h, sx : sx + w]
        return canvas

    @staticmethod
    def _place_mask(layer: Layer, cw: int, ch: int) -> np.ndarray | None:
        """Place the layer's mask into a canvas-sized array."""
        if layer.mask is None:
            return None
        canvas = np.zeros((ch, cw), dtype=np.float32)
        lx, ly = layer.position
        mh, mw = layer.mask.shape[:2]
        sx, sy = max(0, -lx), max(0, -ly)
        dx, dy = max(0, lx), max(0, ly)
        w = min(mw - sx, cw - dx)
        h = min(mh - sy, ch - dy)
        if w > 0 and h > 0:
            canvas[dy : dy + h, dx : dx + w] = layer.mask[sy : sy + h, sx : sx + w]
        return canvas
