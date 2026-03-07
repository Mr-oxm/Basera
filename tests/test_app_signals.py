from photo_editor.ui.app_signals import AppSignals


def test_app_signals_emit_connected_callbacks() -> None:
    signals = AppSignals()
    calls: list[str] = []

    signals.selection_overlay_requested.connect(lambda: calls.append("selection"))
    signals.transform_box_requested.connect(lambda: calls.append("transform"))
    signals.history_refresh_requested.connect(lambda: calls.append("history"))
    signals.clone_preview_requested.connect(lambda x, y: calls.append(f"clone:{x},{y}"))
    signals.duplicate_selection_requested.connect(lambda: calls.append("duplicate"))
    signals.adjustment_layer_requested.connect(lambda name: calls.append(f"add-adjustment:{name}"))
    signals.edit_adjustment_requested.connect(lambda layer_id: calls.append(f"edit-adjustment:{layer_id}"))
    signals.filter_layer_requested.connect(lambda name: calls.append(f"add-filter:{name}"))
    signals.edit_filter_requested.connect(lambda layer_id: calls.append(f"edit-filter:{layer_id}"))
    signals.text_overlay_requested.connect(lambda: calls.append("text-overlay"))
    signals.text_hover_cursor_requested.connect(lambda x, y: calls.append(f"text-hover:{x},{y}"))
    signals.tool_selection_requested.connect(lambda tool: calls.append(f"tool:{tool}"))
    signals.text_editing_shortcuts_requested.connect(lambda editing: calls.append(f"text-shortcuts:{editing}"))

    signals.selection_overlay_requested.emit()
    signals.transform_box_requested.emit()
    signals.history_refresh_requested.emit()
    signals.clone_preview_requested.emit(10, 20)
    signals.duplicate_selection_requested.emit()
    signals.adjustment_layer_requested.emit("Curves")
    signals.edit_adjustment_requested.emit("adj-1")
    signals.filter_layer_requested.emit("Gaussian Blur")
    signals.edit_filter_requested.emit("filter-1")
    signals.text_overlay_requested.emit()
    signals.text_hover_cursor_requested.emit(5, 6)
    signals.tool_selection_requested.emit("node")
    signals.text_editing_shortcuts_requested.emit(True)

    assert calls == [
        "selection",
        "transform",
        "history",
        "clone:10,20",
        "duplicate",
        "add-adjustment:Curves",
        "edit-adjustment:adj-1",
        "add-filter:Gaussian Blur",
        "edit-filter:filter-1",
        "text-overlay",
        "text-hover:5,6",
        "tool:node",
        "text-shortcuts:True",
    ]