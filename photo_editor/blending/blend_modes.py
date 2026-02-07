"""Blend-mode function registry — extensible via register_blend_mode()."""

from __future__ import annotations

from typing import Callable

import numpy as np

from ..core.enums import BlendMode

BlendFunc = Callable[[np.ndarray, np.ndarray], np.ndarray]

_REGISTRY: dict[BlendMode, BlendFunc] = {}


def _populate() -> None:
    """Lazy-load all built-in blend functions."""
    if _REGISTRY:
        return
    from .normal import blend_normal, blend_dissolve
    from .darken import (
        blend_darken, blend_multiply, blend_color_burn,
        blend_linear_burn, blend_darker_color,
    )
    from .lighten import (
        blend_lighten, blend_screen, blend_color_dodge,
        blend_linear_dodge, blend_lighter_color,
    )
    from .contrast import (
        blend_overlay, blend_soft_light, blend_hard_light,
        blend_vivid_light, blend_linear_light, blend_pin_light, blend_hard_mix,
    )
    from .comparative import blend_difference, blend_exclusion, blend_subtract, blend_divide
    from .color_blend import blend_hue, blend_saturation, blend_color, blend_luminosity

    mapping: dict[BlendMode, BlendFunc] = {
        BlendMode.NORMAL: blend_normal, BlendMode.DISSOLVE: blend_dissolve,
        BlendMode.DARKEN: blend_darken, BlendMode.MULTIPLY: blend_multiply,
        BlendMode.COLOR_BURN: blend_color_burn, BlendMode.LINEAR_BURN: blend_linear_burn,
        BlendMode.DARKER_COLOR: blend_darker_color,
        BlendMode.LIGHTEN: blend_lighten, BlendMode.SCREEN: blend_screen,
        BlendMode.COLOR_DODGE: blend_color_dodge, BlendMode.LINEAR_DODGE: blend_linear_dodge,
        BlendMode.LIGHTER_COLOR: blend_lighter_color,
        BlendMode.OVERLAY: blend_overlay, BlendMode.SOFT_LIGHT: blend_soft_light,
        BlendMode.HARD_LIGHT: blend_hard_light, BlendMode.VIVID_LIGHT: blend_vivid_light,
        BlendMode.LINEAR_LIGHT: blend_linear_light, BlendMode.PIN_LIGHT: blend_pin_light,
        BlendMode.HARD_MIX: blend_hard_mix,
        BlendMode.DIFFERENCE: blend_difference, BlendMode.EXCLUSION: blend_exclusion,
        BlendMode.SUBTRACT: blend_subtract, BlendMode.DIVIDE: blend_divide,
        BlendMode.HUE: blend_hue, BlendMode.SATURATION: blend_saturation,
        BlendMode.COLOR: blend_color, BlendMode.LUMINOSITY: blend_luminosity,
    }
    _REGISTRY.update(mapping)


def get_blend_func(mode: BlendMode) -> BlendFunc:
    _populate()
    return _REGISTRY.get(mode, _REGISTRY.get(BlendMode.NORMAL, lambda b, o: o))


def register_blend_mode(mode: BlendMode, func: BlendFunc) -> None:
    """Register a custom / plugin blend mode at runtime."""
    _populate()
    _REGISTRY[mode] = func
