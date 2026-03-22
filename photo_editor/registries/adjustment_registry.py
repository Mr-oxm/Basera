"""Registry for non-destructive adjustment processors."""

from __future__ import annotations

from functools import lru_cache
from importlib import import_module

from ..adjustments.adjustment_base import Adjustment

_ADJUSTMENT_SPECS: dict[str, tuple[str, str]] = {
    "Brightness/Contrast": ("photo_editor.adjustments.brightness_contrast", "BrightnessContrast"),
    "Levels": ("photo_editor.adjustments.levels", "Levels"),
    "Curves": ("photo_editor.adjustments.curves", "Curves"),
    "Exposure": ("photo_editor.adjustments.exposure", "Exposure"),
    "Vibrance": ("photo_editor.adjustments.vibrance", "Vibrance"),
    "Hue/Saturation": ("photo_editor.adjustments.hue_saturation", "HueSaturation"),
    "Color Balance": ("photo_editor.adjustments.color_balance", "ColorBalance"),
    "Black & White": ("photo_editor.adjustments.black_white", "BlackWhite"),
    "Photo Filter": ("photo_editor.adjustments.photo_filter", "PhotoFilter"),
    "Gradient Map": ("photo_editor.adjustments.gradient_map", "GradientMap"),
    "Selective Color": ("photo_editor.adjustments.selective_color", "SelectiveColor"),
    "Channel Mixer": ("photo_editor.adjustments.channel_mixer", "ChannelMixer"),
    "Invert": ("photo_editor.adjustments.invert", "Invert"),
    "Posterize": ("photo_editor.adjustments.posterize", "Posterize"),
    "Threshold": ("photo_editor.adjustments.threshold", "Threshold"),
    "White Balance": ("photo_editor.adjustments.white_balance", "WhiteBalance"),
    "Recolor": ("photo_editor.adjustments.recolor", "Recolor"),
    "Split Toning": ("photo_editor.adjustments.split_toning", "SplitToning"),
    "Normals": ("photo_editor.adjustments.normals", "Normals"),
}


def _load_class(module_name: str, class_name: str) -> type[Adjustment]:
    module = import_module(module_name)
    loaded = getattr(module, class_name)
    if not issubclass(loaded, Adjustment):
        raise TypeError(f"{module_name}.{class_name} is not an Adjustment")
    return loaded


@lru_cache(maxsize=1)
def get_adjustment_map() -> dict[str, type[Adjustment]]:
    """Return display-name to adjustment-class mapping."""
    return {
        name: _load_class(module_name, class_name)
        for name, (module_name, class_name) in _ADJUSTMENT_SPECS.items()
    }


def get_adjustment_class(name: str) -> type[Adjustment] | None:
    """Return the adjustment class for a display name."""
    return get_adjustment_map().get(name)