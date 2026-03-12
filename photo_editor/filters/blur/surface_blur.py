"""Surface Blur filter (edge-preserving blur)."""

import cv2
import numpy as np

from ..filter_base import Filter


class SurfaceBlur(Filter):
    """Edge-preserving blur similar to Photoshop's Surface Blur.

    Uses bilateral filtering under the hood.

    Parameters
    ----------
    radius : int
        Spatial extent of the blur, range [1, 100].
    threshold : int
        Colour-difference threshold, range [1, 255].
        Pixels with colour differences above this are not blurred together.
    preserve_alpha : bool
        If True the original alpha channel is kept unchanged.
    """

    def __init__(self) -> None:
        super().__init__(
            "Surface Blur",
            {"radius": 5, "threshold": 15, "preserve_alpha": False},
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        radius = int(params.get("radius", self.default_params["radius"]))
        threshold = int(params.get("threshold", self.default_params["threshold"]))
        radius = max(1, min(radius, 100))
        threshold = max(1, min(threshold, 255))
        preserve = bool(params.get("preserve_alpha",
                                   self.default_params["preserve_alpha"]))

        # Premultiply to avoid dark fringe
        pm, orig_alpha = self._premultiply(image)

        # Convert to 0-255 for bilateral filter, which works best in uint8.
        pm_u8 = np.clip(pm * 255, 0, 255).astype(np.uint8)

        # Diameter: OpenCV bilateral uses d = 2*radius + 1 when d > 0.
        d = 2 * radius + 1
        if d > 300:
            d = -1  # let OpenCV choose based on sigma

        sigma_color = float(threshold)
        sigma_space = float(radius)

        # bilateralFilter only handles 1- or 3-channel; split RGBA
        blurred_rgb = cv2.bilateralFilter(pm_u8[..., :3], d, sigma_color, sigma_space)
        # Blur the alpha with a plain Gaussian to keep it smooth
        ksize = int(np.ceil(radius * 3)) | 1
        ksize = max(3, ksize)
        blurred_a = cv2.GaussianBlur(pm_u8[..., 3:4], (ksize, ksize), sigma_space)
        if blurred_a.ndim == 2:
            blurred_a = blurred_a[..., np.newaxis]

        blurred = np.concatenate(
            [blurred_rgb.astype(np.float32) / 255.0,
             blurred_a.astype(np.float32) / 255.0],
            axis=-1,
        )

        return self._unpremultiply(blurred, orig_alpha, preserve)

    def supports_region_rendering(self, params: dict | None = None) -> bool:
        return True

    def region_padding(self, params: dict | None = None) -> int:
        params = params or {}
        radius = int(params.get("radius", self.default_params["radius"]))
        radius = max(1, min(radius, 100))
        return radius * 2 + 2

    def expands_bounds(self, params: dict | None = None) -> bool:
        params = params or {}
        return not bool(params.get("preserve_alpha", self.default_params["preserve_alpha"]))
