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
        result = layer_image.copy()
        for style in styles:
            if not style.params.enabled:
                continue
            result = style.apply(result)
        return np.clip(result, 0, 1)
