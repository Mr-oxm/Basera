"""Shared UI support services used across controllers and widgets."""

from .guide_ui_state import apply_guides, apply_preview_guide
from .layer_panel_state import (
    reordered_stack_order,
    selected_indices_from_layer_ids,
    sync_panel_selection,
)
from .rasterize_guard import (
    ensure_active_layer_rasterized_for_tool,
    needs_text_layer_rasterization,
    rasterize_active_text_layer,
)
from .selection_ui_state import apply_selection_overlay
from .vector_ui_state import (
    clear_boolean_preview,
    enter_pick_segments_mode,
    exit_pick_segments_mode,
    show_boolean_preview,
    update_boolean_toolbar,
)

__all__ = [
    "apply_guides",
    "apply_preview_guide",
    "apply_selection_overlay",
    "clear_boolean_preview",
    "ensure_active_layer_rasterized_for_tool",
    "enter_pick_segments_mode",
    "exit_pick_segments_mode",
    "needs_text_layer_rasterization",
    "rasterize_active_text_layer",
    "reordered_stack_order",
    "selected_indices_from_layer_ids",
    "show_boolean_preview",
    "sync_panel_selection",
    "update_boolean_toolbar",
]