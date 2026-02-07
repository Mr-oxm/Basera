"""Lighting Effects render filter."""

import numpy as np

from ..filter_base import Filter


class LightingEffects(Filter):
    """Simulate a point-light source illuminating the image.

    A simple Lambertian shading model is used: surface normals are
    derived from the image luminance gradient, and the dot product with
    the light direction modulates brightness.

    Parameters
    ----------
    light_x : float
        Normalised X position of the light [0, 1]. Default 0.5.
    light_y : float
        Normalised Y position of the light [0, 1]. Default 0.0 (top).
    intensity : float
        Light intensity multiplier [0, 5]. Default 1.5.
    ambient : float
        Ambient light level [0, 1]. Default 0.2.
    """

    def __init__(self) -> None:
        super().__init__(
            "Lighting Effects",
            {"light_x": 0.5, "light_y": 0.0, "intensity": 1.5, "ambient": 0.2},
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).astype(np.float32)
        alpha = self._alpha(image)

        lx = float(params.get("light_x", self.default_params["light_x"]))
        ly = float(params.get("light_y", self.default_params["light_y"]))
        intensity = float(params.get("intensity", self.default_params["intensity"]))
        ambient = float(params.get("ambient", self.default_params["ambient"]))

        lx = max(0.0, min(lx, 1.0))
        ly = max(0.0, min(ly, 1.0))
        intensity = max(0.0, min(intensity, 5.0))
        ambient = max(0.0, min(ambient, 1.0))

        h, w = rgb.shape[:2]

        # --- Surface normals from luminance gradient ---
        lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
        # Sobel-like gradients.
        dy = np.zeros_like(lum)
        dx = np.zeros_like(lum)
        dy[1:-1, :] = lum[2:, :] - lum[:-2, :]
        dx[:, 1:-1] = lum[:, 2:] - lum[:, :-2]

        # Normal: (-dx, -dy, 1) then normalise.
        nz = np.ones_like(lum)
        length = np.sqrt(dx * dx + dy * dy + nz * nz)
        nx = -dx / length
        ny = -dy / length
        nz = nz / length

        # --- Light direction per pixel ---
        light_pos = np.array([lx * w, ly * h, max(w, h) * 0.5], dtype=np.float32)

        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        ldir_x = light_pos[0] - xx
        ldir_y = light_pos[1] - yy
        ldir_z = np.full((h, w), light_pos[2], dtype=np.float32)

        ld_len = np.sqrt(ldir_x ** 2 + ldir_y ** 2 + ldir_z ** 2) + 1e-10
        ldir_x /= ld_len
        ldir_y /= ld_len
        ldir_z /= ld_len

        # Dot product (Lambertian diffuse).
        dot = np.clip(nx * ldir_x + ny * ldir_y + nz * ldir_z, 0, 1)

        # Distance attenuation (inverse-square, softened).
        atten = 1.0 / (1.0 + (ld_len / max(w, h)) ** 2)

        # Final shading per-pixel.
        shading = ambient + intensity * dot * atten
        shading = shading[..., np.newaxis].astype(np.float32)

        result = rgb * shading
        return self._merge(result, alpha)
