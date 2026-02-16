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
    preserve_alpha : bool
        If True the original alpha channel is kept unchanged.
    """

    def __init__(self) -> None:
        super().__init__(
            "Lens Blur",
            {"radius": 5, "blade_count": 6, "preserve_alpha": False},
        )

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
        radius = int(params.get("radius", self.default_params["radius"]))
        blade_count = int(params.get("blade_count", self.default_params["blade_count"]))
        radius = max(1, min(radius, 50))
        blade_count = max(3, min(blade_count, 8))
        preserve = bool(params.get("preserve_alpha",
                                   self.default_params["preserve_alpha"]))

        kernel = self._create_bokeh_kernel(radius, blade_count)

        # Work in premultiplied-alpha space to avoid dark fringe
        pm, orig_alpha = self._premultiply(image)
        blurred = cv2.filter2D(pm, -1, kernel)

        return self._unpremultiply(blurred, orig_alpha, preserve)
