"""Properties panel — shows editable parameters for the active layer / tool.

When the Text tool is active, the panel switches to a specialised
layout with font picker, bold/italic/underline toggles, alignment,
colour, and spacing controls.

When the Gradient tool is active, the panel switches to a gradient
properties bar with colour / gradient picker, type selector, opacity,
and reverse.
"""

from __future__ import annotations

# Re-export from the split properties package for backward compatibility
from .properties import (
    BrushPropertiesBar,
    CropPropertiesBar,
    GradientPropertiesBar,
    MovePropertiesBar,
    PropertiesPanel,
    SelectionPropertiesBar,
    TextPropertiesBar,
    VectorPropertiesBar,
    ZoomPropertiesBar,
)

__all__ = [
    "PropertiesPanel",
    "BrushPropertiesBar",
    "TextPropertiesBar",
    "GradientPropertiesBar",
    "MovePropertiesBar",
    "SelectionPropertiesBar",
    "ZoomPropertiesBar",
    "CropPropertiesBar",
    "VectorPropertiesBar",
]
