"""Enumerations used throughout the editor."""

from enum import Enum, auto


class BlendMode(Enum):
    """All Photoshop-compatible blend modes."""

    # Normal
    NORMAL = auto()
    DISSOLVE = auto()
    # Darken
    DARKEN = auto()
    MULTIPLY = auto()
    COLOR_BURN = auto()
    LINEAR_BURN = auto()
    DARKER_COLOR = auto()
    # Lighten
    LIGHTEN = auto()
    SCREEN = auto()
    COLOR_DODGE = auto()
    LINEAR_DODGE = auto()
    LIGHTER_COLOR = auto()
    # Contrast
    OVERLAY = auto()
    SOFT_LIGHT = auto()
    HARD_LIGHT = auto()
    VIVID_LIGHT = auto()
    LINEAR_LIGHT = auto()
    PIN_LIGHT = auto()
    HARD_MIX = auto()
    # Comparative
    DIFFERENCE = auto()
    EXCLUSION = auto()
    SUBTRACT = auto()
    DIVIDE = auto()
    # Color
    HUE = auto()
    SATURATION = auto()
    COLOR = auto()
    LUMINOSITY = auto()


class LayerType(Enum):
    """Supported layer types."""

    RASTER = auto()
    TEXT = auto()
    SHAPE = auto()
    ADJUSTMENT = auto()
    GROUP = auto()
    SMART_OBJECT = auto()


class ToolType(Enum):
    """Available tool identifiers."""

    MOVE = auto()
    BRUSH = auto()
    ERASER = auto()
    CLONE_STAMP = auto()
    HEALING_BRUSH = auto()
    GRADIENT = auto()
    PAINT_BUCKET = auto()
    RECT_SELECT = auto()
    ELLIPSE_SELECT = auto()
    LASSO = auto()
    MAGIC_WAND = auto()
    TEXT = auto()
    SHAPE = auto()
    TRANSFORM = auto()
    ZOOM = auto()
    PAN = auto()
    CROP = auto()
    EYEDROPPER = auto()
