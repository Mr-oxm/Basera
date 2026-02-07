"""Bevel and Emboss layer style – highlight and shadow from alpha edge normals."""

import cv2
import numpy as np

from .style_base import LayerStyle


class BevelEmboss(LayerStyle):
    """Generate a 3-D highlight / shadow from the alpha channel edge normals."""

    def __init__(self) -> None:
        super().__init__("Bevel and Emboss")
        self.params.extra = {
            "depth": 3,
            "size": 5,
            "soften": 0,
            "angle": 120,
            "altitude": 30,
        }

    # ------------------------------------------------------------------
    def apply(self, layer_image: np.ndarray) -> np.ndarray:
        img = self._f32(layer_image).copy()
        p = self.params.extra
        if not self.params.enabled:
            return img

        depth = float(p["depth"])
        size = int(p["size"])
        soften = int(p["soften"])
        angle_rad = np.deg2rad(float(p["angle"]))
        alt_rad = np.deg2rad(float(p["altitude"]))

        alpha = img[:, :, 3]

        # Smooth the alpha to get a "height map"
        ksize = max(size * 2 + 1, 1)
        if ksize > 1:
            height = cv2.GaussianBlur(alpha, (ksize, ksize), 0)
        else:
            height = alpha.copy()

        # Compute gradients (normals)
        grad_x = cv2.Sobel(height, cv2.CV_32F, 1, 0, ksize=3) * depth
        grad_y = cv2.Sobel(height, cv2.CV_32F, 0, 1, ksize=3) * depth

        # Light direction
        lx = np.cos(angle_rad) * np.cos(alt_rad)
        ly = -np.sin(angle_rad) * np.cos(alt_rad)
        lz = np.sin(alt_rad)

        # Normalise surface normals (-grad_x, -grad_y, 1)
        nx = -grad_x
        ny = -grad_y
        nz = np.ones_like(nx)
        mag = np.sqrt(nx * nx + ny * ny + nz * nz) + 1e-8
        nx /= mag
        ny /= mag
        nz /= mag

        # Dot product => lighting intensity in [-1, 1]
        shade = nx * lx + ny * ly + nz * lz

        # Optional soften
        if soften > 0:
            sk = soften * 2 + 1
            shade = cv2.GaussianBlur(shade, (sk, sk), 0)

        # Separate highlight (> 0) and shadow (< 0)
        highlight = np.clip(shade, 0, 1)
        shadow = np.clip(-shade, 0, 1)

        # Apply only inside the layer
        opacity = self.params.opacity
        out = img.copy()
        for c in range(3):
            lit = img[:, :, c] + highlight * opacity - shadow * opacity * 0.5
            out[:, :, c] = np.where(alpha > 0, lit, img[:, :, c])

        return np.clip(out, 0, 1)
