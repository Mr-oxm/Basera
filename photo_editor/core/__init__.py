"""Core data models, abstractions, and extracted domain services."""

from .enums import BlendMode, LayerType, ToolType
from .color import (
    Color, ColorFill, SolidFill, LinearGradient, RadialGradient,
    GradientStop, FillType,
)
from .color_engine import (
    HSV, HSL, CMYK, LabColor, OklabColor,
    ColorManager, SwatchPalette, HarmonyType,
    ConicalGradient, DiamondGradient,
    color_to_hsv, hsv_to_color, color_to_hsl, hsl_to_color,
    color_to_cmyk, cmyk_to_color, color_to_lab, lab_to_color,
    color_to_oklab, oklab_to_color,
    perceptual_lerp, generate_harmony,
    contrast_ratio, kelvin_to_color,
    GRADIENT_PRESETS,
)
from .layer import Layer
from .layer_stack import LayerStack
from .selection import Selection
from .history import HistoryManager
from .document import Document
from .canvas import CanvasState
from .text_layer import TextLayerData, TextRun, CharFormat, ParagraphFormat

__all__ = [
    "BlendMode", "LayerType", "ToolType",
    "Color", "ColorFill", "SolidFill", "LinearGradient", "RadialGradient",
    "GradientStop", "FillType",
    "Layer", "LayerStack", "Selection",
    "HistoryManager", "Document", "CanvasState",
    "TextLayerData", "TextRun", "CharFormat", "ParagraphFormat",
]
