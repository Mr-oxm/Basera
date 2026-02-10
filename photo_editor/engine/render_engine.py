"""Main render engine — composites layer stack into a single image.

Performance notes
-----------------
* Uses ``BlendingEngine.blend_region_inplace`` to blend layers directly
  into the canvas at their native size, avoiding the old full-canvas
  ``_place`` allocation per layer.
* Caches the final composite result (``_result``) so that repeated
  calls without any invalidation (e.g. UI panel refreshes) are free.
* Clipping-mask layers fall back to the full-canvas ``_place`` path
  because they need the placed image of the previous layer.
"""

from __future__ import annotations

import numpy as np

from ..blending.blending_engine import BlendingEngine
from ..core.document import Document
from ..core.enums import BlendMode, LayerType
from ..core.layer import Layer
from ..styles.style_engine import StyleEngine


class RenderEngine:
    """Renders a Document's layer stack to a flat RGBA buffer."""

    def __init__(self) -> None:
        self._blending = BlendingEngine()
        # Composite-result cache
        self._result: np.ndarray | None = None
        self._result_valid: bool = False

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    def invalidate(self, layer_id: str | None = None) -> None:
        """Mark the composite as stale.

        * ``layer_id=None`` — everything is dirty (full rebuild needed).
        * ``layer_id="abc"`` — only one layer changed; the composite
          must still be rebuilt but callers can throttle requests.
        """
        self._result_valid = False

    def invalidate_all(self) -> None:
        """Hard reset — clears the result cache entirely."""
        self._result = None
        self._result_valid = False

    # ------------------------------------------------------------------
    # Public render
    # ------------------------------------------------------------------

    def render(self, document: Document) -> np.ndarray:
        if self._result_valid and self._result is not None:
            return self._result

        h, w = document.height, document.width
        canvas = np.zeros((h, w, 4), dtype=np.float32)

        # Pre-scan: find layers whose placed image is needed by a
        # following clipping-mask layer.
        visible = [
            layer for layer in document.layers
            if layer.visible and layer.parent_id is None
            and layer.layer_type != LayerType.ADJUSTMENT
        ]
        needs_placed: set[str] = set()
        for i in range(len(visible) - 1):
            if visible[i + 1].clipping_mask:
                needs_placed.add(visible[i].id)

        prev_img: np.ndarray | None = None

        for layer in visible:
            if layer.layer_type == LayerType.GROUP:
                group_img = self._render_group(layer, document, w, h)
                # Group composite is canvas-sized already → position (0,0)
                self._blending.blend_region_inplace(
                    canvas, group_img, (0, 0),
                    layer.blend_mode, layer.opacity,
                )
                prev_img = group_img
                continue

            mask = layer.mask if layer.mask_enabled else None

            if layer.clipping_mask and prev_img is not None:
                # Clipping-mask layer: needs the previous layer's placed
                # image → fall back to the full-canvas path.
                if layer.styles:
                    layer_copy = Layer(layer.name, layer.width, layer.height)
                    layer_copy._pixels = StyleEngine.apply_styles(layer.pixels, layer.styles)
                    layer_copy.position = layer.position
                    placed = self._place(layer_copy, w, h)
                else:
                    placed = self._place(layer, w, h)
                placed[..., 3:4] *= prev_img[..., 3:4]
                placed_mask = (
                    self._place_mask(layer, w, h) if mask is not None else None
                )
                self._blending.blend_region_inplace(
                    canvas, placed, (0, 0),
                    layer.blend_mode, layer.opacity, placed_mask,
                )
                prev_img = placed
            else:
                # --- Fast path: region blend directly -----------------
                pixels = layer.pixels
                if layer.styles:
                    pixels = StyleEngine.apply_styles(pixels, layer.styles)
                self._blending.blend_region_inplace(
                    canvas, pixels, layer.position,
                    layer.blend_mode, layer.opacity, mask,
                )
                # Only compute the placed image if the NEXT layer needs
                # it for clipping.
                if layer.id in needs_placed:
                    prev_img = self._place(layer, w, h)
                else:
                    prev_img = None

        np.clip(canvas, 0, 1, out=canvas)
        self._result = canvas
        self._result_valid = True
        return canvas

    def render_to_uint8(self, document: Document) -> np.ndarray:
        return (self.render(document) * 255).astype(np.uint8)

    # ---- Internal --------------------------------------------------------

    def _render_group(
        self, group: Layer, document: Document, cw: int, ch: int,
    ) -> np.ndarray:
        """Composite all children of *group* using region blending."""
        canvas = np.zeros((ch, cw, 4), dtype=np.float32)
        for layer in document.layers:
            if layer.parent_id != group.id or not layer.visible:
                continue
            mask = layer.mask if layer.mask_enabled else None
            pixels = layer.pixels
            if layer.styles:
                pixels = StyleEngine.apply_styles(pixels, layer.styles)
            self._blending.blend_region_inplace(
                canvas, pixels, layer.position,
                layer.blend_mode, layer.opacity, mask,
            )
        return canvas

    @staticmethod
    def _place(layer: Layer, cw: int, ch: int) -> np.ndarray:
        """Place layer pixels onto a canvas-sized array (clipping path)."""
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
        """Place the layer's mask into a canvas-sized array (clipping path)."""
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
