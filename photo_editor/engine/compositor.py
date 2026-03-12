"""Layer compositor with clipping-mask, group, and mask-layer support.

Uses ``BlendingEngine.blend_region_inplace`` for fast region-based
compositing — same optimisation strategy as RenderEngine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ..blending.blending_engine import BlendingEngine
from ..core.enums import LayerType
from ..core.layer import Layer
from ..core.layer_stack import LayerStack
from ..masks.mask_manager import MaskManager
from ..styles.style_engine import StyleEngine

if TYPE_CHECKING:
    from .cache.image_pool import ImagePool


class Compositor:
    """Composites a LayerStack into a flat RGBA image."""

    def __init__(self, image_pool: ImagePool | None = None, quality_mode: str = "final") -> None:
        self._blending = BlendingEngine()
        self._pool = image_pool
        self._quality_mode = quality_mode

    @staticmethod
    def _calc_filter_padding(adj_layers: list[Layer]) -> int:
        """Return the pixel padding needed for blur filter overflow.

        When a blur filter is applied to a layer, the blurred result
        extends beyond the original layer boundary.  We need to pad
        the pixel buffer *before* applying the filter so the blur has
        room to extend.  The padding is derived from the filter's
        radius / distance / amount parameter.
        """
        pad = 0
        for adj_layer in adj_layers:
            if adj_layer.layer_type != LayerType.FILTER:
                continue
            params = adj_layer.adjustment_params or {}
            pad = max(
                pad,
                int(
                    max(
                        params.get("radius", 0),
                        params.get("distance", params.get("amount", 0)),
                    )
                ),
            )
        return pad

    def _apply_filters_padded(
        self, pixels: np.ndarray, adj_layers: list[Layer],
    ) -> tuple[np.ndarray, int]:
        """Apply adj/filter layers to *pixels*, adding blur padding.

        Returns (result_pixels, padding) where *padding* is the number
        of pixels added on each side.  The caller must offset the blend
        position by ``-padding`` on both axes to compensate.
        """
        pad = self._calc_filter_padding(adj_layers)
        if pad > 0:
            h, w = pixels.shape[:2]
            padded = np.zeros((h + 2 * pad, w + 2 * pad, 4), dtype=np.float32)
            padded[pad:pad + h, pad:pad + w] = pixels
            pixels = padded
        else:
            pixels = pixels.copy()
        for adj_layer in adj_layers:
            adj = adj_layer.adjustment
            if adj is not None:
                pixels = adj.apply(pixels, adj_layer.adjustment_params)
        np.clip(pixels, 0, 1, out=pixels)
        return pixels, pad

    @staticmethod
    def _processors_support_region_rendering(adj_layers: list[Layer]) -> bool:
        for adj_layer in adj_layers:
            processor = adj_layer.adjustment
            if processor is None:
                continue
            if not processor.supports_region_rendering(adj_layer.adjustment_params or {}):
                return False
        return True

    @staticmethod
    def _apply_region_processors(pixels: np.ndarray, adj_layers: list[Layer]) -> np.ndarray:
        result = pixels.copy()
        for adj_layer in adj_layers:
            processor = adj_layer.adjustment
            if processor is None:
                continue
            result = processor.apply(result, adj_layer.adjustment_params or {})
        np.clip(result, 0, 1, out=result)
        return result

    @staticmethod
    def _processors_region_padding(adj_layers: list[Layer]) -> int:
        padding = 0
        for adj_layer in adj_layers:
            processor = adj_layer.adjustment
            if processor is None:
                continue
            padding += int(processor.region_padding(adj_layer.adjustment_params or {}))
        return padding

    @staticmethod
    def _processors_expand_bounds(adj_layers: list[Layer]) -> bool:
        for adj_layer in adj_layers:
            processor = adj_layer.adjustment
            if processor is None:
                continue
            if processor.expands_bounds(adj_layer.adjustment_params or {}):
                return True
        return False

    @staticmethod
    def _apply_channels(pixels: np.ndarray, layer: Layer) -> np.ndarray:
        if layer.channel_r and layer.channel_g and layer.channel_b and layer.channel_a:
            return pixels
        res = pixels.copy()
        if not layer.channel_r: res[..., 0] = 0.0
        if not layer.channel_g: res[..., 1] = 0.0
        if not layer.channel_b: res[..., 2] = 0.0
        if not layer.channel_a: res[..., 3] = 0.0
        return res

    def _get_effective_mask(self, layer: Layer, stack: LayerStack) -> np.ndarray | None:
        """Compute the combined mask for *layer*.

        Combines the legacy per-layer mask and all child MASK layers.
        """
        return MaskManager.get_combined_mask(layer, stack)

    def _root_filter_padding(self, stack: LayerStack) -> int:
        root_adj_layers = [
            layer for layer in stack
            if layer.visible and layer.parent_id is None
            and layer.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER)
        ]
        return self._calc_filter_padding(root_adj_layers)

    def can_render_region_incrementally(self, stack: LayerStack) -> bool:
        """Return True when region redraw is structurally supported."""
        return True

    def composite_region(
        self,
        stack: LayerStack,
        width: int,
        height: int,
        x: int,
        y: int,
        region_width: int,
        region_height: int,
    ) -> np.ndarray:
        """Composite only a document-space region.

        Root-level filters get extra padding so neighborhood-based operations
        like blur remain correct at tile boundaries before the final crop.
        """
        pad = self._root_filter_padding(stack)
        work_x = max(0, x - pad)
        work_y = max(0, y - pad)
        work_x1 = min(width, x + region_width + pad)
        work_y1 = min(height, y + region_height + pad)
        work = self._composite_at_origin(
            stack,
            work_x1 - work_x,
            work_y1 - work_y,
            work_x,
            work_y,
        )
        crop_x = x - work_x
        crop_y = y - work_y
        return work[crop_y:crop_y + region_height, crop_x:crop_x + region_width].copy()

    def composite(self, stack: LayerStack, width: int, height: int) -> np.ndarray:
        return self._composite_at_origin(stack, width, height, 0, 0)

    def _composite_at_origin(
        self,
        stack: LayerStack,
        width: int,
        height: int,
        origin_x: int,
        origin_y: int,
    ) -> np.ndarray:
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

        # Regular (non-mask, non-adj) children of non-group parents.
        # Groups handle their children via _composite_group; non-group
        # parents clip children to the parent's alpha boundaries.
        group_ids = {l.id for l in layers if l.layer_type == LayerType.GROUP}
        regular_children: dict[str, list[Layer]] = {}
        for l in layers:
            if (l.parent_id and l.visible
                    and l.parent_id not in group_ids
                    and l.layer_type not in (
                        LayerType.ADJUSTMENT, LayerType.FILTER, LayerType.MASK)
                    and l.id not in mask_layer_ids
                    and l.id not in adj_child_ids):
                regular_children.setdefault(l.parent_id, []).append(l)

        # Pre-scan for clipping-mask needs — keep standalone masks in-line
        # Root-level adjustment/filter layers ARE included here; they act as
        # canvas-wide effects applied to everything composited below them
        # (Photoshop adjustment-layer semantics).  Child adj/filter layers are
        # excluded via adj_child_ids (they are applied per-parent instead).
        visible = [
            l for l in layers
            if l.visible and l.parent_id is None
            and l.id not in mask_layer_ids
            and (l.layer_type != LayerType.MASK or l.id in standalone_mask_ids)
            and l.id not in adj_child_ids
        ]
        needs_placed: set[str] = set()
        # Only raster/group/mask layers participate in clipping-mask chains;
        # skip root-level adjustment/filter layers in this scan.
        clippable = [
            l for l in visible
            if l.layer_type not in (LayerType.ADJUSTMENT, LayerType.FILTER)
        ]
        for i in range(len(clippable) - 1):
            if clippable[i + 1].clipping_mask:
                needs_placed.add(clippable[i].id)

        prev_img: np.ndarray | None = None

        for layer in visible:
            # --- Root-level adjustment/filter: apply to accumulated canvas ---
            if layer.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER):
                adj = layer.adjustment
                if adj is not None:
                    canvas = adj.apply(canvas, layer.adjustment_params or {})
                    np.clip(canvas, 0, 1, out=canvas)
                prev_img = None
                continue

            # --- Standalone mask: attenuate canvas built so far --------
            if layer.layer_type == LayerType.MASK and layer.id in standalone_mask_ids:
                gray = layer.get_mask_grayscale()
                placed_gray = (
                    self._pool.acquire((height, width), dtype=np.float32)
                    if self._pool else np.zeros((height, width), dtype=np.float32)
                )
                placed_gray.fill(0)
                lx, ly = layer.position
                mh, mw = gray.shape[:2]
                sx, sy, dx, dy, rw, rh = self._placement_rect(
                    mw, mh, lx, ly, origin_x, origin_y, width, height,
                )
                if rw > 0 and rh > 0:
                    placed_gray[dy:dy + rh, dx:dx + rw] = gray[sy:sy + rh, sx:sx + rw]
                if layer.ex_parent_id:
                    # Detached mask — only attenuate alpha
                    canvas[..., 3] *= placed_gray
                else:
                    # Global standalone mask — attenuate all channels
                    canvas *= placed_gray[..., np.newaxis]
                if self._pool:
                    self._pool.release(placed_gray)
                continue

            if layer.layer_type == LayerType.GROUP:
                group_img = self._composite_group(
                    layer, stack, width, height, origin_x, origin_y,
                )
                # Apply child adj/filter layers scoped to this group
                if layer.id in adj_children:
                    for adj_layer in adj_children[layer.id]:
                        adj = adj_layer.adjustment
                        if adj is not None:
                            group_img = adj.apply(group_img, adj_layer.adjustment_params)
                    np.clip(group_img, 0, 1, out=group_img)
                if layer.styles:
                    group_img = StyleEngine.apply_styles(group_img, layer.styles)
                    np.clip(group_img, 0, 1, out=group_img)
                group_img = self._apply_channels(group_img, layer)
                # Apply mask layers attached to the group
                group_mask = self._get_effective_mask(layer, stack)
                if group_mask is not None:
                    # group_img is canvas-sized; place the mask at the group's
                    # logical position (which is (0,0) for groups).
                    placed_mask = (
                        self._pool.acquire((height, width), dtype=np.float32)
                        if self._pool else np.zeros((height, width), dtype=np.float32)
                    )
                    placed_mask.fill(0)
                    gx, gy = layer.position
                    mh_, mw_ = group_mask.shape[:2]
                    sx_, sy_, dx_, dy_, rw_, rh_ = self._placement_rect(
                        mw_, mh_, gx, gy, origin_x, origin_y, width, height,
                    )
                    if rw_ > 0 and rh_ > 0:
                        placed_mask[dy_:dy_ + rh_, dx_:dx_ + rw_] = group_mask[sy_:sy_ + rh_, sx_:sx_ + rw_]
                    group_img[..., 3] *= placed_mask
                    if self._pool:
                        self._pool.release(placed_mask)
                self._blending.blend_region_inplace(
                    canvas, group_img, (0, 0),
                    layer.blend_mode, layer.opacity,
                )
                prev_img = group_img
                continue

            # Combined mask: legacy mask + mask layers
            mask = self._get_effective_mask(layer, stack)

            pixels, blend_pos = self._layer_pixels_for_canvas(
                layer, width, height, origin_x, origin_y, adj_children,
            )

            # Check whether any regular child clips the parent
            _has_clip_child = False
            if layer.id in regular_children:
                for _rc in regular_children[layer.id]:
                    if _rc.clips_parent:
                        _has_clip_child = True
                        break

            if layer.clipping_mask and prev_img is not None:
                placed = self._place_pixels(pixels, blend_pos, width, height, origin_x, origin_y)
                placed[..., 3:4] *= prev_img[..., 3:4]
                placed_mask = (
                    self._place_mask_combined(layer, stack, width, height, origin_x, origin_y)
                    if mask is not None else None
                )
                self._blending.blend_region_inplace(
                    canvas, placed, (0, 0),
                    layer.blend_mode, layer.opacity, placed_mask,
                )
                prev_img = placed

            elif _has_clip_child:
                # Delayed blend: clips_parent children restrict the
                # parent's visible area before it is composited.
                parent_placed = self._place_pixels(
                    pixels, blend_pos, width, height, origin_x, origin_y)
                for child in regular_children[layer.id]:
                    if not child.clips_parent:
                        continue
                    c_pix, c_pos = self._layer_pixels_for_canvas(
                        child, width, height, origin_x, origin_y, adj_children,
                    )
                    c_placed = self._place_pixels(c_pix, c_pos, width, height, origin_x, origin_y)
                    parent_placed[..., 3:4] *= c_placed[..., 3:4]
                # Blend the clipped parent onto the canvas
                placed_mask = (
                    self._place_mask_combined(layer, stack, width, height, origin_x, origin_y)
                    if mask is not None else None
                )
                self._blending.blend_region_inplace(
                    canvas, parent_placed, (0, 0),
                    layer.blend_mode, layer.opacity, placed_mask,
                )
                # Composite remaining non-clip children (clipped to parent)
                for child in regular_children[layer.id]:
                    if child.clips_parent:
                        continue
                    c_mask = self._get_effective_mask(child, stack)
                    c_pix, c_pos = self._layer_pixels_for_canvas(
                        child, width, height, origin_x, origin_y, adj_children,
                    )
                    c_placed = self._place_pixels(c_pix, c_pos, width, height, origin_x, origin_y)
                    c_placed[..., 3:4] *= parent_placed[..., 3:4]
                    c_placed_mask = (
                        self._place_mask_combined(child, stack, width, height, origin_x, origin_y)
                        if c_mask is not None else None
                    )
                    self._blending.blend_region_inplace(
                        canvas, c_placed, (0, 0),
                        child.blend_mode, child.opacity, c_placed_mask,
                    )
                prev_img = parent_placed

            else:
                self._blending.blend_region_inplace(
                    canvas, pixels, (blend_pos[0] - origin_x, blend_pos[1] - origin_y),
                    layer.blend_mode, layer.opacity, mask,
                )
                if layer.id in needs_placed:
                    prev_img = self._place_pixels(pixels, blend_pos, width, height, origin_x, origin_y)
                else:
                    prev_img = None

                # --- Regular children of non-group parents ---
                # Each child is composited clipped to the parent's alpha.
                if layer.id in regular_children:
                    parent_placed = prev_img
                    if parent_placed is None:
                        parent_placed = self._place_pixels(
                            pixels, blend_pos, width, height, origin_x, origin_y)
                    for child in regular_children[layer.id]:
                        c_mask = self._get_effective_mask(child, stack)
                        c_pix, c_pos = self._layer_pixels_for_canvas(
                            child, width, height, origin_x, origin_y, adj_children,
                        )
                        c_placed = self._place_pixels(c_pix, c_pos, width, height, origin_x, origin_y)
                        c_placed[..., 3:4] *= parent_placed[..., 3:4]
                        c_placed_mask = (
                            self._place_mask_combined(child, stack, width, height, origin_x, origin_y)
                            if c_mask is not None else None
                        )
                        self._blending.blend_region_inplace(
                            canvas, c_placed, (0, 0),
                            child.blend_mode, child.opacity, c_placed_mask,
                        )
                    prev_img = parent_placed

        return canvas

    def _composite_group(
        self, group: Layer, stack: LayerStack, w: int, h: int,
        origin_x: int = 0, origin_y: int = 0,
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

        # Build regular (non-mask, non-adj) children map for group members.
        # These are clips_parent / normal children of layers within this group.
        regular_children: dict[str, list[Layer]] = {}
        for layer in stack:
            if (layer.parent_id and layer.visible
                    and layer.parent_id in group_child_ids
                    and layer.parent_id != group.id
                    and layer.layer_type not in (
                        LayerType.ADJUSTMENT, LayerType.FILTER, LayerType.MASK)
                    and layer.id not in mask_ids
                    and layer.id not in adj_child_ids):
                regular_children.setdefault(layer.parent_id, []).append(layer)

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
            if layer.styles:
                pixels = StyleEngine.apply_styles(pixels, layer.styles)
            pixels = self._apply_channels(pixels, layer)
            blend_pos = layer.position
            if layer.id in adj_children:
                pixels, pad = self._apply_filters_padded(
                    pixels, adj_children[layer.id],
                )
                if pad > 0:
                    blend_pos = (layer.position[0] - pad,
                                 layer.position[1] - pad)

            # Check whether any regular child clips the parent
            _has_clip_child = False
            if layer.id in regular_children:
                for _rc in regular_children[layer.id]:
                    if _rc.clips_parent:
                        _has_clip_child = True
                        break

            if _has_clip_child:
                # Delayed blend: clips_parent children restrict the
                # parent's visible area before it is composited.
                parent_placed = self._place_pixels(
                    pixels, blend_pos, w, h, origin_x, origin_y)
                for child in regular_children[layer.id]:
                    if not child.clips_parent:
                        continue
                    c_pix, c_pos = self._layer_pixels_for_canvas(
                        child, w, h, origin_x, origin_y, adj_children,
                    )
                    c_placed = self._place_pixels(c_pix, c_pos, w, h, origin_x, origin_y)
                    parent_placed[..., 3:4] *= c_placed[..., 3:4]
                # Blend the clipped parent onto the group canvas
                placed_mask = (
                    self._place_mask_combined(layer, stack, w, h, origin_x, origin_y)
                    if mask is not None else None
                )
                self._blending.blend_region_inplace(
                    canvas, parent_placed, (0, 0),
                    layer.blend_mode, layer.opacity, placed_mask,
                )
                # Composite remaining non-clip children (clipped to parent)
                for child in regular_children[layer.id]:
                    if child.clips_parent:
                        continue
                    c_mask = self._get_effective_mask(child, stack)
                    c_pix, c_pos = self._layer_pixels_for_canvas(
                        child, w, h, origin_x, origin_y, adj_children,
                    )
                    c_placed = self._place_pixels(c_pix, c_pos, w, h, origin_x, origin_y)
                    c_placed[..., 3:4] *= parent_placed[..., 3:4]
                    c_placed_mask = (
                        self._place_mask_combined(child, stack, w, h, origin_x, origin_y)
                        if c_mask is not None else None
                    )
                    self._blending.blend_region_inplace(
                        canvas, c_placed, (0, 0),
                        child.blend_mode, child.opacity, c_placed_mask,
                    )
            else:
                self._blending.blend_region_inplace(
                    canvas, pixels, (blend_pos[0] - origin_x, blend_pos[1] - origin_y),
                    layer.blend_mode, layer.opacity, mask,
                )
                # Regular children of non-group parents within the group
                if layer.id in regular_children:
                    parent_placed = self._place_pixels(
                        pixels, blend_pos, w, h, origin_x, origin_y)
                    for child in regular_children[layer.id]:
                        c_mask = self._get_effective_mask(child, stack)
                        c_pix, c_pos = self._layer_pixels_for_canvas(
                            child, w, h, origin_x, origin_y, adj_children,
                        )
                        c_placed = self._place_pixels(c_pix, c_pos, w, h, origin_x, origin_y)
                        c_placed[..., 3:4] *= parent_placed[..., 3:4]
                        c_placed_mask = (
                            self._place_mask_combined(child, stack, w, h, origin_x, origin_y)
                            if c_mask is not None else None
                        )
                        self._blending.blend_region_inplace(
                            canvas, c_placed, (0, 0),
                            child.blend_mode, child.opacity, c_placed_mask,
                        )
        return canvas

    def _layer_bounds(self, layer: Layer, stack: LayerStack) -> tuple[float, float, float, float] | None:
        """Return (min_x, min_y, max_x, max_y) for a layer, including nested groups."""
        if layer.layer_type == LayerType.GROUP:
            min_x, min_y = float("inf"), float("inf")
            max_x, max_y = float("-inf"), float("-inf")
            found = False
            for child in stack:
                if child.parent_id != layer.id or not child.visible:
                    continue
                if child.layer_type in (LayerType.MASK, LayerType.ADJUSTMENT, LayerType.FILTER):
                    continue
                cb = self._layer_bounds(child, stack)
                if cb is None:
                    continue
                cx0, cy0, cx1, cy1 = cb
                min_x = min(min_x, cx0)
                min_y = min(min_y, cy0)
                max_x = max(max_x, cx1)
                max_y = max(max_y, cy1)
                found = True
            return (min_x, min_y, max_x, max_y) if found else None
        try:
            lx, ly = layer.position
            lw = int(layer.width)
            lh = int(layer.height)
            return (float(lx), float(ly), float(lx + lw), float(ly + lh))
        except (AttributeError, IndexError, TypeError, ValueError):
            return None

    def _layer_pixels_for_canvas(
        self,
        layer: Layer,
        canvas_w: int,
        canvas_h: int,
        origin_x: int,
        origin_y: int,
        adj_children: dict,
    ) -> tuple[np.ndarray | None, tuple[int, int]]:
        position = layer.position
        child_processors = adj_children.get(layer.id, [])
        region_styles_supported = (not layer.styles) or StyleEngine.can_apply_styles_regionally(layer.styles)
        region_processors_supported = (not child_processors) or self._processors_support_region_rendering(child_processors)
        style_padding = StyleEngine.style_region_padding(layer.styles) if layer.styles else 0
        processor_padding = self._processors_region_padding(child_processors) if child_processors else 0
        effect_padding = style_padding + processor_padding
        if (
            self._quality_mode == "preview"
            and
            layer.layer_type != LayerType.GROUP
            and region_styles_supported
            and region_processors_supported
            and layer.can_decode_display_roi()
        ):
            decoded = layer.decode_display_roi_padded(
                origin_x - effect_padding,
                origin_y - effect_padding,
                canvas_w + effect_padding * 2,
                canvas_h + effect_padding * 2,
                position=position,
            )
            if decoded is not None:
                pixels, position = decoded
                offset_x = position[0] - layer.position[0]
                offset_y = position[1] - layer.position[1]
                if layer.styles:
                    pixels = StyleEngine.apply_styles_region(
                        pixels,
                        layer.styles,
                        offset_x,
                        offset_y,
                        int(layer.width),
                        int(layer.height),
                    )
                pixels = self._apply_channels(pixels, layer)
                if child_processors:
                    pixels = self._apply_region_processors(pixels, child_processors)
                return pixels, position

        pixels = layer.pixels
        if layer.styles:
            pixels = StyleEngine.apply_styles(pixels, layer.styles)
        pixels = self._apply_channels(pixels, layer)
        if layer.id in adj_children:
            pixels, pad = self._apply_filters_padded(
                pixels, adj_children[layer.id],
            )
            if pad > 0:
                position = (layer.position[0] - pad, layer.position[1] - pad)
        return pixels, position

    def _get_layer_pixels(self, layer: Layer, stack: LayerStack,
                          adj_children: dict) -> np.ndarray | None:
        """Get pixels for a layer; for groups, recursively composite."""
        if layer.layer_type == LayerType.GROUP:
            pixels = self.composite_group_tight(layer, stack)
        else:
            pixels = layer.pixels
        if pixels is None or pixels.size == 0:
            return None
        if layer.styles:
            pixels = StyleEngine.apply_styles(pixels, layer.styles)
        pixels = self._apply_channels(pixels, layer)
        if layer.id in adj_children:
            pixels, _pad = self._apply_filters_padded(
                pixels, adj_children[layer.id],
            )
        return pixels

    def composite_group_tight(self, group: Layer, stack: LayerStack) -> np.ndarray | None:
        """Composite a group's children into a tight bounding-box buffer.

        Recursively composites nested groups so a group can contain groups.
        Returns a float32 RGBA array of shape (H, W, 4), or None if the
        group has no visible children. Used for group layer thumbnails.
        """
        min_x, min_y = float("inf"), float("inf")
        max_x, max_y = float("-inf"), float("-inf")
        found = False
        for layer in stack:
            if layer.parent_id != group.id or not layer.visible:
                continue
            if layer.layer_type in (LayerType.MASK, LayerType.ADJUSTMENT, LayerType.FILTER):
                continue
            bounds = self._layer_bounds(layer, stack)
            if bounds is None:
                continue
            cx0, cy0, cx1, cy1 = bounds
            min_x = min(min_x, cx0)
            min_y = min(min_y, cy0)
            max_x = max(max_x, cx1)
            max_y = max(max_y, cy1)
            found = True
        if not found:
            return None
        bw = max(1, int(max_x - min_x))
        bh = max(1, int(max_y - min_y))

        canvas = np.zeros((bh, bw, 4), dtype=np.float32)
        group_child_ids = {l.id for l in stack if l.parent_id == group.id}
        mask_ids = {mid for l in stack if l.parent_id == group.id for mid in l.mask_layers}
        adj_children: dict[str, list] = {}
        adj_child_ids: set[str] = set()
        for layer in stack:
            if (layer.parent_id and layer.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER)
                    and layer.visible and layer.parent_id in group_child_ids):
                adj_children.setdefault(layer.parent_id, []).append(layer)
                adj_child_ids.add(layer.id)
        for layer in stack:
            if layer.parent_id != group.id or not layer.visible:
                continue
            if layer.id in mask_ids or layer.layer_type == LayerType.MASK:
                continue
            if layer.id in adj_child_ids or layer.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER):
                continue
            bounds = self._layer_bounds(layer, stack)
            if bounds is None:
                continue
            cx0, cy0, _, _ = bounds
            rel_x = int(cx0 - min_x)
            rel_y = int(cy0 - min_y)
            mask = self._get_effective_mask(layer, stack)
            pixels = self._get_layer_pixels(layer, stack, adj_children)
            if pixels is None or pixels.size == 0:
                continue
            self._blending.blend_region_inplace(
                canvas, pixels, (rel_x, rel_y),
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
    def _placement_rect(
        src_w: int,
        src_h: int,
        pos_x: int,
        pos_y: int,
        origin_x: int,
        origin_y: int,
        canvas_w: int,
        canvas_h: int,
    ) -> tuple[int, int, int, int, int, int]:
        sx = max(0, origin_x - pos_x)
        sy = max(0, origin_y - pos_y)
        dx = max(0, pos_x - origin_x)
        dy = max(0, pos_y - origin_y)
        width = min(src_w - sx, canvas_w - dx)
        height = min(src_h - sy, canvas_h - dy)
        return sx, sy, dx, dy, max(0, width), max(0, height)

    @staticmethod
    def _place_pixels(pixels: np.ndarray, position: tuple[int, int],
                      cw: int, ch: int,
                      origin_x: int = 0, origin_y: int = 0) -> np.ndarray:
        """Place arbitrary pixel data at *position* onto a canvas-sized array."""
        canvas = np.zeros((ch, cw, 4), dtype=np.float32)
        lx, ly = position
        lh, lw = pixels.shape[:2]
        sx, sy, dx, dy, w, h = Compositor._placement_rect(
            lw, lh, lx, ly, origin_x, origin_y, cw, ch,
        )
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
                             cw: int, ch: int,
                             origin_x: int = 0, origin_y: int = 0) -> np.ndarray | None:
        """Place the combined mask (legacy + mask layers) onto a canvas."""
        combined = self._get_effective_mask(layer, stack)
        if combined is None:
            return None
        canvas = np.zeros((ch, cw), dtype=np.float32)
        lx, ly = layer.position
        mh, mw = combined.shape[:2]
        sx, sy, dx, dy, w, h = self._placement_rect(
            mw, mh, lx, ly, origin_x, origin_y, cw, ch,
        )
        if w > 0 and h > 0:
            canvas[dy : dy + h, dx : dx + w] = combined[sy : sy + h, sx : sx + w]
        return canvas
