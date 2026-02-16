"""Motion Blur filter."""

import cv2
import numpy as np

from ..filter_base import Filter


class MotionBlur(Filter):
    """Simulate motion blur along a given angle.

    Parameters
    ----------
    distance : int
        Blur distance in pixels, range [1, 200].
    angle : float
        Angle of motion in degrees, range [0, 360].
    preserve_alpha : bool
        If True the original alpha channel is kept unchanged.
    """

    def __init__(self) -> None:
        super().__init__(
            "Motion Blur",
            {"distance": 10, "angle": 0.0, "preserve_alpha": False},
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _build_motion_kernel(distance: int, angle: float) -> np.ndarray:
        """Create a 1-D motion-blur kernel rotated to *angle*."""
        distance = max(1, distance)
        kernel_size = distance
        kernel = np.zeros((kernel_size, kernel_size), dtype=np.float32)

        # Draw a line through the centre of the kernel.
        center = (kernel_size - 1) / 2.0
        cos_a = np.cos(np.radians(angle))
        sin_a = np.sin(np.radians(angle))

        for i in range(kernel_size):
            t = i - center
            x = int(round(center + t * cos_a))
            y = int(round(center + t * sin_a))
            if 0 <= x < kernel_size and 0 <= y < kernel_size:
                kernel[y, x] = 1.0

        # Normalise so the kernel sums to 1.
        total = kernel.sum()
        if total > 0:
            kernel /= total
        return kernel

    # ------------------------------------------------------------------
    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        distance = int(params.get("distance", self.default_params["distance"]))
        angle = float(params.get("angle", self.default_params["angle"]))
        distance = max(1, min(distance, 200))
        angle = angle % 360.0
        preserve = bool(params.get("preserve_alpha",
                                   self.default_params["preserve_alpha"]))

        kernel = self._build_motion_kernel(distance, angle)

        # Work in premultiplied-alpha space to avoid dark fringe
        pm, orig_alpha = self._premultiply(image)
        blurred = cv2.filter2D(pm, -1, kernel)

        return self._unpremultiply(blurred, orig_alpha, preserve)
