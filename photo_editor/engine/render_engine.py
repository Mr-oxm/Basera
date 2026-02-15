"""Main render engine — composites layer stack into a single image.

Performance notes
-----------------
* Uses ``BlendingEngine.blend_region_inplace`` to blend layers directly
  into the canvas at their native size, avoiding the old full-canvas
  ``_place`` allocation per layer.
* **Incremental compositing cache** — when ``invalidate(layer_id)``
  targets a specific layer, the engine caches the composite built
  *below* that layer and only re-blends from the dirty layer upward.
  For a 10-layer document where only the top layer changes, this
  skips 90 % of the work.
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
from ..masks.mask_manager import MaskManager


class RenderEngine:
    """Renders a Document's layer stack to a flat RGBA buffer."""

    def __init__(self) -> None:
        self._blending = BlendingEngine()
        # Composite-result cache
        self._result: np.ndarray | None = None
        self._result_valid: bool = False
        # Pre-allocated canvas to avoid repeated allocation
        self._canvas_buf: np.ndarray | None = None
        self._canvas_shape: tuple[int, int] = (0, 0)

        # -- Incremental compositing cache --
        # Stores the composite built from all layers *below* a given
        # layer so that only the dirty layer and those above it need
        # re-blending on the next render.
        self._inc_base: np.ndarray | None = None     # snapshot before dirty layer
        self._inc_layer_id: str | None = None         # which layer the cache is for
        self._inc_layer_order: list[str] = []          # layer ordering at cache time
        self._inc_prev_img: np.ndarray | None = None   # prev_img at cache point
        # Dirty tracking
        self._dirty_layer_id: str | None = None
        self._full_dirty: bool = True

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    def invalidate(self, layer_id: str | None = None) -> None:
        """Mark the composite as stale.

        * ``layer_id=None`` — everything is dirty (full rebuild needed).
        * ``layer_id="abc"`` — only that layer changed; the engine can
          re-use the cached composite of all layers below it.
        """
        self._result_valid = False
        if layer_id is not None:
            if self._dirty_layer_id is None or self._dirty_layer_id == layer_id:
                self._dirty_layer_id = layer_id
                self._full_dirty = False
            else:
                # A *different* layer was dirtied → need full rebuild
                self._full_dirty = True
                self._dirty_layer_id = None
        else:
            self._full_dirty = True
            self._dirty_layer_id = None

    def invalidate_all(self) -> None:
        """Hard reset — clears the result cache entirely."""
        self._result = None
        self._result_valid = False
        self._canvas_buf = None
        self._inc_base = None
        self._inc_layer_id = None
        self._inc_layer_order = []
        self._inc_prev_img = None
        self._full_dirty = True
        self._dirty_layer_id = None

    # ------------------------------------------------------------------
    # Pre-allocated canvas helper
    # ------------------------------------------------------------------

    def _get_canvas(self, h: int, w: int) -> np.ndarray:
        """Return a zeroed (h, w, 4) float32 canvas, reusing memory."""
        if self._canvas_shape != (h, w) or self._canvas_buf is None:
            self._canvas_buf = np.zeros((h, w, 4), dtype=np.float32)
            self._canvas_shape = (h, w)
        else:
            self._canvas_buf[:] = 0
        return self._canvas_buf

    # ------------------------------------------------------------------
    # Public render
    # ------------------------------------------------------------------

    def render(self, document: Document) -> np.ndarray:
        if self._result_valid and self._result is not None:
            return self._result

        h, w = document.height, document.width

        # Pre-scan: find layers whose placed image is needed by a
        # following clipping-mask layer.
        visible = [
            layer for layer in document.layers
            if layer.visible and layer.parent_id is None
        ]

        # Collect mask-layer IDs so we skip them in the main compositing loop
        mask_layer_ids: set[str] = set()
        for layer in document.layers:
            for mid in layer.mask_layers:
                mask_layer_ids.add(mid)

        # Standalone mask IDs (no parent, not attached to any layer)
        standalone_mask_ids: set[str] = set()
        for layer in document.layers:
            if (layer.layer_type == LayerType.MASK
                    and layer.parent_id is None
                    and layer.id not in mask_layer_ids):
                standalone_mask_ids.add(layer.id)

        # Build map of child adjustment/filter layers per parent
        adj_children: dict[str, list] = {}
        for layer in document.layers:
            if (layer.parent_id
                    and layer.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER)
                    and layer.visible):
                adj_children.setdefault(layer.parent_id, []).append(layer)

        # Collect child adj/filter layer ids so we skip them in the main loop
        adj_child_ids: set[str] = set()
        for children in adj_children.values():
            for c in children:
                adj_child_ids.add(c.id)

        # Filter out attached mask layers and child adj/filter layers;
        # keep standalone masks in the visible list so they are processed
        # at their stack position (only affecting layers below).
        visible = [
            l for l in visible
            if l.id not in mask_layer_ids
            and (l.layer_type != LayerType.MASK or l.id in standalone_mask_ids)
            and l.id not in adj_child_ids
        ]
        current_order = [l.id for l in visible]

        needs_placed: set[str] = set()
        for i in range(len(visible) - 1):
            if visible[i + 1].clipping_mask:
                needs_placed.add(visible[i].id)

        # --- Determine if the incremental cache is usable ----------------
        start_idx = 0
        use_cache = (
            not self._full_dirty
            and self._dirty_layer_id is not None
            and current_order == self._inc_layer_order
            and self._inc_layer_id == self._dirty_layer_id
            and self._inc_base is not None
            and self._inc_base.shape[:2] == (h, w)
        )

        if use_cache:
            try:
                dirty_idx = current_order.index(self._dirty_layer_id)
            except ValueError:
                use_cache = False

        if use_cache:
            # Restore the composite to the state just before the dirty layer
            canvas = self._get_canvas(h, w)
            np.copyto(canvas, self._inc_base)
            start_idx = dirty_idx
            prev_img = self._inc_prev_img
        else:
            canvas = self._get_canvas(h, w)
            prev_img = None

        # Determine where to snapshot for future incremental renders
        save_at_id = self._dirty_layer_id
        save_at_idx: int | None = None
        if save_at_id and save_at_id in current_order:
            save_at_idx = current_order.index(save_at_id)

        needs_clip = False  # track whether we need final clip

        for i, layer in enumerate(visible):
            if i < start_idx:
                # Still need prev_img for clipping-mask tracking
                if layer.id in needs_placed:
                    prev_img = self._place(layer, w, h)
                continue

            # --- Save incremental cache point (just before dirty layer) ---
            if (
                not use_cache
                and save_at_idx is not None
                and i == save_at_idx
            ):
                self._inc_base = canvas.copy()
                self._inc_layer_id = save_at_id
                self._inc_layer_order = current_order
                self._inc_prev_img = prev_img.copy() if prev_img is not None else None

            if layer.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER):
                # Apply adjustment/filter to composite built so far
                adj = layer.adjustment
                if adj is not None:
                    canvas = adj.apply(canvas, layer.adjustment_params)
                    needs_clip = True  # adjustments can produce out-of-range
                continue

            # --- Standalone mask: attenuate canvas built so far -----------
            if layer.layer_type == LayerType.MASK and layer.id in standalone_mask_ids:
                gray = layer.get_mask_grayscale()
                placed_gray = np.zeros((h, w), dtype=np.float32)
                lx, ly = layer.position
                mh_, mw_ = gray.shape[:2]
                sx, sy = max(0, -lx), max(0, -ly)
                dx, dy = max(0, lx), max(0, ly)
                rw = min(mw_ - sx, w - dx)
                rh = min(mh_ - sy, h - dy)
                if rw > 0 and rh > 0:
                    placed_gray[dy:dy + rh, dx:dx + rw] = gray[sy:sy + rh, sx:sx + rw]
                if layer.ex_parent_id:
                    canvas[..., 3] *= placed_gray
                else:
                    canvas *= placed_gray[..., np.newaxis]
                continue

            if layer.layer_type == LayerType.GROUP:
                group_img = self._render_group(layer, document, w, h)
                # Apply child adj/filter layers scoped to this group
                if layer.id in adj_children:
                    for adj_layer in adj_children[layer.id]:
                        adj = adj_layer.adjustment
                        if adj is not None:
                            group_img = adj.apply(group_img, adj_layer.adjustment_params)
                    needs_clip = True
                # Apply mask layers attached to the group
                group_mask = MaskManager.get_combined_mask(layer, document.layers)
                if group_mask is not None:
                    placed_mask = np.zeros((h, w), dtype=np.float32)
                    gx, gy = layer.position
                    mh_, mw_ = group_mask.shape[:2]
                    sx_, sy_ = max(0, -gx), max(0, -gy)
                    dx_, dy_ = max(0, gx), max(0, gy)
                    rw_ = min(mw_ - sx_, w - dx_)
                    rh_ = min(mh_ - sy_, h - dy_)
                    if rw_ > 0 and rh_ > 0:
                        placed_mask[dy_:dy_ + rh_, dx_:dx_ + rw_] = group_mask[sy_:sy_ + rh_, sx_:sx_ + rw_]
                    group_img[..., 3] *= placed_mask
                # Group composite is canvas-sized already → position (0,0)
                self._blending.blend_region_inplace(
                    canvas, group_img, (0, 0),
                    layer.blend_mode, layer.opacity,
                )
                if layer.blend_mode != BlendMode.NORMAL:
                    needs_clip = True
                prev_img = group_img
                continue

            mask = MaskManager.get_combined_mask(layer, document.layers)

            if layer.clipping_mask and prev_img is not None:
                # Clipping-mask layer: needs the previous layer's placed
                # image → fall back to the full-canvas path.
                pixels = layer.pixels
                # Apply child adj/filters scoped to this layer
                if layer.id in adj_children:
                    pixels = pixels.copy()
                    for adj_layer in adj_children[layer.id]:
                        adj = adj_layer.adjustment
                        if adj is not None:
                            pixels = adj.apply(pixels, adj_layer.adjustment_params)
                    np.clip(pixels, 0, 1, out=pixels)
                if layer.styles:
                    layer_copy = Layer(layer.name, layer.width, layer.height)
                    layer_copy._pixels = StyleEngine.apply_styles(pixels, layer.styles)
                    layer_copy.position = layer.position
                    placed = self._place(layer_copy, w, h)
                else:
                    if pixels is not layer.pixels:
                        layer_copy = Layer(layer.name, layer.width, layer.height)
                        layer_copy._pixels = pixels
                        layer_copy.position = layer.position
                        placed = self._place(layer_copy, w, h)
                    else:
                        placed = self._place(layer, w, h)
                placed[..., 3:4] *= prev_img[..., 3:4]
                placed_mask = (
                    self._place_combined_mask(layer, document.layers, w, h)
                    if mask is not None else None
                )
                self._blending.blend_region_inplace(
                    canvas, placed, (0, 0),
                    layer.blend_mode, layer.opacity, placed_mask,
                )
                if layer.blend_mode != BlendMode.NORMAL:
                    needs_clip = True
                prev_img = placed
            else:
                # --- Fast path: region blend directly -----------------
                pixels = layer.pixels
                # Apply child adj/filters scoped to this layer
                if layer.id in adj_children:
                    pixels = pixels.copy()
                    for adj_layer in adj_children[layer.id]:
                        adj = adj_layer.adjustment
                        if adj is not None:
                            pixels = adj.apply(pixels, adj_layer.adjustment_params)
                    np.clip(pixels, 0, 1, out=pixels)
                if layer.styles:
                    pixels = StyleEngine.apply_styles(pixels, layer.styles)
                self._blending.blend_region_inplace(
                    canvas, pixels, layer.position,
                    layer.blend_mode, layer.opacity, mask,
                )
                if layer.blend_mode != BlendMode.NORMAL:
                    needs_clip = True
                # Only compute the placed image if the NEXT layer needs
                # it for clipping.
                if layer.id in needs_placed:
                    prev_img = self._place(layer, w, h)
                else:
                    prev_img = None

        # Only clip when non-NORMAL blends or adjustments were used
        if needs_clip:
            np.clip(canvas, 0, 1, out=canvas)

        # Reset dirty tracking for next frame
        self._full_dirty = False
        self._result = canvas
        self._result_valid = True
        return canvas

    def render_to_uint8(self, document: Document) -> np.ndarray:
        # render() already clips to [0,1]
        return (self.render(document) * 255).astype(np.uint8)

    # ---- Internal --------------------------------------------------------

    def _render_group(
        self, group: Layer, document: Document, cw: int, ch: int,
    ) -> np.ndarray:
        """Composite all children of *group* using region blending."""
        canvas = np.zeros((ch, cw, 4), dtype=np.float32)
        # Collect mask-layer IDs used by children of this group
        mask_ids: set[str] = set()
        group_child_ids: set[str] = set()
        for layer in document.layers:
            if layer.parent_id == group.id:
                group_child_ids.add(layer.id)
                for mid in layer.mask_layers:
                    mask_ids.add(mid)

        # Build adj/filter map for children of group members
        adj_children: dict[str, list] = {}
        adj_child_ids: set[str] = set()
        for layer in document.layers:
            if (layer.parent_id
                    and layer.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER)
                    and layer.visible
                    and layer.parent_id in group_child_ids):
                adj_children.setdefault(layer.parent_id, []).append(layer)
                adj_child_ids.add(layer.id)

        for layer in document.layers:
            if layer.parent_id != group.id or not layer.visible:
                continue
            if layer.id in mask_ids or layer.layer_type == LayerType.MASK:
                continue
            if layer.id in adj_child_ids:
                continue
            # Skip adj/filter layers parented directly to the group
            # (they are applied in the main render loop)
            if layer.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER):
                continue

            mask = MaskManager.get_combined_mask(layer, document.layers)

            # Handle nested groups recursively
            if layer.layer_type == LayerType.GROUP:
                pixels = self._render_group(layer, document, cw, ch)
                position = (0, 0)
            else:
                pixels = layer.pixels
                position = layer.position

            # Apply child adj/filter layers scoped to this layer
            if layer.id in adj_children:
                pixels = pixels.copy()
                for adj_layer in adj_children[layer.id]:
                    adj = adj_layer.adjustment
                    if adj is not None:
                        pixels = adj.apply(pixels, adj_layer.adjustment_params)
                np.clip(pixels, 0, 1, out=pixels)
            if layer.styles:
                pixels = StyleEngine.apply_styles(pixels, layer.styles)
            self._blending.blend_region_inplace(
                canvas, pixels, position,
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

    @staticmethod
    def _place_combined_mask(layer: Layer, stack, cw: int, ch: int) -> np.ndarray | None:
        """Place the combined mask (legacy + mask layers) onto a canvas."""
        combined = MaskManager.get_combined_mask(layer, stack)
        if combined is None:
            return None
        canvas = np.zeros((ch, cw), dtype=np.float32)
        lx, ly = layer.position
        mh, mw = combined.shape[:2]
        sx, sy = max(0, -lx), max(0, -ly)
        dx, dy = max(0, lx), max(0, ly)
        w = min(mw - sx, cw - dx)
        h = min(mh - sy, ch - dy)
        if w > 0 and h > 0:
            canvas[dy : dy + h, dx : dx + w] = combined[sy : sy + h, sx : sx + w]
        return canvas
