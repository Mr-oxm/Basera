"""Layer data model — the atomic unit of the compositing stack.

Non-destructive transforms (Affinity-style)
--------------------------------------------
Raster layers store the *original* source pixel data alongside current
transform parameters (scale, rotation).  Display pixels are always
re-derived from the source, so no matter how many times you resize or
rotate, the full-resolution original is preserved.

Destructive tools (brush, eraser, etc.) automatically *rasterize* the
transform before modifying pixels, baking the current transform into
the source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeAlias
from uuid import uuid4

import numpy as np

from .enums import BlendMode, LayerType
from .uint8_tile_store import Uint8TileStore

if TYPE_CHECKING:
    from ..processors import ImageProcessor

    LayerProcessor: TypeAlias = ImageProcessor
else:
    LayerProcessor = object


@dataclass
class Layer:
    """Single compositing layer with optional mask and styles."""

    name: str
    width: int
    height: int
    layer_type: LayerType = LayerType.RASTER
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    opacity: float = 1.0
    blend_mode: BlendMode = BlendMode.NORMAL
    visible: bool = True
    locked: bool = False
    position: tuple[int, int] = (0, 0)
    mask_enabled: bool = True
    clipping_mask: bool = False
    clips_parent: bool = False
    parent_id: str | None = None
    # Channel visibility toggles
    channel_r: bool = True
    channel_g: bool = True
    channel_b: bool = True
    channel_a: bool = True
    # Persistent transform tracking
    transform_angle: float = 0.0
    transform_scale_x: float = 1.0
    transform_scale_y: float = 1.0
    transform_base_w: int = 0
    transform_base_h: int = 0

    def __post_init__(self) -> None:
        self._pixels = np.zeros((self.height, self.width, 4), dtype=np.float32)
        self._pixels_u8: np.ndarray | None = None
        self._pixels_tile_store: Uint8TileStore | None = None
        self._mask: np.ndarray | None = None
        self._styles: list = []
        self._adjustment: LayerProcessor | None = None
        self._adjustment_params: dict = {}
        self.children: list[str] = []
        # Mask layer children — IDs of MASK-type layers attached to this layer
        self.mask_layers: list[str] = []
        # Ex-parent tracking: when a mask layer is detached from its parent,
        # this records the old parent so compositing can scope the mask
        # to only that layer (instead of affecting all layers below).
        self.ex_parent_id: str | None = None
        # --- Non-destructive transform state ---
        # Original full-quality pixel data (None = no ND transform active)
        self._source_pixels: np.ndarray | None = None
        self._source_mask: np.ndarray | None = None
        self._pixels_dirty: bool = False
        # --- Vector layer data ---
        # When layer_type == SHAPE, this holds the VectorLayer scene graph.
        # The rasterizer converts vector data → _pixels on demand.
        self._vector_data: object | None = None  # VectorLayer instance
        self._transform_cache: dict[tuple, tuple[np.ndarray | None, Uint8TileStore | None, np.ndarray | None, int, int]] = {}
        self._source_revision: int = 0

    @staticmethod
    def _float_to_u8(value: np.ndarray) -> np.ndarray:
        clipped = np.nan_to_num(np.clip(value, 0.0, 1.0), nan=0.0, posinf=1.0, neginf=0.0)
        return np.rint(clipped * 255.0).astype(np.uint8)

    @staticmethod
    def _u8_to_float(value: np.ndarray) -> np.ndarray:
        if value.dtype == np.float32:
            return value.copy()
        return value.astype(np.float32) / 255.0

    def _clear_fast_transform_cache(self) -> None:
        self._transform_cache.clear()

    def _make_fast_transform_cache_key(
        self,
        scale_x: float,
        scale_y: float,
        angle: float,
        fast: bool,
    ) -> tuple[int, bool, int, int, float, float, float]:
        return (
            self._source_revision,
            bool(fast),
            max(1, int(round(self.source_width * float(scale_x)))),
            max(1, int(round(self.source_height * float(scale_y)))),
            round(float(scale_x), 3 if fast else 5),
            round(float(scale_y), 3 if fast else 5),
            round(float(angle), 1 if fast else 4),
        )

    def _copy_display_u8(self) -> np.ndarray:
        if self._pixels_tile_store is not None:
            return self._pixels_tile_store.to_array()
        if self._pixels_u8 is not None:
            return self._pixels_u8.copy()
        return self._float_to_u8(self._pixels)

    def copy_display_u8(self) -> np.ndarray:
        return self._copy_display_u8()

    def _store_display_u8(self, rgba_u8: np.ndarray) -> None:
        self.height, self.width = rgba_u8.shape[:2]
        if max(self.width, self.height) > 256:
            self._pixels_tile_store = Uint8TileStore.from_array(rgba_u8)
            self._pixels_u8 = None
        else:
            self._pixels_u8 = rgba_u8.copy()
            self._pixels_tile_store = None
        self._pixels = None

    def _store_display_float_compacted(self, value: np.ndarray) -> None:
        self._store_display_u8(self._float_to_u8(value))

    def _restore_transform_cache_entry(
        self,
        entry: tuple[np.ndarray | None, Uint8TileStore | None, np.ndarray | None, int, int],
    ) -> None:
        pixels_u8, tile_store, mask_u8, width, height = entry
        self.width = width
        self.height = height
        self._pixels = None
        self._pixels_u8 = pixels_u8.copy() if pixels_u8 is not None else None
        self._pixels_tile_store = tile_store.copy() if tile_store is not None else None
        self._mask = None if mask_u8 is None else (mask_u8.astype(np.float32) / 255.0)
        self._pixels_dirty = False

    def _cache_current_transform_result(self, cache_key: tuple, mask_result: np.ndarray | None) -> None:
        mask_u8 = None
        if mask_result is not None:
            mask_u8 = np.rint(np.clip(mask_result, 0.0, 1.0) * 255.0).astype(np.uint8)
        self._transform_cache[cache_key] = (
            self._pixels_u8.copy() if self._pixels_u8 is not None else None,
            self._pixels_tile_store.copy() if self._pixels_tile_store is not None else None,
            mask_u8,
            int(self.width),
            int(self.height),
        )

    # ---- Pixel data ---------------------------------------------------------

    @property
    def pixels(self) -> np.ndarray:
        if self._pixels_dirty:
            self._recompute_from_source()
        if self._pixels is None and self._pixels_tile_store is not None:
            self._pixels = self._u8_to_float(self._pixels_tile_store.to_array())
        if self._pixels is None and self._pixels_u8 is not None:
            self._pixels = self._u8_to_float(self._pixels_u8)
        return self._pixels

    @pixels.setter
    def pixels(self, value: np.ndarray) -> None:
        self._pixels = value.astype(np.float32) if value.dtype != np.float32 else value
        self._pixels_u8 = None
        self._pixels_tile_store = None
        self.height, self.width = value.shape[:2]
        self._clear_fast_transform_cache()

    def ensure_pixels_float(self) -> np.ndarray:
        return self.pixels

    def can_decode_display_roi(self) -> bool:
        return self._pixels is None and (
            self._pixels_u8 is not None or self._pixels_tile_store is not None
        )

    def can_mutate_display_region_locally(self) -> bool:
        return self._pixels is None and not self._pixels_dirty and (
            self._pixels_u8 is not None or self._pixels_tile_store is not None
        )

    def read_display_pixel_float(self, x: int, y: int) -> np.ndarray | None:
        px = int(x)
        py = int(y)
        if px < 0 or py < 0 or px >= int(self.width) or py >= int(self.height):
            return None
        if self._pixels is not None:
            return self._pixels[py, px].copy()
        if self._pixels_tile_store is not None:
            return self._u8_to_float(self._pixels_tile_store.decode_roi(px, py, 1, 1))[0, 0]
        if self._pixels_u8 is not None:
            return self._u8_to_float(self._pixels_u8[py:py + 1, px:px + 1])[0, 0]
        return None

    def decode_display_roi(
        self,
        origin_x: int,
        origin_y: int,
        canvas_w: int,
        canvas_h: int,
        position: tuple[int, int] | None = None,
    ) -> tuple[np.ndarray, tuple[int, int]] | None:
        if self._pixels_tile_store is None and self._pixels_u8 is None:
            return None
        pos_x, pos_y = position if position is not None else self.position
        if self._pixels_tile_store is not None:
            src_w = self._pixels_tile_store.width
            src_h = self._pixels_tile_store.height
        else:
            src_h, src_w = self._pixels_u8.shape[:2]
        sx = max(0, origin_x - pos_x)
        sy = max(0, origin_y - pos_y)
        dx = max(0, pos_x - origin_x)
        dy = max(0, pos_y - origin_y)
        width = min(src_w - sx, canvas_w - dx)
        height = min(src_h - sy, canvas_h - dy)
        if width <= 0 or height <= 0:
            return None
        if self._pixels_tile_store is not None:
            roi_u8 = self._pixels_tile_store.decode_roi(sx, sy, width, height)
        else:
            roi_u8 = self._pixels_u8[sy:sy + height, sx:sx + width]
        return self._u8_to_float(roi_u8), (pos_x + sx, pos_y + sy)

    def decode_display_roi_padded(
        self,
        origin_x: int,
        origin_y: int,
        canvas_w: int,
        canvas_h: int,
        position: tuple[int, int] | None = None,
    ) -> tuple[np.ndarray, tuple[int, int]] | None:
        if canvas_w <= 0 or canvas_h <= 0:
            return None
        pos_x, pos_y = position if position is not None else self.position
        overlap = self.decode_display_roi(origin_x, origin_y, canvas_w, canvas_h, position=position)
        padded = np.zeros((canvas_h, canvas_w, 4), dtype=np.float32)
        if overlap is None:
            return padded, (origin_x, origin_y)
        roi, (roi_x, roi_y) = overlap
        dx = max(0, roi_x - origin_x)
        dy = max(0, roi_y - origin_y)
        h, w = roi.shape[:2]
        padded[dy:dy + h, dx:dx + w] = roi
        return padded, (origin_x, origin_y)

    def compact_display_storage(self) -> bool:
        if self._pixels_dirty or self._pixels is None:
            return False
        self._store_display_u8(self._float_to_u8(self._pixels))
        return True

    def read_display_region_float(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> tuple[np.ndarray, tuple[int, int]] | None:
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(int(self.width), x0 + int(width))
        y1 = min(int(self.height), y0 + int(height))
        if x1 <= x0 or y1 <= y0:
            return None
        if self._pixels is not None:
            return self._pixels[y0:y1, x0:x1].copy(), (x0, y0)
        decoded = self.decode_display_roi(
            self.position[0] + x0,
            self.position[1] + y0,
            x1 - x0,
            y1 - y0,
        )
        if decoded is None:
            return np.zeros((y1 - y0, x1 - x0, 4), dtype=np.float32), (x0, y0)
        region, _position = decoded
        return region, (x0, y0)

    def write_display_region_float(self, x: int, y: int, region: np.ndarray) -> None:
        height, width = region.shape[:2]
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(int(self.width), x0 + int(width))
        y1 = min(int(self.height), y0 + int(height))
        if x1 <= x0 or y1 <= y0:
            return
        sx0 = x0 - int(x)
        sy0 = y0 - int(y)
        cropped = region[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)]
        if self._pixels is not None:
            self._pixels[y0:y1, x0:x1] = cropped
            return
        cropped_u8 = self._float_to_u8(cropped)
        if self._pixels_tile_store is not None:
            self._pixels_tile_store.write_roi(x0, y0, cropped_u8)
            return
        if self._pixels_u8 is not None:
            self._pixels_u8[y0:y1, x0:x1] = cropped_u8

    # ---- Non-destructive transform API --------------------------------------

    @property
    def source_pixels(self) -> np.ndarray:
        """Original untransformed pixel data, or current pixels if no ND transform."""
        if self._source_pixels is not None:
            return self._u8_to_float(self._source_pixels)
        return self.pixels

    @property
    def source_mask(self) -> np.ndarray | None:
        if self._source_mask is None:
            return None
        if self._source_mask.dtype == np.float32:
            return self._source_mask.copy()
        return self._source_mask.astype(np.float32) / 255.0

    @property
    def source_width(self) -> int:
        """Width of the original source data."""
        if self._source_pixels is not None:
            return self._source_pixels.shape[1]
        return self.width

    @property
    def source_height(self) -> int:
        """Height of the original source data."""
        if self._source_pixels is not None:
            return self._source_pixels.shape[0]
        return self.height

    @property
    def has_transform(self) -> bool:
        """True when a non-destructive transform is active."""
        return self._source_pixels is not None and (
            self.transform_scale_x != 1.0
            or self.transform_scale_y != 1.0
            or self.transform_angle != 0.0
        )

    def init_non_destructive(self) -> None:
        """Snapshot current pixels as source for non-destructive transforms.

        Idempotent — only captures on first call.  Subsequent transforms
        keep reusing the same high-quality source.
        """
        if self._source_pixels is None:
            self._source_pixels = self._copy_display_u8()
            if self._mask is not None:
                self._source_mask = np.rint(np.clip(self._mask, 0.0, 1.0) * 255.0).astype(np.uint8)
            # Ensure base dimensions are initialised
            if self.transform_base_w == 0:
                self.transform_base_w = self.width
                self.transform_base_h = self.height
            self._source_revision += 1
            self._clear_fast_transform_cache()

    def compute_display(
        self,
        scale_x: float | None = None,
        scale_y: float | None = None,
        angle: float | None = None,
        fast: bool = False,
    ) -> None:
        """Eagerly recompute display pixels from source + transform params.

        Pass explicit values to override stored params (useful during a
        drag where the param hasn't been committed yet).  ``None`` means
        "use the stored value".
        """
        if self._source_pixels is None:
            return

        from ..transforms.transform_engine import TransformEngine
        import cv2

        sx = scale_x if scale_x is not None else self.transform_scale_x
        sy = scale_y if scale_y is not None else self.transform_scale_y
        ang = angle if angle is not None else self.transform_angle

        cache_key = self._make_fast_transform_cache_key(sx, sy, ang, fast)
        cache_entry = self._transform_cache.get(cache_key)
        if cache_entry is not None:
            self._restore_transform_cache_entry(cache_entry)
            return

        result = self.source_pixels
        mask_result = self.source_mask

        if sx != 1.0 or sy != 1.0:
            result = TransformEngine.scale(result, sx, sy, fast=fast)
            if mask_result is not None:
                sh, sw = result.shape[:2]
                mask_interp = cv2.INTER_NEAREST if fast else cv2.INTER_LINEAR
                mask_result = cv2.resize(
                    mask_result, (sw, sh), interpolation=mask_interp
                )

        # Update unrotated display dimensions
        self.transform_base_w = result.shape[1]
        self.transform_base_h = result.shape[0]

        if ang != 0.0:
            result = TransformEngine.rotate(result, ang, expand=True, fast=fast)
            if mask_result is not None:
                mask_3d = np.stack([mask_result] * 4, axis=-1)
                mask_3d = TransformEngine.rotate(mask_3d, ang, expand=True, fast=fast)
                mask_result = mask_3d[..., 0]

        clipped = np.clip(result, 0.0, 1.0).astype(np.float32) if result.dtype != np.float32 else np.clip(result, 0.0, 1.0)
        self._store_display_float_compacted(clipped)
        if mask_result is not None:
            self._mask = np.clip(mask_result, 0.0, 1.0)
        else:
            self._mask = None
        self.height, self.width = result.shape[:2]
        self._cache_current_transform_result(cache_key, mask_result)
        self._pixels_dirty = False

    def invalidate_transform(self) -> None:
        """Mark display pixels as needing lazy recompute from source."""
        if self._source_pixels is not None:
            self._pixels_dirty = True

    def rasterize_transform(self) -> None:
        """Bake current transforms into pixels, discarding the source.

        Called automatically before destructive operations (painting)
        and explicitly via *Layer > Rasterize*.
        """
        if self._source_pixels is not None:
            if self._pixels_dirty:
                self._recompute_from_source()
            # Current _pixels/mask are the baked result — adopt them
            self._source_pixels = None
            self._source_mask = None
        self.transform_scale_x = 1.0
        self.transform_scale_y = 1.0
        self.transform_angle = 0.0
        self.transform_base_w = 0
        self.transform_base_h = 0
        self._pixels_dirty = False
        self._clear_fast_transform_cache()
        self._source_revision += 1

    def _recompute_from_source(self) -> None:
        """Internal lazy recompute triggered by the ``pixels`` getter."""
        if self._source_pixels is None:
            self._pixels_dirty = False
            return
        # Delegate to compute_display with stored params
        self.compute_display()

    # ---- Mask ---------------------------------------------------------------

    @property
    def mask(self) -> np.ndarray | None:
        return self._mask

    @mask.setter
    def mask(self, value: np.ndarray | None) -> None:
        self._mask = value
        self._clear_fast_transform_cache()

    def add_mask(self, fill_white: bool = True) -> None:
        val = 1.0 if fill_white else 0.0
        self._mask = np.full((self.height, self.width), val, dtype=np.float32)
        self._clear_fast_transform_cache()

    def remove_mask(self) -> None:
        self._mask = None
        self._clear_fast_transform_cache()

    # ---- Styles / Adjustments ----------------------------------------------

    @property
    def styles(self) -> list:
        return self._styles

    @property
    def adjustment(self) -> LayerProcessor | None:
        return self._adjustment

    @adjustment.setter
    def adjustment(self, value: LayerProcessor | None) -> None:
        self._adjustment = value

    @property
    def adjustment_params(self) -> dict:
        return self._adjustment_params

    @adjustment_params.setter
    def adjustment_params(self, value: dict) -> None:
        self._adjustment_params = value

    # ---- Utilities ----------------------------------------------------------

    @property
    def is_mask_layer(self) -> bool:
        """True when this layer acts as a mask (MASK type)."""
        return self.layer_type == LayerType.MASK

    def get_mask_grayscale(self) -> np.ndarray:
        """Return the grayscale mask data from this layer's pixels.

        For MASK layers the luminance of the RGB channels is used:
        white = fully visible, black = fully hidden.
        """
        # Use luminance: 0.299R + 0.587G + 0.114B
        pixels = self.pixels
        return (
            pixels[..., 0] * 0.299
            + pixels[..., 1] * 0.587
            + pixels[..., 2] * 0.114
        ).astype(np.float32)

    def duplicate(self) -> "Layer":
        new = Layer(
            name=f"{self.name} copy",
            width=self.width,
            height=self.height,
            layer_type=self.layer_type,
            opacity=self.opacity,
            blend_mode=self.blend_mode,
            visible=self.visible,
            position=self.position,
            transform_angle=self.transform_angle,
            transform_scale_x=self.transform_scale_x,
            transform_scale_y=self.transform_scale_y,
            transform_base_w=self.transform_base_w,
            transform_base_h=self.transform_base_h,
            channel_r=self.channel_r,
            channel_g=self.channel_g,
            channel_b=self.channel_b,
            channel_a=self.channel_a,
        )
        new.pixels = self.pixels.copy()
        if self._pixels_u8 is not None:
            new._pixels_u8 = self._pixels_u8.copy()
            if self._pixels is None:
                new._pixels = None
        if self._pixels_tile_store is not None:
            new._pixels_tile_store = self._pixels_tile_store.copy()
            if self._pixels is None:
                new._pixels = None
        if self._mask is not None:
            new._mask = self._mask.copy()
        new._styles = list(self._styles)
        new.mask_layers = list(self.mask_layers)
        new.ex_parent_id = self.ex_parent_id
        # Copy non-destructive source data
        if self._source_pixels is not None:
            new._source_pixels = self._source_pixels.copy()
        if self._source_mask is not None:
            new._source_mask = self._source_mask.copy()
        new._source_revision = self._source_revision
        # Copy adjustment layer data
        if self._adjustment is not None:
            new._adjustment = self._adjustment
            new._adjustment_params = dict(self._adjustment_params)
        # Copy vector layer data
        if self._vector_data is not None:
            new._vector_data = self._vector_data  # VectorLayer is serializable
        return new

    def fill(self, color: np.ndarray) -> None:
        self.ensure_pixels_float()[:] = color.astype(np.float32)
        self._clear_fast_transform_cache()
