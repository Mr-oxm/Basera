"""Emboss filter."""

import cv2
import numpy as np

from ..filter_base import Filter


class Emboss(Filter):
    """Create an embossed / raised-surface effect.

    Parameters
    ----------
    angle : float
        Light-source angle in degrees, range [0, 360].
    height : int
        Emboss depth, range [1, 10].
    amount : int
        Effect strength as percentage, range [1, 500].
    """

    def __init__(self) -> None:
        super().__init__(
            "Emboss",
            {"angle": 135.0, "height": 3, "amount": 100},
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).astype(np.float32)
        alpha = self._alpha(image)

        angle = float(params.get("angle", self.default_params["angle"]))
        height = int(params.get("height", self.default_params["height"]))
        amount = int(params.get("amount", self.default_params["amount"]))
        angle = angle % 360.0
        height = max(1, min(height, 10))
        amount = max(1, min(amount, 500))

        strength = amount / 100.0

        # Build a 3x3 emboss kernel oriented at *angle*.
        rad = np.radians(angle)
        dx = np.cos(rad)
        dy = np.sin(rad)

        # Simple directional emboss kernel scaled by height.
        kernel = np.zeros((3, 3), dtype=np.float32)
        # Place negative weight opposite the light direction and positive
        # weight along the light direction through the centre.
        kernel[1, 1] = 1.0
        # Determine the two opposing neighbours based on angle.
        offsets = [(-1, -1), (-1, 0), (-1, 1),
                   (0, -1),           (0, 1),
                   (1, -1),  (1, 0),  (1, 1)]
        weights: list[float] = []
        for oy, ox in offsets:
            dot = ox * dx + oy * dy
            weights.append(dot)

        for (oy, ox), w in zip(offsets, weights):
            kernel[1 + oy, 1 + ox] = -w * height

        # Convert to greyscale for the emboss pass.
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        embossed = cv2.filter2D(gray, -1, kernel)

        # Shift to 0.5 baseline and scale.
        embossed = embossed * strength + 0.5

        # Blend emboss luminance back onto the original colour.
        embossed_3ch = np.stack([embossed] * 3, axis=-1).astype(np.float32)
        result = rgb * embossed_3ch

        return self._merge(result, alpha)
