"""Add Noise filter."""

import numpy as np

from ..filter_base import Filter


class AddNoise(Filter):
    """Add synthetic noise to the image.

    Parameters
    ----------
    amount : float
        Noise intensity, range [0, 100].
    gaussian : bool
        If *True* use Gaussian noise; otherwise uniform noise.
    monochromatic : bool
        If *True* the same noise value is used for all channels.
    """

    def __init__(self) -> None:
        super().__init__(
            "Add Noise",
            {"amount": 10.0, "gaussian": True, "monochromatic": False},
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).astype(np.float32)
        alpha = self._alpha(image)

        amount = float(params.get("amount", self.default_params["amount"]))
        gaussian = bool(params.get("gaussian", self.default_params["gaussian"]))
        mono = bool(params.get("monochromatic", self.default_params["monochromatic"]))

        amount = max(0.0, min(amount, 100.0))
        strength = amount / 100.0  # normalise to [0, 1]

        h, w, c = rgb.shape
        rng = np.random.default_rng()

        if mono:
            shape = (h, w, 1)
        else:
            shape = (h, w, c)

        if gaussian:
            noise = rng.standard_normal(shape).astype(np.float32) * strength
        else:
            noise = (rng.random(shape).astype(np.float32) - 0.5) * 2.0 * strength

        if mono:
            noise = np.repeat(noise, c, axis=-1)

        result = rgb + noise
        return self._merge(result, alpha)
