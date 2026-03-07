"""Shared helpers for layers-panel selection and reorder state."""

from __future__ import annotations


def sync_panel_selection(document, panel) -> None:
    """Synchronise the layers panel selection from the document layer stack."""
    sel_indices = document.layers.selected_indices
    panel.refresh(document)

    list_widget = panel._list
    list_widget.blockSignals(True)
    list_widget.clearSelection()
    row_ids = panel.row_layer_ids()

    active = document.layers.active_layer
    if active and active.id in row_ids:
        list_widget.setCurrentRow(row_ids.index(active.id))

    for selected_index in sel_indices:
        if 0 <= selected_index < len(document.layers.layers):
            layer_id = document.layers.layers[selected_index].id
            if layer_id in row_ids:
                row = row_ids.index(layer_id)
                item = list_widget.item(row)
                if item is not None:
                    item.setSelected(True)
    list_widget.blockSignals(False)


def selected_indices_from_layer_ids(layer_ids: list[str], stack_layers: list) -> set[int]:
    """Map selected layer IDs from the panel back to layer-stack indices."""
    new_selection: set[int] = set()
    for layer_id in layer_ids:
        for index, layer in enumerate(stack_layers):
            if layer.id == layer_id:
                new_selection.add(index)
                break
    return new_selection


def reordered_stack_order(display_ids: list[str], dragged_ids: list[str], target_visual_row: int) -> list[str]:
    """Convert a panel drag target into the corresponding stack order."""
    dragged_set = set(dragged_ids)
    above_count = 0
    for index, layer_id in enumerate(display_ids):
        if index >= target_visual_row:
            break
        if layer_id in dragged_set:
            above_count += 1

    remaining = [layer_id for layer_id in display_ids if layer_id not in dragged_set]
    adjusted_row = max(0, min(target_visual_row - above_count, len(remaining)))
    for index, layer_id in enumerate(dragged_ids):
        remaining.insert(adjusted_row + index, layer_id)
    return list(reversed(remaining))