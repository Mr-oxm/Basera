"""Layers panel — visibility toggles, lock buttons, opacity, blend mode, groups.

Visual design inspired by professional photo editors: dark panel with purple
accent colour for the selected layer, compact header with opacity / blend-mode
controls, thumbnail previews, and an icon-based bottom toolbar.
"""

from __future__ import annotations

# Re-export from the split layers package for backward compatibility
from .layers import LayersPanel

__all__ = ["LayersPanel"]
