"""Oil Paint filter."""

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

        h, w, c = rgb_u8.shape
        result = np.zeros_like(rgb_u8)

        # Quantise intensities.
        intensity = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2GRAY)
        quantised = (intensity.astype(np.float32) / 255.0 * levels).astype(np.int32)

        # For each pixel, find the most-frequent intensity bin in its
        # neighbourhood and take the average colour of those pixels.
        pad = radius
        padded_rgb = cv2.copyMakeBorder(rgb_u8, pad, pad, pad, pad, cv2.BORDER_REFLECT_101)
        padded_q = cv2.copyMakeBorder(quantised, pad, pad, pad, pad, cv2.BORDER_REFLECT_101)

        for y in range(h):
            for x in range(w):
                region_q = padded_q[y:y + 2 * pad + 1, x:x + 2 * pad + 1]
                region_rgb = padded_rgb[y:y + 2 * pad + 1, x:x + 2 * pad + 1]

                # Find the most common bin.
                bins = np.bincount(region_q.ravel(), minlength=levels + 1)
                dominant = int(np.argmax(bins))

                mask = region_q == dominant
                count = mask.sum()
                if count > 0:
                    avg_colour = region_rgb[mask].mean(axis=0).astype(np.uint8)
                else:
                    avg_colour = rgb_u8[y, x]

                result[y, x] = avg_colour

        result_f = result.astype(np.float32) / 255.0
        return self._merge(result_f, alpha)
