"""Core blending engine — Photoshop-compatible alpha compositing."""

import numpy as np

from ..core.enums import BlendMode
from .blend_modes import get_blend_func


class BlendingEngine:
    """Composites two RGBA layers with any blend mode."""

    @staticmethod
    def blend(
        base: np.ndarray,
        overlay: np.ndarray,
        mode: BlendMode = BlendMode.NORMAL,
        opacity: float = 1.0,
    ) -> np.ndarray:
        """Blend *overlay* onto *base*.

        Both arrays must be float32 RGBA [H, W, 4] in [0, 1].
        """
        base = np.clip(base, 0, 1)
        overlay = np.clip(overlay, 0, 1)

        base_rgb = base[..., :3]
        base_a = base[..., 3:4]
        over_rgb = overlay[..., :3]
        over_a = overlay[..., 3:4] * opacity

        blend_fn = get_blend_func(mode)
        blended = np.clip(blend_fn(base_rgb, over_rgb), 0, 1)

        # Porter-Duff "over"
        out_a = over_a + base_a * (1 - over_a)
        safe_a = np.where(out_a > 0, out_a, 1.0)
        out_rgb = (blended * over_a + base_rgb * base_a * (1 - over_a)) / safe_a

        result = np.empty_like(base)
        result[..., :3] = out_rgb
        result[..., 3:4] = out_a
        return np.clip(result, 0, 1)

    @staticmethod
    def blend_with_mask(
        base: np.ndarray,
        overlay: np.ndarray,
        mask: np.ndarray | None,
        mode: BlendMode = BlendMode.NORMAL,
        opacity: float = 1.0,
    ) -> np.ndarray:
        """Blend with an optional single-channel mask."""
        if mask is not None:
            masked = overlay.copy()
            m = mask[..., np.newaxis] if mask.ndim == 2 else mask
            masked[..., 3:4] *= m
            return BlendingEngine.blend(base, masked, mode, opacity)
        return BlendingEngine.blend(base, overlay, mode, opacity)
