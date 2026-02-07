"""Selective Color non-destructive adjustment."""

import numpy as np

from .adjustment_base import Adjustment
from ..utils.color_utils import rgb_to_hsl


class SelectiveColor(Adjustment):
    """Photoshop-style Selective Color adjustment.

    Targets a specific colour range (reds, yellows, greens, cyans,
    blues, magentas, whites, neutrals, blacks) and shifts its CMYK
    components independently.

    Parameters
    ----------
    color_range : str
        One of ``"reds"``, ``"yellows"``, ``"greens"``, ``"cyans"``,
        ``"blues"``, ``"magentas"``, ``"whites"``, ``"neutrals"``,
        ``"blacks"``.
    cyan, magenta, yellow, black : float
        Adjustments in [-100, 100] (percentage).
    """

    def __init__(self) -> None:
        super().__init__(
            "Selective Color",
            {
                "color_range": "reds",
                "cyan": 0,
                "magenta": 0,
                "yellow": 0,
                "black": 0,
            },
        )

    # Hue-centre in [0,1] and tonal range helpers
    _HUE_RANGES: dict[str, tuple[float, float]] = {
        "reds":     (330 / 360, 30 / 360),
        "yellows":  (30 / 360, 90 / 360),
        "greens":   (90 / 360, 150 / 360),
        "cyans":    (150 / 360, 210 / 360),
        "blues":    (210 / 360, 270 / 360),
        "magentas": (270 / 360, 330 / 360),
    }

    @staticmethod
    def _hue_mask(h: np.ndarray, lo: float, hi: float) -> np.ndarray:
        """Build a smooth mask for pixels within a hue range.

        Handles wrap-around (e.g. reds crossing the 0/360 boundary).
        """
        if lo > hi:
            # Wraps around 0 (e.g. reds: 330°→30°)
            dist = np.minimum(
                np.minimum(np.abs(h - lo), np.abs(h - lo - 1.0)),
                np.minimum(np.abs(h - hi), np.abs(h - hi + 1.0)),
            )
            span = (1.0 - lo + hi) / 2.0
        else:
            centre = (lo + hi) / 2.0
            dist = np.abs(h - centre)
            span = (hi - lo) / 2.0

        mask = np.clip(1.0 - dist / max(span, 1e-6), 0.0, 1.0)
        return mask.astype(np.float32)

    @staticmethod
    def _tonal_mask(lum: np.ndarray, kind: str) -> np.ndarray:
        if kind == "whites":
            return np.clip((lum - 0.5) * 2.0, 0.0, 1.0).astype(np.float32)
        if kind == "blacks":
            return np.clip((0.5 - lum) * 2.0, 0.0, 1.0).astype(np.float32)
        # neutrals — peak at 0.5, falloff toward 0 and 1
        return np.clip(1.0 - np.abs(lum - 0.5) * 4.0, 0.0, 1.0).astype(np.float32)

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).copy()
        alpha = self._alpha(image)

        cr = str(params.get("color_range", "reds")).lower()
        c_adj = float(params.get("cyan", 0)) / 100.0
        m_adj = float(params.get("magenta", 0)) / 100.0
        y_adj = float(params.get("yellow", 0)) / 100.0
        k_adj = float(params.get("black", 0)) / 100.0

        if c_adj == 0 and m_adj == 0 and y_adj == 0 and k_adj == 0:
            return image.copy()

        # Build selection mask
        if cr in self._HUE_RANGES:
            hsl = rgb_to_hsl(rgb)
            lo, hi = self._HUE_RANGES[cr]
            mask = self._hue_mask(hsl[..., 0], lo, hi)
            # Weight by saturation so greys are excluded
            mask *= np.clip(hsl[..., 1] * 2.0, 0.0, 1.0)
        elif cr in ("whites", "neutrals", "blacks"):
            lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
            mask = self._tonal_mask(lum, cr)
        else:
            return image.copy()

        mask = mask[..., np.newaxis]

        # Convert adjustments from CMY(K) space to RGB shifts
        # C ↑ → R ↓,  M ↑ → G ↓,  Y ↑ → B ↓
        shift = np.array([-c_adj, -m_adj, -y_adj], dtype=np.float32)

        # Black slider uniformly darkens/lightens the selected range
        if k_adj != 0:
            shift -= k_adj  # negative k_adj brightens

        rgb += mask * shift

        return self._merge(rgb, alpha)
