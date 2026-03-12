"""Engine that applies a stack of layer styles to a layer image."""

import numpy as np

from .style_base import LayerStyle


class StyleEngine:
    """Applies a list of :class:`LayerStyle` objects to a rendered layer.

    Each style's ``.apply()`` handles its own internal opacity *and*
    blend-mode compositing.  The engine simply chains them: each style
    receives the output of the previous one, and the final result is
    returned.  Styles are applied **top-to-bottom** (list order).
    """

    @staticmethod
    def apply_styles(layer_image: np.ndarray, styles: list[LayerStyle]) -> np.ndarray:
        # Fast path: if no styles are enabled, return the original
        # without copying.  The caller must not mutate the result.
        enabled = [s for s in styles if s.params.enabled]
        if not enabled:
            return layer_image
        result = layer_image.copy()
        for style in enabled:
            result = style.apply(result)
        np.clip(result, 0, 1, out=result)
        return result

    @staticmethod
    def can_apply_styles_regionally(styles: list[LayerStyle]) -> bool:
        enabled = [s for s in styles if s.params.enabled]
        return all(style.supports_region_rendering() for style in enabled)

    @staticmethod
    def style_region_padding(styles: list[LayerStyle]) -> int:
        enabled = [s for s in styles if s.params.enabled]
        return sum(style.region_padding() for style in enabled)

    @staticmethod
    def apply_styles_region(
        layer_image: np.ndarray,
        styles: list[LayerStyle],
        offset_x: int,
        offset_y: int,
        full_width: int,
        full_height: int,
    ) -> np.ndarray:
        enabled = [s for s in styles if s.params.enabled]
        if not enabled:
            return layer_image
        result = layer_image.copy()
        for style in enabled:
            result = style.apply_region(result, offset_x, offset_y, full_width, full_height)
        np.clip(result, 0, 1, out=result)
        return result
