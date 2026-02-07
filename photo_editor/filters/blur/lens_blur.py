"""Lens (Bokeh) Blur filter."""

import cv2
import numpy as np

from ..filter_base import Filter


class LensBlur(Filter):
    """Simulate an out-of-focus lens blur with a polygonal bokeh shape.

    Parameters
    ----------
    radius : int
        Blur radius in pixels, range [1, 50].
    blade_count : int
        Number of aperture blades (3-8). More blades approach a circle.
    """

    def __init__(self) -> None:
        super().__init__("Lens Blur", {"radius": 5, "blade_count": 6})

    # ------------------------------------------------------------------
    @staticmethod
    def _create_bokeh_kernel(radius: int, blade_count: int) -> np.ndarray:
        """Return a normalised polygon-shaped kernel."""
        size = 2 * radius + 1
        kernel = np.zeros((size, size), dtype=np.float32)
        center = (radius, radius)

        # Generate polygon vertices
        angles = np.linspace(0, 2 * np.pi, blade_count, endpoint=False)
        pts = np.array(
            [
                [
                    int(round(center[0] + radius * np.cos(a))),
                    int(round(center[1] + radius * np.sin(a))),
                ]
                for a in angles
            ],
            dtype=np.int32,
        )

        cv2.fillConvexPoly(kernel, pts, 1.0)

        total = kernel.sum()
        if total > 0:
            kernel /= total
        return kernel

    # ------------------------------------------------------------------
    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).astype(np.float32)
        alpha = self._alpha(image)

        radius = int(params.get("radius", self.default_params["radius"]))
        blade_count = int(params.get("blade_count", self.default_params["blade_count"]))
        radius = max(1, min(radius, 50))
        blade_count = max(3, min(blade_count, 8))

        kernel = self._create_bokeh_kernel(radius, blade_count)

        # Apply the kernel per-channel.
        blurred = cv2.filter2D(rgb, -1, kernel)

        return self._merge(blurred, alpha)
