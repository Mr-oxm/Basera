"""Clouds render filter (Perlin-like noise)."""

import cv2
import numpy as np

from ..filter_base import Filter


class Clouds(Filter):
    """Generate a cloud texture via fractal (multi-octave) value noise.

    The result blends the generated cloud pattern with the current
    foreground and background colours (white and black by default).

    No required parameters.
    """

    def __init__(self) -> None:
        super().__init__("Clouds", {"seed": 0, "scale": 4.0, "octaves": 6})

    # ------------------------------------------------------------------
    @staticmethod
    def _value_noise(h: int, w: int, scale: float, octaves: int,
                     rng: np.random.Generator) -> np.ndarray:
        """Generate 2-D fractal value noise in [0, 1]."""
        noise = np.zeros((h, w), dtype=np.float32)
        amplitude = 1.0
        total_amp = 0.0

        for _ in range(octaves):
            # Grid of random values at the current scale.
            gh = max(2, int(np.ceil(h / scale)) + 2)
            gw = max(2, int(np.ceil(w / scale)) + 2)
            grid = rng.random((gh, gw)).astype(np.float32)

            # Up-sample with bilinear interpolation.
            upsampled = cv2.resize(grid, (w, h), interpolation=cv2.INTER_LINEAR)

            noise += upsampled * amplitude
            total_amp += amplitude
            amplitude *= 0.5
            scale *= 0.5
            scale = max(1.0, scale)

        noise /= total_amp
        return noise

    # ------------------------------------------------------------------
    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).astype(np.float32)
        alpha = self._alpha(image)

        seed = int(params.get("seed", self.default_params["seed"]))
        scale = float(params.get("scale", self.default_params["scale"]))
        octaves = int(params.get("octaves", self.default_params["octaves"]))
        scale = max(1.0, min(scale, 64.0))
        octaves = max(1, min(octaves, 10))

        h, w = rgb.shape[:2]
        rng = np.random.default_rng(seed if seed != 0 else None)

        noise = self._value_noise(h, w, scale, octaves, rng)

        # Map noise to RGB: 0 -> black, 1 -> white.
        cloud = np.stack([noise] * 3, axis=-1).astype(np.float32)

        # Composite: replace RGB with cloud, keep alpha.
        return self._merge(cloud, alpha)
