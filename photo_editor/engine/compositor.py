"""Layer compositor with clipping-mask and group support.

Uses ``BlendingEngine.blend_region_inplace`` for fast region-based
compositing — same optimisation strategy as RenderEngine.
"""

from __future__ import annotations

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

        # Pre-scan for clipping-mask needs
        visible = [
            l for l in layers
            if l.visible and l.parent_id is None
            and l.layer_type != LayerType.ADJUSTMENT
        ]
        needs_placed: set[str] = set()
        for i in range(len(visible) - 1):
            if visible[i + 1].clipping_mask:
                needs_placed.add(visible[i].id)

        prev_img: np.ndarray | None = None

        for layer in visible:
            if layer.layer_type == LayerType.GROUP:
                group_img = self._composite_group(layer, stack, width, height)
                self._blending.blend_region_inplace(
                    canvas, group_img, (0, 0),
                    layer.blend_mode, layer.opacity,
                )
                prev_img = group_img
                continue

            mask = layer.mask if layer.mask_enabled else None

            if layer.clipping_mask and prev_img is not None:
                placed = self._place(layer, width, height)
                placed[..., 3:4] *= prev_img[..., 3:4]
                placed_mask = (
                    self._place_mask(layer, width, height) if mask is not None else None
                )
                self._blending.blend_region_inplace(
                    canvas, placed, (0, 0),
                    layer.blend_mode, layer.opacity, placed_mask,
                )
                prev_img = placed
            else:
                self._blending.blend_region_inplace(
                    canvas, layer.pixels, layer.position,
                    layer.blend_mode, layer.opacity, mask,
                )
                if layer.id in needs_placed:
                    prev_img = self._place(layer, width, height)
                else:
                    prev_img = None

        return canvas

    def _composite_group(
        self, group: Layer, stack: LayerStack, w: int, h: int,
    ) -> np.ndarray:
        canvas = np.zeros((h, w, 4), dtype=np.float32)
        for layer in stack:
            if layer.parent_id != group.id or not layer.visible:
                continue
            mask = layer.mask if layer.mask_enabled else None
            self._blending.blend_region_inplace(
                canvas, layer.pixels, layer.position,
                layer.blend_mode, layer.opacity, mask,
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
