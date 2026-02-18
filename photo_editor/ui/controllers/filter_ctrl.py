"""Adjustment and filter layer creation, editing, and menu filters."""

from __future__ import annotations

from ...commands import UpdateEffectCommand
from ...core.enums import LayerType
from ..filter_runner import _adj_map, _filter_name_map, _filter_map, run_adjustment, run_filter


class FilterController:
    """Handles adjustment/filter layer add/edit and menu filter application."""

    def __init__(self) -> None:
        self._mw = None

    def preview_render(self) -> None:
        """Re-render the canvas for a live filter/adjustment preview (async)."""
        mw = self._mw
        if not mw._doc:
            return
        active = mw._doc.layers.active_layer
        if active:
            mw._pipeline.invalidate(active.id)
        else:
            mw._pipeline.invalidate()
        mw._schedule_render()

    def wire(self, main_window) -> None:
        """Connect to main window and wire menu signals."""
        self._mw = main_window
        mw = main_window

        # Menu: filter_* actions (Blur, Sharpen, etc.)
        a = mw._menu.actions_map
        for key, action in a.items():
            if key.startswith("filter_"):
                fkey = key[len("filter_"):]
                action.triggered.connect(lambda checked, k=fkey: self.on_menu_filter(k))

    def on_adjustment(self, name: str) -> None:
        """Apply adjustment directly (destructive)."""
        mw = self._mw
        if mw._doc and run_adjustment(name, mw._doc, mw, preview_fn=self.preview_render):
            mw._refresh()

    def on_add_adjustment_layer(self, name: str) -> None:
        """Create a new adjustment layer for the given adjustment *name*."""
        mw = self._mw
        if not mw._doc:
            return
        adj_cls = _adj_map().get(name)
        if adj_cls is None:
            return
        adj = adj_cls()
        prev_active = mw._doc.layers.active_layer
        layer = mw._doc.add_layer(name=name, layer_type=LayerType.ADJUSTMENT)
        layer.adjustment = adj
        layer.adjustment_params = dict(adj.default_params)
        if prev_active is not None:
            parent = prev_active
            if prev_active.parent_id:
                p = mw._doc.layers.get(prev_active.parent_id)
                if p:
                    parent = p
            if parent.layer_type not in (LayerType.ADJUSTMENT, LayerType.FILTER, LayerType.MASK):
                layer.parent_id = parent.id
                mw._doc.layers.reposition_before(layer.id, parent.id)
        mw._refresh()
        if adj.default_params:
            self.on_edit_adjustment_layer(layer.id)

    def on_edit_adjustment_layer(self, layer_id: str) -> None:
        """Open a dialog to edit an existing adjustment layer's parameters."""
        mw = self._mw
        if not mw._doc:
            return
        layer = mw._doc.layers.get(layer_id)
        if layer is None or layer.layer_type != LayerType.ADJUSTMENT:
            return
        adj = layer.adjustment
        if adj is None or not adj.default_params:
            return

        from ..dialogs.filter_dialog import FilterDialog

        current_params = dict(layer.adjustment_params) if layer.adjustment_params else dict(adj.default_params)
        dlg = FilterDialog(f"Adjustment — {adj.name}", current_params, parent=mw)

        def _on_preview(params: dict) -> None:
            layer.adjustment_params = params
            mw._schedule_render()

        dlg.params_changed.connect(_on_preview)
        _on_preview(current_params)

        old_params = dict(current_params)
        if dlg.exec():
            mw.execute_command(UpdateEffectCommand(layer.id, dlg.get_params()))
        else:
            layer.adjustment_params = old_params
            mw._pipeline.invalidate()
            mw._refresh()

    def on_add_filter_layer(self, display_name: str) -> None:
        """Create a new filter layer for the given filter display name."""
        mw = self._mw
        if not mw._doc:
            return
        fmap = _filter_name_map()
        filt_cls = fmap.get(display_name)
        if filt_cls is None:
            return
        filt = filt_cls()
        prev_active = mw._doc.layers.active_layer
        layer = mw._doc.add_layer(name=display_name, layer_type=LayerType.FILTER)
        layer.adjustment = filt
        layer.adjustment_params = dict(filt.default_params)
        if prev_active is not None:
            parent = prev_active
            if prev_active.parent_id:
                p = mw._doc.layers.get(prev_active.parent_id)
                if p:
                    parent = p
            if parent.layer_type not in (LayerType.ADJUSTMENT, LayerType.FILTER, LayerType.MASK):
                layer.parent_id = parent.id
                mw._doc.layers.reposition_before(layer.id, parent.id)
        mw._refresh()
        if filt.default_params:
            self.on_edit_filter_layer(layer.id)

    def on_edit_filter_layer(self, layer_id: str) -> None:
        """Open a dialog to edit an existing filter layer's parameters."""
        mw = self._mw
        if not mw._doc:
            return
        layer = mw._doc.layers.get(layer_id)
        if layer is None or layer.layer_type != LayerType.FILTER:
            return
        filt = layer.adjustment
        if filt is None or not filt.default_params:
            return

        from ..dialogs.filter_dialog import FilterDialog

        current_params = dict(layer.adjustment_params) if layer.adjustment_params else dict(filt.default_params)
        dlg = FilterDialog(f"Filter — {filt.name}", current_params, parent=mw)

        def _on_preview(params: dict) -> None:
            layer.adjustment_params = params
            mw._schedule_render()

        dlg.params_changed.connect(_on_preview)
        _on_preview(current_params)

        old_params = dict(current_params)
        if dlg.exec():
            mw.execute_command(UpdateEffectCommand(layer.id, dlg.get_params()))
        else:
            layer.adjustment_params = old_params
            mw._pipeline.invalidate()
            mw._refresh()

    def on_menu_filter(self, key: str) -> None:
        """Menu bar filter entry — create a filter layer by internal key."""
        mw = self._mw
        if not mw._doc:
            return
        filt_cls = _filter_map().get(key)
        if filt_cls is None:
            return
        filt = filt_cls()
        self.on_add_filter_layer(filt.name)

    def on_filter(self, key: str) -> None:
        """Apply filter directly (destructive)."""
        mw = self._mw
        if mw._doc and run_filter(key, mw._doc, mw, preview_fn=self.preview_render):
            mw._refresh()
