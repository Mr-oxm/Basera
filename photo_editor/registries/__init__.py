"""Lazy registries for adjustments and filters.

These registries are intentionally defined outside the UI layer so core
document restore, controllers, and future plugin-loading code can resolve
processors without importing UI modules.
"""

from .adjustment_registry import get_adjustment_class, get_adjustment_map
from .filter_registry import get_filter_class, get_filter_map, get_filter_name_map

__all__ = [
    "get_adjustment_class",
    "get_adjustment_map",
    "get_filter_class",
    "get_filter_map",
    "get_filter_name_map",
]