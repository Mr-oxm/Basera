"""Twirl distortion filter."""

import cv2
import numpy as np

from ..filter_base import Filter


class Twirl(Filter):
    """Twirl (swirl) pixels around a centre point.

    Parameters
    ----------
    angle : float
        Maximum rotation in degrees at the centre, range [-999, 999].
    radius : float
        Normalised radius of the twirl effect (0-1 fraction of the
        shorter image dimension).  Defaults to 0.5.
    """

    def __init__(self) -> None:
        super().__init__("Twirl", {"angle": 90.0, "radius": 0.5})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).astype(np.float32)
        alpha = self._alpha(image)

        angle_deg = float(params.get("angle", self.default_params["angle"]))
        radius_frac = float(params.get("radius", self.default_params["radius"]))
        angle_deg = max(-999.0, min(angle_deg, 999.0))
        radius_frac = max(0.01, min(radius_frac, 1.0))

        h, w = rgb.shape[:2]
        cx, cy = w / 2.0, h / 2.0
        max_radius = radius_frac * min(w, h) / 2.0
        angle_rad = np.radians(angle_deg)

        # Build remap grids.
        x_coords, y_coords = np.meshgrid(
            np.arange(w, dtype=np.float32),
            np.arange(h, dtype=np.float32),
        )

        dx = x_coords - cx
        dy = y_coords - cy
        dist = np.sqrt(dx * dx + dy * dy)

        # Twirl amount falls off linearly with distance.
        falloff = np.clip(1.0 - dist / max_radius, 0, 1)
        theta = falloff * angle_rad

        cos_t = np.cos(theta).astype(np.float32)
        sin_t = np.sin(theta).astype(np.float32)

        map_x = (cx + cos_t * dx - sin_t * dy).astype(np.float32)
        map_y = (cy + sin_t * dx + cos_t * dy).astype(np.float32)

        distorted = cv2.remap(
            rgb, map_x, map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        )

        alpha_f = alpha.astype(np.float32)
        alpha_out = cv2.remap(
            alpha_f, map_x, map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        )
        if alpha_out.ndim == 2:
            alpha_out = alpha_out[..., np.newaxis]

        return self._merge(distorted, alpha_out)
