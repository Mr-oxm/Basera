"""Render pipeline — orchestrates compositor (with adjustment/filter layers).

Two compositing backends:
- **TileCompositor** (default): tile-based incremental rendering with
  dirty-tile tracking and per-tile caching.  Interactive renders use this
  path for responsiveness.
- **Compositor** (legacy): full-frame single-pass.  Used as fallback and
  for the ``execute_at_scale`` preview path.

Caches the uint8 output so repeated calls without invalidation
(e.g. panel refreshes, selection overlay updates) are essentially free.
Pre-allocates the uint8 buffer to avoid repeated allocation + conversion.
"""

import numpy as np

from ..core.document import Document
from .cache.image_pool import ImagePool
from .compositor import Compositor
from .tile_cache import TileCache
from .tile_compositor import TileCompositor

try:
    import cv2 as _cv2
except ImportError:  # pragma: no cover
    _cv2 = None


class RenderPipeline:
    """Full pipeline: layer compositing -> adjustment layers -> output."""

    def __init__(self, use_tiled: bool = True) -> None:
        self._pool = ImagePool(max_buffers_per_shape=4)
        self._compositor = Compositor(image_pool=self._pool)
        self._tile_compositor = TileCompositor(image_pool=self._pool)
        self._tile_cache = TileCache(tile_size=256)
        self._use_tiled = use_tiled
        self._last_width = 0
        self._last_height = 0
        # Cached final uint8 result
        self._result_uint8: np.ndarray | None = None
        self._uint8_valid: bool = False
        # Pre-allocated uint8 conversion buffer
        self._uint8_buf: np.ndarray | None = None

    def execute(
        self,
        document: Document,
        snapshot: object | None = None,
        cancel_token: object | None = None,
    ) -> np.ndarray:
        """Composite the document and return float32 RGBA.

        When *snapshot* is provided (a ``RenderSnapshot``), the compositor
        uses its immutable layer list instead of the live document, making
        this safe to call from a background thread.
        """
        w, h = document.width, document.height
        if snapshot is not None:
            w, h = snapshot.width, snapshot.height
        if w != self._last_width or h != self._last_height:
            self._tile_cache.initialize(w, h)
            self._tile_compositor.invalidate_all()
            self._last_width, self._last_height = w, h

        if self._use_tiled:
            if snapshot is not None:
                return self._tile_compositor.composite_snapshot(snapshot)
            return self._tile_compositor.composite(
                document.layers, w, h, cancel_token=cancel_token,
            )

        if snapshot is not None:
            return self._compositor.composite_snapshot(snapshot)
        return self._compositor.composite(document.layers, w, h)

    def invalidate_region(self, x: int, y: int, width: int, height: int) -> None:
        """Mark tiles overlapping (x, y, width, height) as dirty."""
        self._tile_cache.invalidate_region(x, y, width, height)
        self._tile_compositor.invalidate_region(x, y, width, height)
        self._uint8_valid = False

    def execute_to_uint8(self, document: Document) -> np.ndarray:
        """Return the composited image as uint8 RGBA.

        Returns a cached copy when nothing has been invalidated since
        the last call, avoiding both the composite and the float->uint8
        conversion.
        """
        if self._uint8_valid and self._result_uint8 is not None:
            return self._result_uint8
        result = self.execute(document)
        # Fast float32→uint8 using pre-allocated buffer
        shape = result.shape
        if self._uint8_buf is None or self._uint8_buf.shape != shape:
            self._uint8_buf = np.empty(shape, dtype=np.uint8)
        # render() already clips to [0,1], so this is safe
        np.multiply(result, 255, out=self._uint8_buf, casting="unsafe")
        self._result_uint8 = self._uint8_buf
        self._uint8_valid = True
        return self._result_uint8

    def execute_at_scale(
        self, document: Document, scale: float, snapshot: object | None = None,
    ) -> np.ndarray:
        """Composite at reduced resolution for interactive preview.

        Scales layer pixel data *before* compositing so all blend,
        adjustment, and filter passes run at the smaller resolution.
        The result is then upscaled to the original document dimensions
        so the caller always receives a document-sized buffer.
        """
        if scale >= 1.0:
            return self.execute(document, snapshot=snapshot)

        from .renderer.render_snapshot import (
            RenderSnapshot, LayerSnapshot, create_render_snapshot,
        )

        src = snapshot
        if src is None:
            src = create_render_snapshot(document)

        full_w, full_h = src.width, src.height
        preview_w = max(1, int(full_w * scale))
        preview_h = max(1, int(full_h * scale))

        # Build scaled layer snapshots
        scaled_layers: list[LayerSnapshot] = []
        scaled_map: dict[str, LayerSnapshot] = {}
        for snap in src.layers:
            scaled_pix = snap.pixels
            scaled_mask = snap.mask
            scaled_pos = snap.position
            scaled_w = snap.width
            scaled_h = snap.height

            if snap.pixels.size > 0 and _cv2 is not None:
                sh, sw = snap.pixels.shape[:2]
                new_sw = max(1, int(sw * scale))
                new_sh = max(1, int(sh * scale))
                if new_sw != sw or new_sh != sh:
                    scaled_pix = _cv2.resize(
                        snap.pixels, (new_sw, new_sh),
                        interpolation=_cv2.INTER_AREA,
                    )
                    scaled_w = new_sw
                    scaled_h = new_sh
                    if snap.mask is not None:
                        scaled_mask = _cv2.resize(
                            snap.mask, (new_sw, new_sh),
                            interpolation=_cv2.INTER_AREA,
                        )
            scaled_pos = (
                int(snap.position[0] * scale),
                int(snap.position[1] * scale),
            )
            new_snap = LayerSnapshot(
                id=snap.id, name=snap.name,
                width=scaled_w, height=scaled_h,
                layer_type=snap.layer_type,
                opacity=snap.opacity, blend_mode=snap.blend_mode,
                visible=snap.visible, position=scaled_pos,
                clipping_mask=snap.clipping_mask,
                clips_parent=snap.clips_parent,
                parent_id=snap.parent_id,
                mask_enabled=snap.mask_enabled,
                mask_layers=snap.mask_layers,
                children=snap.children,
                ex_parent_id=snap.ex_parent_id,
                channel_r=snap.channel_r, channel_g=snap.channel_g,
                channel_b=snap.channel_b, channel_a=snap.channel_a,
                has_alpha=snap.has_alpha,
                pixels=scaled_pix, mask=scaled_mask,
                styles=snap.styles,
                adjustment=snap.adjustment,
                adjustment_params=snap.adjustment_params,
            )
            scaled_layers.append(new_snap)
            scaled_map[new_snap.id] = new_snap

        preview_snap = RenderSnapshot(
            width=preview_w, height=preview_h,
            generation=src.generation,
            layers=tuple(scaled_layers),
            layer_map=scaled_map,
        )
        if self._use_tiled:
            result = self._tile_compositor.composite_snapshot(preview_snap)
        else:
            result = self._compositor.composite_snapshot(preview_snap)

        # Upscale back to document dimensions
        if _cv2 is not None and (result.shape[1] != full_w or result.shape[0] != full_h):
            result = _cv2.resize(
                result, (full_w, full_h),
                interpolation=_cv2.INTER_LINEAR,
            )
        return result

    def invalidate(self, layer_id: str | None = None) -> None:
        self._uint8_valid = False
        self._tile_cache.invalidate_all()
        self._tile_compositor.invalidate_all()

    def invalidate_topology(self) -> None:
        """Force full invalidation on structural changes."""
        self._compositor.invalidate_topology()
        self._uint8_valid = False
        self._tile_cache.invalidate_all()
        self._tile_compositor.invalidate_all()
