"""Tile-based compositor — processes the document in fixed-size tiles.

Each tile is composited independently, enabling:
- Incremental re-render: only dirty tiles are recomposited
- Layer intersection culling: layers that don't touch a tile are skipped
- Reduced memory: tile-sized buffers (~256 KB) vs full-canvas (~32 MB at 1080p)
- Cancellation: cancel token checked between tiles for fast abort

Architecture
------------
1. **Pre-process** (per-layer, once per composite call):
   Apply styles, channel toggles, and child adjustment/filter layers.
   This produces *prepared* pixel data + adjusted blend positions.

2. **Tile loop** (per-tile):
   For each tile, iterate only layers whose bounding box intersects the
   tile rectangle.  Extract tile-sized regions, handle clipping/masking
   at tile granularity, and blend into a tile-sized canvas.

3. **Tile cache** (cross-frame):
   Cached tile buffers are reused when a tile is not dirty.  Tools call
   ``invalidate_region()`` to mark only the tiles they touched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from ..blending.blending_engine import BlendingEngine
from ..core.enums import BlendMode, LayerType
from ..masks.mask_manager import MaskManager
from ..styles.style_engine import StyleEngine
from .compositor import _TopologyCache
from .mip_cache import MipCache, mip_level_for_scale

if TYPE_CHECKING:
    from ..core.layer import Layer
    from ..core.layer_stack import LayerStack
    from .cache.image_pool import ImagePool
    from .renderer.cancel_token import CancelToken

TILE_SIZE = 256


# =====================================================================
# Tile coordinate helpers
# =====================================================================

@dataclass(frozen=True, slots=True)
class TileCoord:
    """Pixel-space rectangle for a single tile."""
    x: int
    y: int
    w: int
    h: int


def compute_tile_grid(width: int, height: int, tile_size: int = TILE_SIZE) -> list[TileCoord]:
    tiles: list[TileCoord] = []
    for ty in range(0, height, tile_size):
        for tx in range(0, width, tile_size):
            tw = min(tile_size, width - tx)
            th = min(tile_size, height - ty)
            tiles.append(TileCoord(tx, ty, tw, th))
    return tiles


def _intersects(ax: int, ay: int, aw: int, ah: int,
                bx: int, by: int, bw: int, bh: int) -> bool:
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


# =====================================================================
# Prepared-layer record
# =====================================================================

@dataclass(slots=True)
class _Prepared:
    """Pre-processed layer data ready for per-tile blending."""
    layer: object
    pixels: np.ndarray
    position: tuple[int, int]
    mask: np.ndarray | None
    blend_mode: BlendMode
    opacity: float
    layer_type: LayerType
    is_clipping: bool
    has_clip_children: bool
    clip_children: list[_Prepared]
    regular_children: list[_Prepared]
    is_group: bool = False
    group_prepared: list[_Prepared] | None = None
    is_standalone_mask: bool = False
    ex_parent_id: str | None = None
    needs_placed: bool = False
    has_alpha: bool = True


# =====================================================================
# Tile-level placement helpers
# =====================================================================

def _extract_to_tile(pixels: np.ndarray, position: tuple[int, int],
                     tile: TileCoord) -> np.ndarray | None:
    """Extract the portion of *pixels* (at *position*) that overlaps *tile*.

    Returns a (tile.h, tile.w, C) buffer with the overlap region placed
    at the correct offset, or ``None`` when there is no intersection.
    """
    lx, ly = position
    lh, lw = pixels.shape[:2]
    if not _intersects(lx, ly, lw, lh, tile.x, tile.y, tile.w, tile.h):
        return None
    channels = pixels.shape[2] if pixels.ndim == 3 else 0
    if channels:
        buf = np.zeros((tile.h, tile.w, channels), dtype=pixels.dtype)
    else:
        buf = np.zeros((tile.h, tile.w), dtype=pixels.dtype)
    # overlap in canvas space
    ox = max(lx, tile.x)
    oy = max(ly, tile.y)
    ox2 = min(lx + lw, tile.x + tile.w)
    oy2 = min(ly + lh, tile.y + tile.h)
    ow, oh = ox2 - ox, oy2 - oy
    # source coords in layer
    sx = ox - lx
    sy = oy - ly
    # dest coords in tile
    dx = ox - tile.x
    dy = oy - tile.y
    if channels:
        buf[dy:dy + oh, dx:dx + ow] = pixels[sy:sy + oh, sx:sx + ow]
    else:
        buf[dy:dy + oh, dx:dx + ow] = pixels[sy:sy + oh, sx:sx + ow]
    return buf


# =====================================================================
# TileCompositor
# =====================================================================

class TileCompositor:
    """Composites a layer stack tile-by-tile with caching and dirty tracking."""

    def __init__(
        self,
        tile_size: int = TILE_SIZE,
        image_pool: ImagePool | None = None,
        use_float16: bool = False,
    ) -> None:
        self.tile_size = tile_size
        self._blending = BlendingEngine()
        self._pool = image_pool
        self._use_float16 = use_float16
        self._mip_cache = MipCache()
        # Tile cache: (tx, ty) -> np.ndarray  (tile data)
        self._cache: dict[tuple[int, int], np.ndarray] = {}
        self._canvas_w = 0
        self._canvas_h = 0

    @property
    def tile_dtype(self) -> np.dtype:
        return np.float16 if self._use_float16 else np.float32

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def invalidate_all(self) -> None:
        self._cache.clear()
        self._mip_cache.clear()

    def invalidate_region(self, x: int, y: int, w: int, h: int) -> None:
        ts = self.tile_size
        x0 = max(0, (x // ts) * ts)
        y0 = max(0, (y // ts) * ts)
        for ty in range(y0, y + h, ts):
            for tx in range(x0, x + w, ts):
                self._cache.pop((tx, ty), None)

    def composite(
        self,
        stack,
        width: int,
        height: int,
        cancel_token: CancelToken | None = None,
        mip_level: int = 0,
    ) -> np.ndarray:
        """Composite the full document via tiled rendering.

        *mip_level* selects the pre-downsampled layer pyramid:
          0 = full resolution, 1 = 1:2, 2 = 1:4, 3 = 1:8.
        When mip > 0, compositing runs at reduced resolution and the
        result is upscaled to the original dimensions.

        Returns a (height, width, 4) float32 RGBA canvas.
        """
        if width != self._canvas_w or height != self._canvas_h:
            self._cache.clear()
            self._canvas_w = width
            self._canvas_h = height

        # Mip-level rendering: composite at reduced size, then upscale
        if mip_level > 0:
            divisor = 1 << mip_level
            mip_w = max(1, width // divisor)
            mip_h = max(1, height // divisor)
            mip_canvas = self._composite_at_size(
                stack, width, height, mip_w, mip_h,
                cancel_token, mip_level,
            )
            try:
                import cv2
                return cv2.resize(
                    mip_canvas, (width, height),
                    interpolation=cv2.INTER_LINEAR,
                )
            except ImportError:
                return mip_canvas

        return self._composite_at_size(
            stack, width, height, width, height, cancel_token, 0,
        )

    def _composite_at_size(
        self,
        stack,
        orig_w: int,
        orig_h: int,
        target_w: int,
        target_h: int,
        cancel_token: CancelToken | None,
        mip_level: int,
    ) -> np.ndarray:
        """Internal: composite at *target* dimensions using *mip_level* data."""
        canvas = np.zeros((target_h, target_w, 4), dtype=np.float32)
        layers = list(stack)
        topo = _TopologyCache.build(layers)

        prepared = self._prepare_visible(topo, stack, mip_level=mip_level)

        tiles = compute_tile_grid(target_w, target_h, self.tile_size)
        for tile in tiles:
            if cancel_token is not None and cancel_token.is_cancelled:
                from .renderer.cancel_token import RenderCancelled
                raise RenderCancelled()

            # Only use tile cache for mip=0 (full res) since mip renders
            # are transient preview frames.
            if mip_level == 0:
                key = (tile.x, tile.y)
                cached = self._cache.get(key)
                if cached is not None and cached.shape[:2] == (tile.h, tile.w):
                    canvas[tile.y:tile.y + tile.h,
                           tile.x:tile.x + tile.w] = cached
                    continue

            tile_data = self._composite_tile(
                tile, prepared, stack, target_w, target_h)

            if mip_level == 0:
                if self._use_float16:
                    self._cache[key] = tile_data.astype(np.float16)
                else:
                    self._cache[key] = tile_data

            canvas[tile.y:tile.y + tile.h,
                   tile.x:tile.x + tile.w] = tile_data

        return canvas

    def composite_snapshot(self, snapshot) -> np.ndarray:
        from .compositor import _SnapshotStackAdapter
        adapter = _SnapshotStackAdapter(snapshot)
        return self.composite(adapter, snapshot.width, snapshot.height)

    # ------------------------------------------------------------------
    # Layer pre-processing
    # ------------------------------------------------------------------

    @staticmethod
    def _calc_filter_padding(adj_layers: list) -> int:
        pad = 0
        for adj_layer in adj_layers:
            if adj_layer.layer_type != LayerType.FILTER:
                continue
            params = adj_layer.adjustment_params or {}
            r = params.get("radius",
                    params.get("distance",
                    params.get("amount", 0)))
            try:
                pad = max(pad, int(float(r) * 3) + 4)
            except (TypeError, ValueError):
                pass
        return pad

    @staticmethod
    def _apply_filters_padded(pixels: np.ndarray, adj_layers: list) -> tuple[np.ndarray, int]:
        pad = TileCompositor._calc_filter_padding(adj_layers)
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
    def _apply_channels(pixels: np.ndarray, layer) -> np.ndarray:
        if layer.channel_r and layer.channel_g and layer.channel_b and layer.channel_a:
            return pixels
        res = pixels.copy()
        if not layer.channel_r: res[..., 0] = 0.0
        if not layer.channel_g: res[..., 1] = 0.0
        if not layer.channel_b: res[..., 2] = 0.0
        if not layer.channel_a: res[..., 3] = 0.0
        return res

    def _process_layer(
        self, layer, adj_children: dict, stack, mip_level: int = 0,
    ) -> tuple[np.ndarray, tuple[int, int], np.ndarray | None]:
        """Apply styles, channels, adj/filters to a single layer.

        Returns (pixels, blend_position, mask).
        """
        pixels = layer.pixels
        if layer.styles:
            pixels = StyleEngine.apply_styles(pixels, layer.styles)
        pixels = self._apply_channels(pixels, layer)
        blend_pos = layer.position
        if layer.id in adj_children:
            pixels, pad = self._apply_filters_padded(pixels, adj_children[layer.id])
            if pad > 0:
                blend_pos = (layer.position[0] - pad, layer.position[1] - pad)
        mask = MaskManager.get_combined_mask(layer, stack)

        # Apply mip-level downsampling after all per-layer processing
        if mip_level > 0:
            pixels, blend_pos = self._mip_cache.get(
                layer.id, pixels, blend_pos, mip_level)
            if mask is not None:
                mask = self._mip_cache.get_mask(
                    layer.id + '_mask', mask, mip_level)

        return pixels, blend_pos, mask

    def _prepare_child(
        self, child, adj_children: dict, stack, mip_level: int = 0,
    ) -> _Prepared:
        pixels, pos, mask = self._process_layer(
            child, adj_children, stack, mip_level)
        return _Prepared(
            layer=child, pixels=pixels, position=pos, mask=mask,
            blend_mode=child.blend_mode, opacity=child.opacity,
            layer_type=child.layer_type,
            is_clipping=False, has_clip_children=False,
            clip_children=[], regular_children=[],
            has_alpha=getattr(child, 'has_alpha', True),
        )

    def _prepare_visible(
        self, topo: _TopologyCache, stack, mip_level: int = 0,
    ) -> list[_Prepared]:
        adj_children = topo.adj_children
        result: list[_Prepared] = []

        for layer in topo.visible:
            # Root adjustment/filter
            if layer.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER):
                result.append(_Prepared(
                    layer=layer, pixels=np.empty((0, 0, 4), dtype=np.float32),
                    position=(0, 0), mask=None,
                    blend_mode=layer.blend_mode, opacity=layer.opacity,
                    layer_type=layer.layer_type,
                    is_clipping=False, has_clip_children=False,
                    clip_children=[], regular_children=[],
                ))
                continue

            # Standalone mask
            if layer.layer_type == LayerType.MASK and layer.id in topo.standalone_mask_ids:
                gray = layer.get_mask_grayscale()
                pos = layer.position
                if mip_level > 0:
                    gray = self._mip_cache.get_mask(
                        layer.id + '_smask', gray, mip_level)
                    divisor = 1 << mip_level
                    pos = (pos[0] // divisor, pos[1] // divisor)
                result.append(_Prepared(
                    layer=layer,
                    pixels=gray[..., np.newaxis] if gray.ndim == 2 else gray,
                    position=pos, mask=None,
                    blend_mode=layer.blend_mode, opacity=layer.opacity,
                    layer_type=LayerType.MASK,
                    is_clipping=False, has_clip_children=False,
                    clip_children=[], regular_children=[],
                    is_standalone_mask=True,
                    ex_parent_id=layer.ex_parent_id,
                ))
                continue

            # Group
            if layer.layer_type == LayerType.GROUP:
                group_prepared = self._prepare_group_children(
                    layer, topo, stack, mip_level)
                gmask = MaskManager.get_combined_mask(layer, stack)
                gpos = layer.position
                if mip_level > 0 and gmask is not None:
                    gmask = self._mip_cache.get_mask(
                        layer.id + '_gmask', gmask, mip_level)
                    divisor = 1 << mip_level
                    gpos = (gpos[0] // divisor, gpos[1] // divisor)
                result.append(_Prepared(
                    layer=layer, pixels=np.empty((0, 0, 4), dtype=np.float32),
                    position=gpos, mask=gmask,
                    blend_mode=layer.blend_mode, opacity=layer.opacity,
                    layer_type=LayerType.GROUP,
                    is_clipping=False, has_clip_children=False,
                    clip_children=[], regular_children=[],
                    is_group=True, group_prepared=group_prepared,
                ))
                continue

            # Skip transparent layers
            if not getattr(layer, 'has_alpha', True):
                result.append(_Prepared(
                    layer=layer,
                    pixels=np.empty((0, 0, 4), dtype=np.float32),
                    position=layer.position, mask=None,
                    blend_mode=layer.blend_mode, opacity=layer.opacity,
                    layer_type=layer.layer_type,
                    is_clipping=False, has_clip_children=False,
                    clip_children=[], regular_children=[],
                    has_alpha=False,
                ))
                continue

            # Normal raster layer
            pixels, blend_pos, mask = self._process_layer(
                layer, adj_children, stack, mip_level)

            # Prepare clip and regular children
            clip_children: list[_Prepared] = []
            reg_children: list[_Prepared] = []
            has_clip_child = False
            if layer.id in topo.regular_children:
                for rc in topo.regular_children[layer.id]:
                    child_prep = self._prepare_child(
                        rc, adj_children, stack, mip_level)
                    if rc.clips_parent:
                        child_prep.is_clipping = True
                        clip_children.append(child_prep)
                        has_clip_child = True
                    else:
                        reg_children.append(child_prep)

            result.append(_Prepared(
                layer=layer, pixels=pixels, position=blend_pos, mask=mask,
                blend_mode=layer.blend_mode, opacity=layer.opacity,
                layer_type=layer.layer_type,
                is_clipping=layer.clipping_mask,
                has_clip_children=has_clip_child,
                clip_children=clip_children,
                regular_children=reg_children,
                needs_placed=layer.id in topo.needs_placed,
                has_alpha=getattr(layer, 'has_alpha', True),
            ))

        return result

    def _prepare_group_children(
        self, group, topo: _TopologyCache, stack, mip_level: int = 0,
    ) -> list[_Prepared]:
        """Prepare the direct children of a group for per-tile compositing."""
        adj_children = topo.adj_children
        layers = list(stack)

        mask_ids: set[str] = set()
        group_child_ids: set[str] = set()
        for layer in layers:
            if layer.parent_id == group.id:
                group_child_ids.add(layer.id)
                for mid in layer.mask_layers:
                    mask_ids.add(mid)

        local_adj: dict[str, list] = {}
        local_adj_ids: set[str] = set()
        for layer in layers:
            if (layer.parent_id
                    and layer.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER)
                    and layer.visible
                    and layer.parent_id in group_child_ids):
                local_adj.setdefault(layer.parent_id, []).append(layer)
                local_adj_ids.add(layer.id)

        local_regular: dict[str, list] = {}
        for layer in layers:
            if (layer.parent_id and layer.visible
                    and layer.parent_id in group_child_ids
                    and layer.parent_id != group.id
                    and layer.layer_type not in (
                        LayerType.ADJUSTMENT, LayerType.FILTER, LayerType.MASK)
                    and layer.id not in mask_ids
                    and layer.id not in local_adj_ids):
                local_regular.setdefault(layer.parent_id, []).append(layer)

        # Merge group-local adj children with global adj_children for
        # child layers that also appear in the global map.
        merged_adj = dict(adj_children)
        merged_adj.update(local_adj)

        prepared: list[_Prepared] = []
        for layer in layers:
            if layer.parent_id != group.id or not layer.visible:
                continue
            if layer.id in mask_ids or layer.layer_type == LayerType.MASK:
                continue
            if layer.id in local_adj_ids:
                continue
            if layer.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER):
                continue

            pixels, blend_pos, mask = self._process_layer(
                layer, merged_adj, stack, mip_level)

            clip_children: list[_Prepared] = []
            reg_children: list[_Prepared] = []
            has_clip_child = False
            if layer.id in local_regular:
                for rc in local_regular[layer.id]:
                    child_prep = self._prepare_child(
                        rc, merged_adj, stack, mip_level)
                    if rc.clips_parent:
                        child_prep.is_clipping = True
                        clip_children.append(child_prep)
                        has_clip_child = True
                    else:
                        reg_children.append(child_prep)

            prepared.append(_Prepared(
                layer=layer, pixels=pixels, position=blend_pos, mask=mask,
                blend_mode=layer.blend_mode, opacity=layer.opacity,
                layer_type=layer.layer_type,
                is_clipping=False, has_clip_children=has_clip_child,
                clip_children=clip_children,
                regular_children=reg_children,
                has_alpha=getattr(layer, 'has_alpha', True),
            ))

        return prepared

    # ------------------------------------------------------------------
    # Per-tile compositing
    # ------------------------------------------------------------------

    def _composite_tile(
        self,
        tile: TileCoord,
        prepared: list[_Prepared],
        stack,
        cw: int,
        ch: int,
    ) -> np.ndarray:
        """Composite all visible layers for a single tile."""
        tile_canvas = np.zeros((tile.h, tile.w, 4), dtype=np.float32)
        prev_tile: np.ndarray | None = None

        for prep in prepared:
            # Root adjustment/filter: apply to accumulated tile canvas
            if prep.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER):
                adj = prep.layer.adjustment
                if adj is not None:
                    tile_canvas = adj.apply(tile_canvas, prep.layer.adjustment_params or {})
                    np.clip(tile_canvas, 0, 1, out=tile_canvas)
                prev_tile = None
                continue

            # Standalone mask: attenuate accumulated tile canvas
            if prep.is_standalone_mask:
                gray_tile = _extract_to_tile(
                    prep.layer.get_mask_grayscale(), prep.position, tile)
                if gray_tile is None:
                    gray_tile = np.zeros((tile.h, tile.w), dtype=np.float32)
                if prep.ex_parent_id:
                    tile_canvas[..., 3] *= gray_tile
                else:
                    tile_canvas *= gray_tile[..., np.newaxis]
                continue

            # Group: composite children per-tile, then apply group attrs
            if prep.is_group:
                group_tile = self._composite_group_tile(
                    tile, prep, stack, cw, ch)
                self._blending.blend_region_inplace(
                    tile_canvas, group_tile, (0, 0),
                    prep.blend_mode, prep.opacity,
                )
                prev_tile = group_tile
                continue

            # Skip transparent
            if not prep.has_alpha:
                prev_tile = None
                continue

            # Layer doesn't touch this tile at all -> skip
            ph, pw = prep.pixels.shape[:2]
            if not _intersects(prep.position[0], prep.position[1], pw, ph,
                               tile.x, tile.y, tile.w, tile.h):
                # Clipping chain: if this layer is needed for clipping,
                # produce a blank prev_tile so the next clipping layer
                # clips to nothing in this tile.
                if prep.needs_placed:
                    prev_tile = np.zeros((tile.h, tile.w, 4), dtype=np.float32)
                else:
                    prev_tile = None
                continue

            # Tile-relative position for blending
            rel_pos = (prep.position[0] - tile.x, prep.position[1] - tile.y)

            # Clipping mask: clip to prev_tile alpha
            if prep.is_clipping and prev_tile is not None:
                placed = _extract_to_tile(prep.pixels, prep.position, tile)
                if placed is None:
                    placed = np.zeros((tile.h, tile.w, 4), dtype=np.float32)
                placed[..., 3:4] *= prev_tile[..., 3:4]
                mask_tile = (
                    _extract_to_tile(prep.mask, prep.position, tile)
                    if prep.mask is not None else None
                )
                self._blending.blend_region_inplace(
                    tile_canvas, placed, (0, 0),
                    prep.blend_mode, prep.opacity, mask_tile,
                )
                prev_tile = placed
                continue

            # Has clip children: restrict parent alpha
            if prep.has_clip_children:
                parent_tile = _extract_to_tile(prep.pixels, prep.position, tile)
                if parent_tile is None:
                    parent_tile = np.zeros((tile.h, tile.w, 4), dtype=np.float32)
                for cc in prep.clip_children:
                    cc_tile = _extract_to_tile(cc.pixels, cc.position, tile)
                    if cc_tile is not None:
                        parent_tile[..., 3:4] *= cc_tile[..., 3:4]
                mask_tile = (
                    _extract_to_tile(prep.mask, prep.position, tile)
                    if prep.mask is not None else None
                )
                self._blending.blend_region_inplace(
                    tile_canvas, parent_tile, (0, 0),
                    prep.blend_mode, prep.opacity, mask_tile,
                )
                # Non-clip regular children, clipped to parent
                for rc in prep.regular_children:
                    rc_tile = _extract_to_tile(rc.pixels, rc.position, tile)
                    if rc_tile is None:
                        continue
                    rc_tile[..., 3:4] *= parent_tile[..., 3:4]
                    rc_mask = (
                        _extract_to_tile(rc.mask, rc.position, tile)
                        if rc.mask is not None else None
                    )
                    self._blending.blend_region_inplace(
                        tile_canvas, rc_tile, (0, 0),
                        rc.blend_mode, rc.opacity, rc_mask,
                    )
                prev_tile = parent_tile
                continue

            # Normal layer: blend into tile
            self._blending.blend_region_inplace(
                tile_canvas, prep.pixels, rel_pos,
                prep.blend_mode, prep.opacity, prep.mask,
            )

            if prep.needs_placed:
                prev_tile = _extract_to_tile(prep.pixels, prep.position, tile)
                if prev_tile is None:
                    prev_tile = np.zeros((tile.h, tile.w, 4), dtype=np.float32)
            else:
                prev_tile = None

            # Regular children of non-group parents
            if prep.regular_children:
                if prev_tile is None:
                    prev_tile = _extract_to_tile(prep.pixels, prep.position, tile)
                    if prev_tile is None:
                        prev_tile = np.zeros((tile.h, tile.w, 4), dtype=np.float32)
                for rc in prep.regular_children:
                    rc_tile = _extract_to_tile(rc.pixels, rc.position, tile)
                    if rc_tile is None:
                        continue
                    rc_tile[..., 3:4] *= prev_tile[..., 3:4]
                    rc_mask = (
                        _extract_to_tile(rc.mask, rc.position, tile)
                        if rc.mask is not None else None
                    )
                    self._blending.blend_region_inplace(
                        tile_canvas, rc_tile, (0, 0),
                        rc.blend_mode, rc.opacity, rc_mask,
                    )

        return tile_canvas

    # ------------------------------------------------------------------
    # Group per-tile compositing (B2)
    # ------------------------------------------------------------------

    def _composite_group_tile(
        self,
        tile: TileCoord,
        group_prep: _Prepared,
        stack,
        cw: int,
        ch: int,
    ) -> np.ndarray:
        """Composite a group's children for a single tile."""
        group_tile = np.zeros((tile.h, tile.w, 4), dtype=np.float32)

        if group_prep.group_prepared:
            for child in group_prep.group_prepared:
                if not child.has_alpha:
                    continue
                ph, pw = child.pixels.shape[:2]
                if not _intersects(child.position[0], child.position[1], pw, ph,
                                   tile.x, tile.y, tile.w, tile.h):
                    continue
                rel_pos = (child.position[0] - tile.x,
                           child.position[1] - tile.y)

                if child.has_clip_children:
                    parent_tile = _extract_to_tile(
                        child.pixels, child.position, tile)
                    if parent_tile is None:
                        parent_tile = np.zeros(
                            (tile.h, tile.w, 4), dtype=np.float32)
                    for cc in child.clip_children:
                        cc_tile = _extract_to_tile(cc.pixels, cc.position, tile)
                        if cc_tile is not None:
                            parent_tile[..., 3:4] *= cc_tile[..., 3:4]
                    mask_tile = (
                        _extract_to_tile(child.mask, child.position, tile)
                        if child.mask is not None else None
                    )
                    self._blending.blend_region_inplace(
                        group_tile, parent_tile, (0, 0),
                        child.blend_mode, child.opacity, mask_tile,
                    )
                    for rc in child.regular_children:
                        rc_tile = _extract_to_tile(rc.pixels, rc.position, tile)
                        if rc_tile is None:
                            continue
                        rc_tile[..., 3:4] *= parent_tile[..., 3:4]
                        rc_mask = (
                            _extract_to_tile(rc.mask, rc.position, tile)
                            if rc.mask is not None else None
                        )
                        self._blending.blend_region_inplace(
                            group_tile, rc_tile, (0, 0),
                            rc.blend_mode, rc.opacity, rc_mask,
                        )
                else:
                    self._blending.blend_region_inplace(
                        group_tile, child.pixels, rel_pos,
                        child.blend_mode, child.opacity, child.mask,
                    )
                    if child.regular_children:
                        parent_tile = _extract_to_tile(
                            child.pixels, child.position, tile)
                        if parent_tile is None:
                            parent_tile = np.zeros(
                                (tile.h, tile.w, 4), dtype=np.float32)
                        for rc in child.regular_children:
                            rc_tile = _extract_to_tile(
                                rc.pixels, rc.position, tile)
                            if rc_tile is None:
                                continue
                            rc_tile[..., 3:4] *= parent_tile[..., 3:4]
                            rc_mask = (
                                _extract_to_tile(rc.mask, rc.position, tile)
                                if rc.mask is not None else None
                            )
                            self._blending.blend_region_inplace(
                                group_tile, rc_tile, (0, 0),
                                rc.blend_mode, rc.opacity, rc_mask,
                            )

        # Apply group-level adj/filter children
        layer = group_prep.layer
        adj_children = {}
        layers = list(stack)
        for l in layers:
            if (l.parent_id == layer.id
                    and l.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER)
                    and l.visible):
                adj_children.setdefault(layer.id, []).append(l)
        if layer.id in adj_children:
            for adj_layer in adj_children[layer.id]:
                adj = adj_layer.adjustment
                if adj is not None:
                    group_tile = adj.apply(group_tile, adj_layer.adjustment_params)
            np.clip(group_tile, 0, 1, out=group_tile)

        # Apply group styles
        if layer.styles:
            group_tile = StyleEngine.apply_styles(group_tile, layer.styles)
            np.clip(group_tile, 0, 1, out=group_tile)
        group_tile = self._apply_channels(group_tile, layer)

        # Apply group mask
        if group_prep.mask is not None:
            mask_tile = _extract_to_tile(
                group_prep.mask, group_prep.position, tile)
            if mask_tile is not None:
                group_tile[..., 3] *= mask_tile
            else:
                group_tile[..., 3] = 0.0

        return group_tile
