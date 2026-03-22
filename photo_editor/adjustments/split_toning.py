"""Split toning — hue/sat tint in shadows and highlights with balance."""

from __future__ import annotations

import numpy as np

from ..utils.color_utils import hsv_to_rgb, luminance
from .adjustment_base import Adjustment


def _smoothstep01(t: np.ndarray) -> np.ndarray:
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class SplitToning(Adjustment):
    def __init__(self) -> None:
        super().__init__(
            "Split Toning",
            {
                "highlights_hue": 0.0,
                "highlights_saturation": 0.0,
                "shadows_hue": 0.0,
                "shadows_saturation": 0.0,
                "balance": 50.0,
            },
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).copy()
        alpha = self._alpha(image)

        h_hi = float(params.get("highlights_hue", 0)) % 360.0 / 360.0
        s_hi = float(np.clip(params.get("highlights_saturation", 0), 0, 100)) / 100.0
        h_sh = float(params.get("shadows_hue", 0)) % 360.0 / 360.0
        s_sh = float(np.clip(params.get("shadows_saturation", 0), 0, 100)) / 100.0
        bal = float(np.clip(params.get("balance", 50), 0, 100)) / 100.0

        if s_hi < 1e-6 and s_sh < 1e-6:
            return image.copy()

        L = luminance(rgb)
        # Crossover shifts with balance (more highlight tint when balance is high).
        thr = 0.12 + 0.76 * bal
        soft = 0.22
        w_h = _smoothstep01(np.clip((L - thr) / soft, 0.0, 1.0))
        w_s = _smoothstep01(np.clip((thr - L) / soft, 0.0, 1.0))
        sumw = w_h + w_s
        if np.any(sumw > 1.0):
            scale = np.where(sumw > 1.0, 1.0 / (sumw + 1e-8), 1.0)
            w_h = w_h * scale
            w_s = w_s * scale
        w0 = 1.0 - w_h - w_s
        w0 = np.clip(w0, 0.0, 1.0)

        rgb_hi = hsv_to_rgb(
            np.stack(
                [
                    np.full_like(L, h_hi, dtype=np.float32),
                    np.full_like(L, s_hi, dtype=np.float32),
                    L,
                ],
                axis=-1,
            ),
        )
        rgb_sh = hsv_to_rgb(
            np.stack(
                [
                    np.full_like(L, h_sh, dtype=np.float32),
                    np.full_like(L, s_sh, dtype=np.float32),
                    L,
                ],
                axis=-1,
            ),
        )

        out = (
            rgb * w0[..., np.newaxis]
            + rgb_hi * w_h[..., np.newaxis]
            + rgb_sh * w_s[..., np.newaxis]
        )
        return self._merge(out.astype(np.float32), alpha)
