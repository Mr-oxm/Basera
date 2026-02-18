"""Backward-compatible re-exports from the color package.

All color engine functionality has been split into photo_editor.color.
This module re-exports for backward compatibility.
"""

from ..color import (
    HSV, HSL, CMYK, LabColor, OklabColor,
    ColorManager, SwatchPalette, HarmonyType,
    ConicalGradient, DiamondGradient,
    rgb_to_hsv, hsv_to_rgb, rgb_to_hsl, hsl_to_rgb,
    rgb_to_cmyk, cmyk_to_rgb,
    color_to_hsv, hsv_to_color, color_to_hsl, hsl_to_color,
    color_to_cmyk, cmyk_to_color, color_to_lab, lab_to_color,
    color_to_oklab, oklab_to_color,
    perceptual_lerp, generate_harmony,
    contrast_ratio, kelvin_to_color,
    GRADIENT_PRESETS,
)

__all__ = [
    "HSV", "HSL", "CMYK", "LabColor", "OklabColor",
    "ColorManager", "SwatchPalette", "HarmonyType",
    "ConicalGradient", "DiamondGradient",
    "rgb_to_hsv", "hsv_to_rgb", "rgb_to_hsl", "hsl_to_rgb",
    "rgb_to_cmyk", "cmyk_to_rgb",
    "color_to_hsv", "hsv_to_color", "color_to_hsl", "hsl_to_color",
    "color_to_cmyk", "cmyk_to_color", "color_to_lab", "lab_to_color",
    "color_to_oklab", "oklab_to_color",
    "perceptual_lerp", "generate_harmony",
    "contrast_ratio", "kelvin_to_color",
    "GRADIENT_PRESETS",
]
