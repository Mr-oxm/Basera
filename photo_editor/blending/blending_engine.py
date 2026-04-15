"""Core blending engine — Photoshop-compatible alpha compositing.

Performance-optimised paths
---------------------------
* **Rust native engine** — when the ``photo_engine`` Rust extension is
  available (Phase C), all blending is delegated to SIMD-accelerated
  Rust kernels via PyO3.  This is ~8× faster than NumPy on 1080p.
* **blend_region_inplace** — blends a layer's native-size pixel buffer
  directly into a canvas slice.  Avoids allocating a full-canvas-sized
  placement array (the old ``_place`` pattern), cutting memory traffic
  by orders of magnitude for small layers on large canvases.
* **NORMAL fast-path** — the most common blend mode skips the generic
  blend-function dispatch entirely.  `_normal_inplace` minimises
  temporary arrays by reusing buffers and in-place operations.
* **Fully-transparent skip** — when the overlay alpha is all zero the
  function returns immediately (common for empty layers).
"""

from __future__ import annotations

import numpy as np

from ..core.enums import BlendMode
from .blend_modes import get_blend_func

try:
    import photo_engine as _rust_engine
except ImportError:
    _rust_engine = None

# HSL-based modes that require multi-channel logic not yet in Rust
_UNSUPPORTED_RUST_MODES = frozenset({
    BlendMode.HUE, BlendMode.SATURATION,
    BlendMode.COLOR, BlendMode.LUMINOSITY,
    BlendMode.DISSOLVE, BlendMode.DARKER_COLOR,
    BlendMode.LIGHTER_COLOR,
})


class BlendingEngine:
    """Composites two RGBA layers with any blend mode."""

    # ------------------------------------------------------------------
    # HIGH-PERFORMANCE: region-based in-place blending
    # ------------------------------------------------------------------

    @staticmethod
    def blend_region_inplace(
        canvas: np.ndarray,
        pixels: np.ndarray,
        position: tuple[int, int],
        mode: BlendMode = BlendMode.NORMAL,
        opacity: float = 1.0,
        mask: np.ndarray | None = None,
    ) -> None:
        """Blend *pixels* at *position* into *canvas* **in-place**.

        This is the fast path that replaces the old _place → blend
        pipeline.  It only touches the overlapping rectangle, so a
        100×100 layer on a 1920×1080 canvas is ~200× cheaper than
        allocating + scanning two full-canvas arrays.

        Parameters
        ----------
        canvas : (H, W, 4) float32 — destination, modified in-place.
        pixels : (h, w, 4) float32 — source layer at native size.
        position : (x, y) — top-left on the canvas.
        mode, opacity : blend mode & layer opacity.
        mask : optional (h, w) float32 — layer mask at native size.
        """
        # --- Rust fast path (Phase C) ---
        if _rust_engine is not None and mode not in _UNSUPPORTED_RUST_MODES:
            mask_2d = None
            if mask is not None:
                mask_2d = mask if mask.ndim == 2 else mask[:, :, 0]
            _rust_engine.blend_region_inplace(
                canvas, pixels,
                int(position[0]), int(position[1]),
                mode.value, float(opacity),
                mask_2d,
            )
            return

        # --- Python/NumPy fallback ---
        ch, cw = canvas.shape[:2]
        lh, lw = pixels.shape[:2]
        lx, ly = position

        sx, sy = max(0, -lx), max(0, -ly)
        dx, dy = max(0, lx), max(0, ly)
        w = min(lw - sx, cw - dx)
        h = min(lh - sy, ch - dy)
        if w <= 0 or h <= 0:
            return

        if mask is not None:
            mh, mw = mask.shape[:2]
            w = min(w, mw - sx)
            h = min(h, mh - sy)
            if w <= 0 or h <= 0:
                return

        base = canvas[dy : dy + h, dx : dx + w]
        over = pixels[sy : sy + h, sx : sx + w]

        over_a = over[..., 3:4]
        if opacity < 1.0:
            over_a = over_a * opacity

        if mask is not None:
            m_roi = mask[sy : sy + h, sx : sx + w]
            over_a = over_a * m_roi[..., np.newaxis]

        if not np.any(over_a):
            return

        if mode == BlendMode.NORMAL:
            _normal_inplace(base, over[..., :3], over_a)
            return

        blend_fn = get_blend_func(mode)
        blended = blend_fn(base[..., :3], over[..., :3])
        np.clip(blended, 0, 1, out=blended)
        _porter_duff_inplace(base, blended, over_a)

    # ------------------------------------------------------------------
    # LEGACY: full-array blending (kept for backward compat)
    # ------------------------------------------------------------------

    @staticmethod
    def blend(
        base: np.ndarray,
        overlay: np.ndarray,
        mode: BlendMode = BlendMode.NORMAL,
        opacity: float = 1.0,
    ) -> np.ndarray:
        over_a = overlay[..., 3:4] * opacity

        if mode == BlendMode.NORMAL:
            result = base.copy()
            _normal_inplace(result, overlay[..., :3], over_a)
            return result

        blend_fn = get_blend_func(mode)
        blended = blend_fn(base[..., :3], overlay[..., :3])
        np.clip(blended, 0, 1, out=blended)

        result = base.copy()
        _porter_duff_inplace(result, blended, over_a)
        return result

    @staticmethod
    def blend_with_mask(
        base: np.ndarray,
        overlay: np.ndarray,
        mask: np.ndarray | None,
        mode: BlendMode = BlendMode.NORMAL,
        opacity: float = 1.0,
    ) -> np.ndarray:
        if mask is not None:
            eff_opacity = overlay[..., 3:4] * opacity
            m = mask[..., np.newaxis] if mask.ndim == 2 else mask
            eff_opacity = eff_opacity * m
        else:
            eff_opacity = overlay[..., 3:4] * opacity

        if mode == BlendMode.NORMAL:
            result = base.copy()
            _normal_inplace(result, overlay[..., :3], eff_opacity)
            return result

        blend_fn = get_blend_func(mode)
        blended = blend_fn(base[..., :3], overlay[..., :3])
        np.clip(blended, 0, 1, out=blended)

        result = base.copy()
        _porter_duff_inplace(result, blended, eff_opacity)
        return result


