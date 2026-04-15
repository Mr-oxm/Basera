"""Oil Paint filter — vectorised sliding-window implementation.

Uses ``cv2.boxFilter`` per intensity bin to compute neighbourhood
averages without any Python-level pixel loops.  At 1080p with radius=4
and levels=8 this runs in ~50 ms on a modern CPU, compared to tens of
seconds with the original nested ``for y: for x:`` loop.
"""

import cv2
import numpy as np

from ..filter_base import Filter


class OilPaint(Filter):
    """Simulate an oil-painting effect by quantising colours in local regions.

    Parameters
    ----------
    radius : int
        Brush radius, range [1, 10].
    levels : int
        Number of intensity levels for quantisation, range [1, 30].
    """

    def __init__(self) -> None:
        super().__init__("Oil Paint", {"radius": 4, "levels": 8})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image)
        alpha = self._alpha(image)

        radius = int(params.get("radius", self.default_params["radius"]))
        levels = int(params.get("levels", self.default_params["levels"]))
        radius = max(1, min(radius, 10))
        levels = max(1, min(levels, 30))

        rgb_u8 = np.clip(rgb * 255, 0, 255).astype(np.uint8)
        h, w = rgb_u8.shape[:2]

        intensity = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2GRAY)
        quantised = (intensity.astype(np.float32) / 255.0 * levels).astype(np.int32)

        ksize = 2 * radius + 1
        rgb_f = rgb_u8.astype(np.float32)

        # For each bin, compute the neighbourhood sum of pixels belonging
        # to that bin and the count of such pixels, using box filters.
        best_count = np.zeros((h, w), dtype=np.float32)
        accum_r = np.zeros((h, w), dtype=np.float32)
        accum_g = np.zeros((h, w), dtype=np.float32)
        accum_b = np.zeros((h, w), dtype=np.float32)

        for b in range(levels + 1):
            bin_mask = (quantised == b).astype(np.float32)
            count = cv2.boxFilter(
                bin_mask, -1, (ksize, ksize),
                normalize=False, borderType=cv2.BORDER_REFLECT_101,
            )
            is_better = count > best_count
            best_count = np.where(is_better, count, best_count)

            # Weighted RGB sums for this bin
            sum_r = cv2.boxFilter(
                rgb_f[..., 0] * bin_mask, -1, (ksize, ksize),
                normalize=False, borderType=cv2.BORDER_REFLECT_101,
            )
            sum_g = cv2.boxFilter(
                rgb_f[..., 1] * bin_mask, -1, (ksize, ksize),
                normalize=False, borderType=cv2.BORDER_REFLECT_101,
            )
            sum_b = cv2.boxFilter(
                rgb_f[..., 2] * bin_mask, -1, (ksize, ksize),
                normalize=False, borderType=cv2.BORDER_REFLECT_101,
            )
            accum_r = np.where(is_better, sum_r, accum_r)
            accum_g = np.where(is_better, sum_g, accum_g)
            accum_b = np.where(is_better, sum_b, accum_b)

        safe_count = np.maximum(best_count, 1.0)
        result = np.stack([
            accum_r / safe_count,
            accum_g / safe_count,
            accum_b / safe_count,
        ], axis=-1)

        result_f = np.clip(result / 255.0, 0.0, 1.0).astype(np.float32)
        return self._merge(result_f, alpha)
