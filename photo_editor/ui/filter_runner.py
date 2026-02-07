"""Runs adjustment and filter dialogs and applies results to the document."""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QWidget

from ..core.document import Document
from .dialogs.filter_dialog import FilterDialog


# ---- Adjustment class registry ---------------------------------------------

def _adj_map() -> dict[str, type]:
    from ..adjustments.brightness_contrast import BrightnessContrast
    from ..adjustments.levels import Levels
    from ..adjustments.curves import Curves
    from ..adjustments.exposure import Exposure
    from ..adjustments.vibrance import Vibrance
    from ..adjustments.hue_saturation import HueSaturation
    from ..adjustments.color_balance import ColorBalance
    from ..adjustments.black_white import BlackWhite
    from ..adjustments.photo_filter import PhotoFilter
    from ..adjustments.gradient_map import GradientMap
    from ..adjustments.selective_color import SelectiveColor
    from ..adjustments.channel_mixer import ChannelMixer
    from ..adjustments.invert import Invert
    from ..adjustments.posterize import Posterize
    from ..adjustments.threshold import Threshold
    return {
        "Brightness/Contrast": BrightnessContrast,
        "Levels": Levels, "Curves": Curves, "Exposure": Exposure,
        "Vibrance": Vibrance, "Hue/Saturation": HueSaturation,
        "Color Balance": ColorBalance, "Black & White": BlackWhite,
        "Photo Filter": PhotoFilter, "Gradient Map": GradientMap,
        "Selective Color": SelectiveColor, "Channel Mixer": ChannelMixer,
        "Invert": Invert, "Posterize": Posterize, "Threshold": Threshold,
    }


# ---- Filter class registry ------------------------------------------------

def _filter_map() -> dict[str, type]:
    from ..filters.blur.gaussian_blur import GaussianBlur
    from ..filters.blur.motion_blur import MotionBlur
    from ..filters.blur.radial_blur import RadialBlur
    from ..filters.blur.surface_blur import SurfaceBlur
    from ..filters.blur.lens_blur import LensBlur
    from ..filters.sharpen.sharpen import Sharpen
    from ..filters.sharpen.unsharp_mask import UnsharpMask
    from ..filters.sharpen.smart_sharpen import SmartSharpen
    from ..filters.noise.add_noise import AddNoise
    from ..filters.noise.reduce_noise import ReduceNoise
    from ..filters.noise.dust_scratches import DustScratches
    from ..filters.noise.median import MedianFilter
    from ..filters.distort.ripple import Ripple
    from ..filters.distort.wave import Wave
    from ..filters.distort.twirl import Twirl
    from ..filters.distort.pinch import Pinch
    from ..filters.distort.perspective import PerspectiveFilter
    from ..filters.stylize.emboss import Emboss
    from ..filters.stylize.find_edges import FindEdges
    from ..filters.stylize.solarize import Solarize
    from ..filters.stylize.oil_paint import OilPaint
    from ..filters.render.clouds import Clouds
    from ..filters.render.difference_clouds import DifferenceClouds
    from ..filters.render.lighting_effects import LightingEffects
    return {
        "gaussian_blur": GaussianBlur, "motion_blur": MotionBlur,
        "radial_blur": RadialBlur, "surface_blur": SurfaceBlur,
        "lens_blur": LensBlur, "sharpen": Sharpen,
        "unsharp_mask": UnsharpMask, "smart_sharpen": SmartSharpen,
        "add_noise": AddNoise, "reduce_noise": ReduceNoise,
        "dust__scratches": DustScratches, "median": MedianFilter,
        "ripple": Ripple, "wave": Wave, "twirl": Twirl,
        "pinch": Pinch, "perspective": PerspectiveFilter,
        "emboss": Emboss, "find_edges": FindEdges,
        "solarize": Solarize, "oil_paint": OilPaint,
        "clouds": Clouds, "difference_clouds": DifferenceClouds,
        "lighting_effects": LightingEffects,
    }


def run_adjustment(name: str, doc: Document, parent: QWidget | None = None) -> bool:
    """Show a dialog for *name*, apply to active layer. Returns True if applied."""
    adj_cls = _adj_map().get(name)
    if adj_cls is None:
        return False
    adj = adj_cls()

    # Invert has no params — apply immediately
    if not adj.default_params:
        return _apply_to_layer(doc, adj, {})

    dlg = FilterDialog(f"Adjustment — {name}", adj.default_params, parent=parent)
    if dlg.exec():
        return _apply_to_layer(doc, adj, dlg.get_params())
    return False


def run_filter(key: str, doc: Document, parent: QWidget | None = None) -> bool:
    """Show a dialog for filter *key*, apply to active layer."""
    filt_cls = _filter_map().get(key)
    if filt_cls is None:
        return False
    filt = filt_cls()

    if not filt.default_params:
        return _apply_to_layer(doc, filt, {})

    dlg = FilterDialog(f"Filter — {filt.name}", filt.default_params, parent=parent)
    if dlg.exec():
        return _apply_to_layer(doc, filt, dlg.get_params())
    return False


def _apply_to_layer(doc: Document, processor, params: dict) -> bool:
    layer = doc.layers.active_layer
    if layer is None or layer.locked:
        return False
    doc.save_snapshot(processor.name)
    layer.pixels = processor.apply(layer.pixels, params)
    return True