# =====================================================================
# Module-private helpers (tight inner loops)
# =====================================================================

def _normal_inplace(base: np.ndarray, over_rgb: np.ndarray, over_a: np.ndarray) -> None:
    """Porter-Duff 'over' for NORMAL blend, written into *base* in-place.

    Optimised to minimise temporary arrays:
    * Reuses ``inv_a`` buffer for the weighted base-alpha term.
    * In-place multiply, add, and divide on ``base`` slices.
    * Total scratch: 1×1-ch (inv_a) + 1×1-ch (out_a) + 1×3-ch
      (over_rgb*over_a) — roughly 3× less memory traffic than the
      naive implementation.
    """
    base_a = base[..., 3:4]

    # inv_a = (1 - over_a), then *= base_a → base_a * (1 - over_a)
    inv_a = np.subtract(1.0, over_a)
    inv_a *= base_a                           # inv_a := base_a * (1 - over_a)

    # out_a = over_a + base_a * (1 - over_a)
    out_a = np.add(over_a, inv_a)

    # safe_a for division (in-place clamp)
    safe_a = np.maximum(out_a, 1e-10, out=out_a.copy())

    # RGB: base[:3] = (over_rgb * over_a + base[:3] * inv_a) / safe_a
    # Do it in-place on base to minimise copies:
    base[..., :3] *= inv_a                     # base_rgb *= base_a*(1-over_a)
    base[..., :3] += over_rgb * over_a         # += over contribution
    base[..., :3] /= safe_a                    # normalise

    base[..., 3:4] = out_a


def _porter_duff_inplace(base: np.ndarray, blended_rgb: np.ndarray, over_a: np.ndarray) -> None:
    """Porter-Duff 'over' for a pre-blended RGB, written into *base* in-place."""
    base_a = base[..., 3:4]
    inv_a = np.subtract(1.0, over_a)
    inv_a *= base_a
    out_a = np.add(over_a, inv_a)
    safe_a = np.maximum(out_a, 1e-10)
    base[..., :3] *= inv_a
    base[..., :3] += blended_rgb * over_a
    base[..., :3] /= safe_a
    base[..., 3:4] = out_a
