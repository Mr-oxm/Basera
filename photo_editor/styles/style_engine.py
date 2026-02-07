"""Engine that applies a stack of layer styles to a layer image."""

import numpy as np

from .style_base import LayerStyle


class StyleEngine:
    """Applies a list of LayerStyle objects to a rendered layer."""

    @staticmethod
    def apply_styles(layer_image: np.ndarray, styles: list[LayerStyle]) -> np.ndarray:
        result = layer_image.copy()
        for style in styles:
            if style.params.enabled:
                styled = style.apply(result)
                a = style.params.opacity
                result = result * (1 - a) + styled * a
        return np.clip(result, 0, 1)
