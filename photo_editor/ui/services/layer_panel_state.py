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
    """Convert a panel drag target into the corresponding stack order.

    Separator markers (``__sep__``) in *display_ids* are stripped before
    computing the insertion position so they don't shift the result.
    The *target_visual_row* is a raw row index into the panel list
    (including separators); it is automatically adjusted to account
    for any separators above it.
    """
    # Build a mapping from raw row → real-layer-only row, and count
    # separators above the target so we can adjust the insertion point.
    seps_above = 0
    for idx in range(min(target_visual_row, len(display_ids))):
        if display_ids[idx] == "__sep__":
            seps_above += 1

    # Work only with real layer IDs (drop separators).
    real_ids = [lid for lid in display_ids if lid != "__sep__"]
    adjusted_target = target_visual_row - seps_above

    dragged_set = set(dragged_ids)
    above_count = 0
    for index, layer_id in enumerate(real_ids):
        if index >= adjusted_target:
            break
        if layer_id in dragged_set:
            above_count += 1

    remaining = [layer_id for layer_id in real_ids if layer_id not in dragged_set]
    insert_at = max(0, min(adjusted_target - above_count, len(remaining)))
    for i, layer_id in enumerate(dragged_ids):
        remaining.insert(insert_at + i, layer_id)
    return list(reversed(remaining))