"""Smart Sharpen filter."""

import cv2
import numpy as np

from ..filter_base import Filter


class SmartSharpen(Filter):
    """Edge-aware sharpening using Laplacian-of-Gaussian approach.

    Unlike basic sharpening, Smart Sharpen uses a Gaussian-weighted
    Laplacian to avoid amplifying noise.

    Parameters
    ----------
    amount : int
        Sharpening strength as percentage, range [1, 500].
    radius : float
        Controls the scale of detail sharpened, range [0.1, 64].
    """

    def __init__(self) -> None:
        super().__init__("Smart Sharpen", {"amount": 100, "radius": 1.0})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).astype(np.float32)
        alpha = self._alpha(image)

        amount = int(params.get("amount", self.default_params["amount"]))
        radius = float(params.get("radius", self.default_params["radius"]))
        amount = max(1, min(amount, 500))
        radius = max(0.1, min(radius, 64.0))

        strength = amount / 100.0
        sigma = radius

        ksize = int(np.ceil(sigma * 6)) | 1
        ksize = max(3, ksize)

        # Step 1: Gaussian blur at the given radius.
        blurred = cv2.GaussianBlur(rgb, (ksize, ksize), sigmaX=sigma, sigmaY=sigma)

        # Step 2: Edge map to protect flat regions (reduces halo artefacts).
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        gray_blurred = cv2.GaussianBlur(gray, (ksize, ksize), sigmaX=sigma, sigmaY=sigma)
        edge_map = np.abs(gray - gray_blurred)
        # Normalise edge map to [0, 1] and expand to 3 channels.
        edge_max = edge_map.max()
        if edge_max > 0:
            edge_map = edge_map / edge_max
        edge_map = np.clip(edge_map, 0, 1)
        edge_map_3ch = edge_map[..., np.newaxis]

        # Step 3: Unsharp mask weighted by edge map.
        detail = rgb - blurred
        sharpened = rgb + strength * detail * edge_map_3ch

        return self._merge(sharpened, alpha)
