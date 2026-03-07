"""Application-level UI coordination signals."""

from PySide6.QtCore import QObject, Signal


class AppSignals(QObject):
    """Cross-controller coordination signals for UI sync tasks."""

    selection_overlay_requested = Signal()
    transform_box_requested = Signal()
    properties_panel_requested = Signal()
    vector_bool_state_requested = Signal()
    rulers_update_requested = Signal()
    history_refresh_requested = Signal()
    canvas_update_requested = Signal()
    brush_cursor_requested = Signal()
    transform_panel_refresh_requested = Signal()
    channels_panel_refresh_requested = Signal()
    duplicate_selection_requested = Signal()
    clone_preview_requested = Signal(int, int)
    adjustment_layer_requested = Signal(str)
    edit_adjustment_requested = Signal(str)
    filter_layer_requested = Signal(str)
    edit_filter_requested = Signal(str)
    text_overlay_requested = Signal()
    text_hover_cursor_requested = Signal(int, int)
    tool_selection_requested = Signal(object)
    text_editing_shortcuts_requested = Signal(bool)