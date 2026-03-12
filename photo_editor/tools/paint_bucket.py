"""Paint Bucket tool — flood-fills a contiguous region with a solid colour."""

import cv2
import numpy as np

from .tool_base import Tool
from ..core.document import Document


class PaintBucketTool(Tool):
    """Fills connected pixels that match the target colour within a tolerance."""

    def __init__(self) -> None:
        super().__init__("Paint Bucket")
        self.color: np.ndarray = np.array([1.0, 0.0, 0.0, 1.0], dtype=np.float32)
        self.tolerance: int = 32  # 0–255 scale
        self.opacity: float = 1.0
        self.contiguous: bool = True

    # ------------------------------------------------------------------
    # Flood-fill
    # ------------------------------------------------------------------

    @staticmethod
    def _flood_fill_mask(pixels: np.ndarray, sx: int, sy: int,
                         tolerance: float) -> np.ndarray:
        """Return a boolean mask of connected pixels similar to the seed colour.

        Uses cv2.floodFill on a 3-channel (RGB) image for reliable results.
        """
        h, w = pixels.shape[:2]
        # Work on RGB only — cv2.floodFill is most reliable on 1- or 3-channel
        rgb = pixels[..., :3]
        rgb_u8 = np.clip(rgb * 255, 0, 255).astype(np.uint8)
        # cv2.floodFill needs a mask 2px larger than the image
        ff_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
        lo_diff = (int(tolerance),) * 3
        hi_diff = (int(tolerance),) * 3
        cv2.floodFill(rgb_u8, ff_mask, (sx, sy), 255,
                      loDiff=lo_diff, upDiff=hi_diff,
                      flags=cv2.FLOODFILL_MASK_ONLY | (255 << 8))
        # Extract the inner mask (strip the 1px border)
        mask = ff_mask[1:-1, 1:-1].astype(np.bool_)
        return mask

    @staticmethod
    def _global_tolerance_mask(pixels: np.ndarray, sx: int, sy: int,
                               tolerance: float) -> np.ndarray:
        """Return a boolean mask of ALL pixels similar to the seed colour (non-contiguous)."""
        seed_color = pixels[sy, sx, :3]
        diff = np.abs(pixels[..., :3] - seed_color).max(axis=-1)
        return diff <= (tolerance / 255.0)

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        self._rasterize_if_needed(doc)
        layer = doc.layers.active_layer
        if layer is None or layer.locked:
            return
        # Convert document coords to layer-local pixel coords
        lx, ly = layer.position
        px, py = x - lx, y - ly
        h, w = int(layer.height), int(layer.width)
        if px < 0 or px >= w or py < 0 or py >= h:
            return

        if layer.can_mutate_display_region_locally():
            working_pixels = layer.read_display_region_float(0, 0, w, h)[0]
        else:
            working_pixels = layer.pixels

        if self.contiguous:
            fill_mask = self._flood_fill_mask(working_pixels, px, py, self.tolerance)
        else:
            fill_mask = self._global_tolerance_mask(working_pixels, px, py, self.tolerance)

        ys, xs = np.nonzero(fill_mask)
        if xs.size == 0 or ys.size == 0:
            return
        min_x = int(xs.min())
        max_x = int(xs.max())
        min_y = int(ys.min())
        max_y = int(ys.max())
        self._begin_destructive_patch(doc, "Paint Bucket Fill")
        doc.capture_layer_tile_region(
            layer,
            min_x,
            min_y,
            max_x - min_x + 1,
            max_y - min_y + 1,
        )

        mask = fill_mask.astype(np.float32)
        # Clip to selection
        sel_mask = self._get_sel_mask(doc)
        if sel_mask is not None:
            mask *= sel_mask
        mask = mask[..., np.newaxis] * self.opacity
        region = working_pixels[min_y:max_y + 1, min_x:max_x + 1].copy()
        region_mask = mask[min_y:max_y + 1, min_x:max_x + 1]
        region[:] = region * (1 - region_mask) + self.color * region_mask
        np.clip(region, 0, 1, out=region)
        if layer.can_mutate_display_region_locally():
            layer.write_display_region_float(min_x, min_y, region)
        else:
            layer.pixels[min_y:max_y + 1, min_x:max_x + 1] = region
        self._commit_destructive_patch(doc)

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        pass  # No drag behaviour

    def on_release(self, doc: Document, x: int, y: int) -> None:
        pass
