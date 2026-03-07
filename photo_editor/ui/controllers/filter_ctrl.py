"""Adjustment and filter layer creation, editing, and menu filters."""

from __future__ import annotations

from ...commands import UpdateEffectCommand
from ...core.enums import LayerType
from ...processors import ImageProcessor
from ...registries import get_adjustment_class, get_filter_class, get_filter_name_map
from .base import ControllerBase
from ..filter_runner import run_adjustment, run_filter


class FilterController(ControllerBase):
    """Handles adjustment/filter layer add/edit and menu filter application."""

    def __init__(self) -> None:
        super().__init__()

    def wire(self, main_window) -> None:
        super().wire(main_window)
        mw = main_window

        # Menu: filter_* actions (Blur, Sharpen, etc.)
        a = mw._menu.actions_map
        for key, action in a.items():
            if key.startswith("filter_"):
                fkey = key[len("filter_"):]
                action.triggered.connect(lambda checked, k=fkey: self.on_menu_filter(k))

    def preview_render(self) -> None:
        """Re-render the canvas for a live filter/adjustment preview (async)."""
        doc = self.doc
        if doc is None:
            return
        active = doc.layers.active_layer
        if active:
            self.ctx.invalidate(active.id)
        else:
            self.ctx.invalidate()
        self.ctx.schedule_render()

    def on_adjustment(self, name: str) -> None:
        """Apply adjustment directly (destructive)."""
        if self.doc and run_adjustment(name, self.doc, self.mw, preview_fn=self.preview_render):
            self.ctx.refresh()

    def on_add_adjustment_layer(self, name: str) -> None:
        """Create a new adjustment layer for the given adjustment *name*."""
        adj_cls = get_adjustment_class(name)
        if adj_cls is None:
            return
        self._add_processor_layer(adj_cls(), LayerType.ADJUSTMENT)

    def on_edit_adjustment_layer(self, layer_id: str) -> None:
        """Open a dialog to edit an existing adjustment layer's parameters."""
        self._edit_processor_layer(layer_id, LayerType.ADJUSTMENT)

    def on_add_filter_layer(self, display_name: str) -> None:
        """Create a new filter layer for the given filter display name."""
        fmap = get_filter_name_map()
        filt_cls = fmap.get(display_name)
        if filt_cls is None:
            return
        self._add_processor_layer(filt_cls(), LayerType.FILTER)

    def on_edit_filter_layer(self, layer_id: str) -> None:
        """Open a dialog to edit an existing filter layer's parameters."""
        self._edit_processor_layer(layer_id, LayerType.FILTER)

    def _add_processor_layer(self, processor: ImageProcessor, layer_type: LayerType) -> None:
        doc = self.doc
        if doc is None:
            return
        # Capture the previously-active layer BEFORE add_layer(), because
        # add_layer() makes the new layer active, which would cause
        # _attach_to_active_parent to see the adj/filter layer itself and
        # bail out on the "parent is ADJUSTMENT/FILTER" guard.
        prev_active = doc.layers.active_layer
        layer = doc.add_layer(name=processor.name, layer_type=layer_type)
        layer.adjustment = processor
        layer.adjustment_params = dict(processor.default_params)
        self._attach_to_parent(layer.id, layer_type, prev_active)
        self.ctx.refresh()
        if processor.default_params:
            self._edit_processor_layer(layer.id, layer_type)

    def _attach_to_parent(self, layer_id: str, layer_type: LayerType, prev_active) -> None:
        """Parent *layer_id* to the nearest suitable ancestor of *prev_active*.

        *prev_active* must be captured before the new layer was added to the
        stack, so it refers to the layer that was active prior to creation.
        Does nothing when there is no suitable parent (leaves layer at root).
        """
        doc = self.doc
        if doc is None or prev_active is None:
            return
        parent = prev_active
        if prev_active.parent_id:
            resolved_parent = doc.layers.get(prev_active.parent_id)
            if resolved_parent is not None:
                parent = resolved_parent
        if parent.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER, LayerType.MASK):
            return
        layer = doc.layers.get(layer_id)
        if layer is None or layer.layer_type != layer_type:
            return
        layer.parent_id = parent.id
        doc.layers.reposition_before(layer.id, parent.id)

    def _attach_to_active_parent(self, layer_id: str, layer_type: LayerType) -> None:
        """Legacy wrapper — prefer capturing prev_active before add_layer."""
        doc = self.doc
        if doc is None:
            return
        self._attach_to_parent(layer_id, layer_type, doc.layers.active_layer)

    def _edit_processor_layer(self, layer_id: str, layer_type: LayerType) -> None:
        doc = self.doc
        if doc is None:
            return
        layer = doc.layers.get(layer_id)
        if layer is None or layer.layer_type != layer_type:
            return
        processor = layer.adjustment
        if processor is None or not processor.default_params:
            return

        from ..dialogs.filter_dialog import FilterDialog

        current_params = dict(layer.adjustment_params) if layer.adjustment_params else dict(processor.default_params)
        dlg = FilterDialog(self._dialog_title(layer_type, processor.name), current_params, parent=self.mw)

        def _on_preview(params: dict) -> None:
            layer.adjustment_params = params
            self.ctx.schedule_render()

        dlg.params_changed.connect(_on_preview)
        _on_preview(current_params)

        old_params = dict(current_params)
        if dlg.exec():
            self.ctx.execute_command(UpdateEffectCommand(layer.id, dlg.get_params()))
        else:
            layer.adjustment_params = old_params
            self.ctx.invalidate()
            self.ctx.refresh()

    @staticmethod
    def _dialog_title(layer_type: LayerType, processor_name: str) -> str:
        kind = "Adjustment" if layer_type == LayerType.ADJUSTMENT else "Filter"
        return f"{kind} — {processor_name}"

    def on_menu_filter(self, key: str) -> None:
        """Menu bar filter entry — create a filter layer by internal key."""
        if self.doc is None:
            return
        filt_cls = get_filter_class(key)
        if filt_cls is None:
            return
        filt = filt_cls()
        self.on_add_filter_layer(filt.name)

    def on_filter(self, key: str) -> None:
        """Apply filter directly (destructive)."""
        if self.doc and run_filter(key, self.doc, self.mw, preview_fn=self.preview_render):
            self.ctx.refresh()
