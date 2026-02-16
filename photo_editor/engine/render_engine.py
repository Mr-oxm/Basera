"""Main render engine — composites layer stack into a single image."""

import numpy as np

from ..blending.blending_engine import BlendingEngine
from ..core.document import Document
from ..core.enums import LayerType
from ..core.layer import Layer


class RenderEngine:
    """Renders a Document's layer stack to a flat RGBA buffer."""

    def __init__(self) -> None:
        self._blending = BlendingEngine()
        self._cache: dict[str, np.ndarray] = {}
        self._dirty: set[str] = set()

    def invalidate(self, layer_id: str | None = None) -> None:
        if layer_id:
            self._dirty.add(layer_id)
        else:
            self._dirty.clear()
            self._cache.clear()

    def render(self, document: Document) -> np.ndarray:
        h, w = document.height, document.width
        canvas = np.zeros((h, w, 4), dtype=np.float32)
        prev_img: np.ndarray | None = None

        for layer in document.layers:
            if not layer.visible:
                continue
            # Skip children — they're composited within their group
            if layer.parent_id is not None:
                continue
            if layer.layer_type == LayerType.GROUP:
                group_img = self._render_group(layer, document, w, h)
                canvas = self._blending.blend(
                    canvas, group_img, layer.blend_mode, layer.opacity,
                )
                prev_img = group_img
                continue
            if layer.layer_type == LayerType.ADJUSTMENT:
                continue
            img = self._render_layer(layer, w, h)
            if img is None:
                continue
            if layer.clipping_mask and prev_img is not None:
                img = img.copy()
                img[..., 3:4] *= prev_img[..., 3:4]
            mask = self._place_mask(layer, w, h) if layer.mask_enabled else None
            canvas = self._blending.blend_with_mask(
                canvas, img, mask, layer.blend_mode, layer.opacity,
            )
            prev_img = img
        return np.clip(canvas, 0, 1)

    def render_to_uint8(self, document: Document) -> np.ndarray:
        return (self.render(document) * 255).astype(np.uint8)

    # ---- Internal -----------------------------------------------------------

    def _render_group(
        self, group: Layer, document: "Document", cw: int, ch: int,
    ) -> np.ndarray:
        """Composite all children of *group* into a single RGBA buffer."""
        canvas = np.zeros((ch, cw, 4), dtype=np.float32)
        for layer in document.layers:
            if layer.parent_id != group.id or not layer.visible:
                continue
            img = self._render_layer(layer, cw, ch)
            if img is None:
                continue
            mask = self._place_mask(layer, cw, ch) if layer.mask_enabled else None
            canvas = self._blending.blend_with_mask(
                canvas, img, mask, layer.blend_mode, layer.opacity,
            )
        return canvas

    def _render_layer(self, layer: Layer, cw: int, ch: int) -> np.ndarray | None:
        if layer.layer_type == LayerType.ADJUSTMENT:
            return None
        if layer.id in self._cache and layer.id not in self._dirty:
            return self._cache[layer.id]

        img = self._place(layer, cw, ch)
        self._cache[layer.id] = img
        self._dirty.discard(layer.id)
        return img

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
