"""Difference Clouds render filter."""

import cv2
import numpy as np

from ..filter_base import Filter


class DifferenceClouds(Filter):
    """Generate cloud noise and blend it with the image via *difference* mode.

    The cloud pattern is generated using fractal value noise, then the
    absolute difference between the image and the cloud is computed,
    producing a marble-like texture when applied repeatedly.

    No required parameters.
    """

    def __init__(self) -> None:
        super().__init__(
            "Difference Clouds",
            {"seed": 0, "scale": 4.0, "octaves": 6},
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _value_noise(h: int, w: int, scale: float, octaves: int,
                     rng: np.random.Generator) -> np.ndarray:
        """Generate 2-D fractal value noise in [0, 1]."""
        noise = np.zeros((h, w), dtype=np.float32)
        amplitude = 1.0
        total_amp = 0.0

        for _ in range(octaves):
            gh = max(2, int(np.ceil(h / scale)) + 2)
            gw = max(2, int(np.ceil(w / scale)) + 2)
            grid = rng.random((gh, gw)).astype(np.float32)
            upsampled = cv2.resize(grid, (w, h), interpolation=cv2.INTER_LINEAR)
            noise += upsampled * amplitude
            total_amp += amplitude
            amplitude *= 0.5
            scale = max(1.0, scale * 0.5)

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
        cloud = np.stack([noise] * 3, axis=-1).astype(np.float32)

        # Difference blend mode: |image - cloud|
        result = np.abs(rgb - cloud)

        return self._merge(result, alpha)
