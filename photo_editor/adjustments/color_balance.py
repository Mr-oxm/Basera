"""Color Balance non-destructive adjustment."""

import numpy as np

from .adjustment_base import Adjustment


class ColorBalance(Adjustment):
    """Photoshop-style colour balance for shadows, midtones, and highlights.

    Each tonal range receives an independent (R, G, B) shift.  A smooth
    weighting function assigns every pixel to its tonal band based on
    luminance.
    """

    def __init__(self) -> None:
        super().__init__(
            "Color Balance",
            {
                "shadows_rgb": (0.0, 0.0, 0.0),
                "midtones_rgb": (0.0, 0.0, 0.0),
                "highlights_rgb": (0.0, 0.0, 0.0),
            },
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _tonal_weights(lum: np.ndarray):
        """Compute smooth shadow / midtone / highlight masks from luminance.

        Shadow peaks near 0, highlight peaks near 1, midtone peaks at 0.5.
        All three sum to roughly 1 everywhere.
        """
        shadows = np.clip(1.0 - lum * 4.0, 0.0, 1.0)             # 0→1, >0.25→0
        highlights = np.clip(lum * 4.0 - 3.0, 0.0, 1.0)          # <0.75→0, 1→1
        midtones = np.clip(1.0 - shadows - highlights, 0.0, 1.0)  # remainder
        return shadows, midtones, highlights

    # ------------------------------------------------------------------
    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).copy()
        alpha = self._alpha(image)

        shd = np.array(params.get("shadows_rgb", (0, 0, 0)), dtype=np.float32)
        mid = np.array(params.get("midtones_rgb", (0, 0, 0)), dtype=np.float32)
        hlt = np.array(params.get("highlights_rgb", (0, 0, 0)), dtype=np.float32)

        # Quick exit
        if np.allclose(shd, 0) and np.allclose(mid, 0) and np.allclose(hlt, 0):
            return image.copy()

        # Normalise shifts from [-100, 100] → [-1, 1]
        shd /= 100.0
        mid /= 100.0
        hlt /= 100.0

        lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
        sw, mw, hw = self._tonal_weights(lum)

        # Broadcast to [H, W, 1] for per-channel multiply
        shift = (
            sw[..., np.newaxis] * shd
            + mw[..., np.newaxis] * mid
            + hw[..., np.newaxis] * hlt
        )

        rgb += shift
        return self._merge(rgb, alpha)
