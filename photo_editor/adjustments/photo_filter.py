"""Photo Filter non-destructive adjustment."""

import numpy as np

from .adjustment_base import Adjustment


class PhotoFilter(Adjustment):
    """Apply a coloured photographic filter over the image.

    Simulates placing a colour-tinted glass filter in front of the lens.
    Luminance is preserved by default (matching Photoshop behaviour).

    Parameters
    ----------
    color : tuple[int, int, int]
        Filter colour in 0-255 RGB.
    density : float
        Strength of the filter, 0-100 %.
    preserve_luminosity : bool
        When *True* (default), the original luminance is restored after
        blending so that only the colour shifts, not brightness.
    """

    def __init__(self) -> None:
        super().__init__(
            "Photo Filter",
            {
                "color": (255, 173, 51),  # warming filter (85)
                "density": 25,
                "preserve_luminosity": True,
            },
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).copy()
        alpha = self._alpha(image)

        color = params.get("color", self.default_params["color"])
        density = float(params.get("density", 25)) / 100.0
        preserve = bool(params.get("preserve_luminosity", True))

        # Normalise filter colour to [0, 1]
        fc = np.array(color, dtype=np.float32) / 255.0

        if preserve:
            # Rec. 709 luminance before blending
            lum_before = (0.2126 * rgb[..., 0]
                          + 0.7152 * rgb[..., 1]
                          + 0.0722 * rgb[..., 2])

        # Multiply blend (colour tint)
        tinted = rgb * fc
        result = rgb * (1.0 - density) + tinted * density

        if preserve:
            lum_after = (0.2126 * result[..., 0]
                         + 0.7152 * result[..., 1]
                         + 0.0722 * result[..., 2])
            ratio = np.where(lum_after > 1e-6,
                             lum_before / lum_after, 1.0)[..., np.newaxis]
            result *= ratio

        return self._merge(result, alpha)
