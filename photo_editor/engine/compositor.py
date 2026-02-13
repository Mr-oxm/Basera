"""Layer compositor with clipping-mask, group, and mask-layer support.

Uses ``BlendingEngine.blend_region_inplace`` for fast region-based
compositing — same optimisation strategy as RenderEngine.
"""

from __future__ import annotations

import numpy as np

from ..blending.blending_engine import BlendingEngine
from ..core.enums import LayerType
from ..core.layer import Layer
from ..core.layer_stack import LayerStack
from ..masks.mask_manager import MaskManager


class Compositor:
    """Composites a LayerStack into a flat RGBA image."""

    def __init__(self) -> None:
        self._blending = BlendingEngine()

    def _get_effective_mask(self, layer: Layer, stack: LayerStack) -> np.ndarray | None:
        """Compute the combined mask for *layer*.

        Combines the legacy per-layer mask and all child MASK layers.
        """
        return MaskManager.get_combined_mask(layer, stack)

    def composite(self, stack: LayerStack, width: int, height: int) -> np.ndarray:
        canvas = np.zeros((height, width, 4), dtype=np.float32)
        layers = list(stack)

        # Set of mask-layer IDs so we skip them in the main loop
        mask_layer_ids: set[str] = set()
        for l in layers:
            for mid in l.mask_layers:
                mask_layer_ids.add(mid)

        # Build map of child adjustment/filter layers per parent
        adj_children: dict[str, list[Layer]] = {}
        adj_child_ids: set[str] = set()
        for l in layers:
            if (l.parent_id
                    and l.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER)
                    and l.visible):
                adj_children.setdefault(l.parent_id, []).append(l)
                adj_child_ids.add(l.id)

        # Standalone mask IDs (no parent, not attached to any layer)
        standalone_mask_ids: set[str] = set()
        for l in layers:
            if (l.layer_type == LayerType.MASK
                    and l.parent_id is None
                    and l.id not in mask_layer_ids):
                standalone_mask_ids.add(l.id)

        # Pre-scan for clipping-mask needs — keep standalone masks in-line
        visible = [
            l for l in layers
            if l.visible and l.parent_id is None
            and l.layer_type != LayerType.ADJUSTMENT
            and l.layer_type != LayerType.FILTER
            and l.id not in mask_layer_ids
            and (l.layer_type != LayerType.MASK or l.id in standalone_mask_ids)
            and l.id not in adj_child_ids
        ]
        needs_placed: set[str] = set()
        for i in range(len(visible) - 1):
            if visible[i + 1].clipping_mask:
                needs_placed.add(visible[i].id)

        prev_img: np.ndarray | None = None

        for layer in visible:
            # --- Standalone mask: attenuate canvas built so far --------
            if layer.layer_type == LayerType.MASK and layer.id in standalone_mask_ids:
                gray = layer.get_mask_grayscale()
                placed_gray = np.zeros((height, width), dtype=np.float32)
                lx, ly = layer.position
                mh, mw = gray.shape[:2]
                sx, sy = max(0, -lx), max(0, -ly)
                dx, dy = max(0, lx), max(0, ly)
                rw = min(mw - sx, width - dx)
                rh = min(mh - sy, height - dy)
                if rw > 0 and rh > 0:
                    placed_gray[dy:dy + rh, dx:dx + rw] = gray[sy:sy + rh, sx:sx + rw]
                if layer.ex_parent_id:
                    # Detached mask — only attenuate alpha
                    canvas[..., 3] *= placed_gray
                else:
                    # Global standalone mask — attenuate all channels
                    canvas *= placed_gray[..., np.newaxis]
                continue

            if layer.layer_type == LayerType.GROUP:
                group_img = self._composite_group(layer, stack, width, height)
                # Apply child adj/filter layers scoped to this group
                if layer.id in adj_children:
                    for adj_layer in adj_children[layer.id]:
                        adj = adj_layer.adjustment
                        if adj is not None:
                            group_img = adj.apply(group_img, adj_layer.adjustment_params)
                    np.clip(group_img, 0, 1, out=group_img)
                # Apply mask layers attached to the group
                group_mask = self._get_effective_mask(layer, stack)
                if group_mask is not None:
                    # group_img is canvas-sized; place the mask at the group's
                    # logical position (which is (0,0) for groups).
                    placed_mask = np.zeros((height, width), dtype=np.float32)
                    gx, gy = layer.position
                    mh_, mw_ = group_mask.shape[:2]
                    sx_, sy_ = max(0, -gx), max(0, -gy)
                    dx_, dy_ = max(0, gx), max(0, gy)
                    rw_ = min(mw_ - sx_, width - dx_)
                    rh_ = min(mh_ - sy_, height - dy_)
                    if rw_ > 0 and rh_ > 0:
                        placed_mask[dy_:dy_ + rh_, dx_:dx_ + rw_] = group_mask[sy_:sy_ + rh_, sx_:sx_ + rw_]
                    group_img[..., 3] *= placed_mask
                self._blending.blend_region_inplace(
                    canvas, group_img, (0, 0),
                    layer.blend_mode, layer.opacity,
                )
                prev_img = group_img
                continue

            # Combined mask: legacy mask + mask layers
            mask = self._get_effective_mask(layer, stack)

            # Apply child adjustment/filter layers to this layer's pixels
            pixels = layer.pixels
            if layer.id in adj_children:
                pixels = pixels.copy()
                for adj_layer in adj_children[layer.id]:
                    adj = adj_layer.adjustment
                    if adj is not None:
                        pixels = adj.apply(pixels, adj_layer.adjustment_params)
                np.clip(pixels, 0, 1, out=pixels)

            if layer.clipping_mask and prev_img is not None:
                placed = self._place_pixels(pixels, layer.position, width, height)
                placed[..., 3:4] *= prev_img[..., 3:4]
                placed_mask = (
                    self._place_mask_combined(layer, stack, width, height)
                    if mask is not None else None
                )
                self._blending.blend_region_inplace(
                    canvas, placed, (0, 0),
                    layer.blend_mode, layer.opacity, placed_mask,
                )
                prev_img = placed
            else:
                self._blending.blend_region_inplace(
                    canvas, pixels, layer.position,
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
        # Collect mask-layer IDs used by children of this group
        mask_ids: set[str] = set()
        group_child_ids: set[str] = set()
        for layer in stack:
            if layer.parent_id == group.id:
                group_child_ids.add(layer.id)
                for mid in layer.mask_layers:
                    mask_ids.add(mid)

        # Build adj/filter map for children of group members
        adj_children: dict[str, list] = {}
        adj_child_ids: set[str] = set()
        for layer in stack:
            if (layer.parent_id
                    and layer.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER)
                    and layer.visible
                    and layer.parent_id in group_child_ids):
                adj_children.setdefault(layer.parent_id, []).append(layer)
                adj_child_ids.add(layer.id)

        for layer in stack:
            if layer.parent_id != group.id or not layer.visible:
                continue
            if layer.id in mask_ids or layer.layer_type == LayerType.MASK:
                continue
            if layer.id in adj_child_ids:
                continue
            # Skip adj/filter layers parented directly to the group
            # (they are applied in the main composite loop)
            if layer.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER):
                continue
            mask = self._get_effective_mask(layer, stack)
            # Apply child adj/filter layers scoped to this layer
            pixels = layer.pixels
            if layer.id in adj_children:
                pixels = pixels.copy()
                for adj_layer in adj_children[layer.id]:
                    adj = adj_layer.adjustment
                    if adj is not None:
                        pixels = adj.apply(pixels, adj_layer.adjustment_params)
                np.clip(pixels, 0, 1, out=pixels)
            self._blending.blend_region_inplace(
                canvas, pixels, layer.position,
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
    def _place_pixels(pixels: np.ndarray, position: tuple[int, int],
                      cw: int, ch: int) -> np.ndarray:
        """Place arbitrary pixel data at *position* onto a canvas-sized array."""
        canvas = np.zeros((ch, cw, 4), dtype=np.float32)
        lx, ly = position
        lh, lw = pixels.shape[:2]
        sx, sy = max(0, -lx), max(0, -ly)
        dx, dy = max(0, lx), max(0, ly)
        w = min(lw - sx, cw - dx)
        h = min(lh - sy, ch - dy)
        if w > 0 and h > 0:
            canvas[dy : dy + h, dx : dx + w] = pixels[sy : sy + h, sx : sx + w]
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

    def _place_mask_combined(self, layer: Layer, stack: LayerStack,
                             cw: int, ch: int) -> np.ndarray | None:
        """Place the combined mask (legacy + mask layers) onto a canvas."""
        combined = self._get_effective_mask(layer, stack)
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
