"""Black & White non-destructive adjustment."""

import numpy as np

from .adjustment_base import Adjustment
from ..utils.color_utils import rgb_to_hsl


class BlackWhite(Adjustment):
    """Convert a colour image to monochrome using per-hue channel weights.

    Six colour sliders (Red, Yellow, Green, Cyan, Blue, Magenta) control
    the luminance contribution of each hue band — identical in concept
    to the Photoshop Black & White adjustment.
    """

    def __init__(self) -> None:
        super().__init__(
            "Black & White",
            {
                "red": 40,
                "yellow": 60,
                "green": 40,
                "cyan": 60,
                "blue": 20,
                "magenta": 80,
            },
        )

    # Six hue-centre angles in [0, 1] (i.e. hue / 360)
    _HUE_CENTRES = np.array([0 / 360, 60 / 360, 120 / 360,
                              180 / 360, 240 / 360, 300 / 360],
                             dtype=np.float32)

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image)
        alpha = self._alpha(image)

        weights = np.array([
            float(params.get("red", 40)),
            float(params.get("yellow", 60)),
            float(params.get("green", 40)),
            float(params.get("cyan", 60)),
            float(params.get("blue", 20)),
            float(params.get("magenta", 80)),
        ], dtype=np.float32) / 100.0  # normalise percentages

        hsl = rgb_to_hsl(rgb)
        h = hsl[..., 0]  # [0, 1]

        # Base luminance (Rec. 709)
        lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]

        # Build blending weight from the six hue bands
        # Each band covers 60° (1/6 of the circle). We use a cosine
        # bell so neighbouring bands overlap smoothly.
        blend = np.zeros_like(lum)
        for i, hc in enumerate(self._HUE_CENTRES):
            # Circular distance in [0, 0.5]
            dist = np.abs(h - hc)
            dist = np.minimum(dist, 1.0 - dist)
            # Cosine bell with 1/6 (60°) half-width
            influence = np.clip(np.cos(dist * 6.0 * np.pi) * 0.5 + 0.5, 0.0, 1.0)
            blend += influence * weights[i]

        # Normalise so that a uniform 100 % across all channels → original lum
        blend = np.clip(blend, 0.0, None)

        grey = lum * blend
        grey = np.clip(grey, 0.0, 1.0)

        result = np.stack([grey, grey, grey], axis=-1).astype(np.float32)
        return self._merge(result, alpha)
