"""High-level mask management for layers."""

import numpy as np

from ..core.layer import Layer


class MaskManager:
    """Create, apply, disable, and refine layer masks."""

    @staticmethod
    def add_mask(layer: Layer, fill_white: bool = True) -> None:
        layer.add_mask(fill_white)

    @staticmethod
    def remove_mask(layer: Layer) -> None:
        layer.remove_mask()

    @staticmethod
    def apply_mask(layer: Layer) -> None:
        """Burn the mask into the alpha channel permanently."""
        if layer.mask is not None:
            layer.pixels[..., 3] *= layer.mask
            layer.remove_mask()

    @staticmethod
    def disable_mask(layer: Layer) -> None:
        layer.mask_enabled = False

    @staticmethod
    def enable_mask(layer: Layer) -> None:
        layer.mask_enabled = True

    @staticmethod
    def invert_mask(layer: Layer) -> None:
        if layer.mask is not None:
            layer.mask = 1.0 - layer.mask

    @staticmethod
    def fill_mask(layer: Layer, value: float = 1.0) -> None:
        if layer.mask is not None:
            layer.mask[:] = value

    @staticmethod
    def gradient_mask(layer: Layer, vertical: bool = True) -> None:
        """Fill the mask with a linear gradient."""
        h, w = layer.height, layer.width
        if vertical:
            grad = np.linspace(1.0, 0.0, h, dtype=np.float32)[:, np.newaxis]
            grad = np.broadcast_to(grad, (h, w)).copy()
        else:
            grad = np.linspace(1.0, 0.0, w, dtype=np.float32)[np.newaxis, :]
            grad = np.broadcast_to(grad, (h, w)).copy()
        layer.mask = grad
