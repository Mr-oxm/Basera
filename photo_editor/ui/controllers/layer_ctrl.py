"""Layer operations — add, delete, group, mask, reorder."""

from __future__ import annotations

import copy

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox

from ...commands import (
    AddGroupCommand,
    AddLayerCommand,
    AddMaskLayerCommand,
    ApplyMaskLayerCommand,
    AttachAdjustmentToLayerCommand,
    AttachMaskToLayerCommand,
    ConvertToMaskCommand,
    DuplicateLayerCommand,
    FlattenCommand,
    InvertMaskLayerCommand,
    MergeDownCommand,
    MoveLayerCommand,
    RemoveLayerCommand,
    RemoveMaskLayerCommand,
    RenameLayerCommand,
    ReorderLayersCommand,
)
from ...core.enums import BlendMode, LayerType, ToolType
from ..dialogs.layer_styles_dialog import LayerStylesDialog

PAINTING_TOOLS = {
    ToolType.BRUSH, ToolType.ERASER, ToolType.CLONE_STAMP,
    ToolType.HEALING_BRUSH, ToolType.GRADIENT, ToolType.PAINT_BUCKET,
}

NUMPAD_MAP = {
    Qt.Key.Key_0: 0, Qt.Key.Key_1: 1, Qt.Key.Key_2: 2,
    Qt.Key.Key_3: 3, Qt.Key.Key_4: 4, Qt.Key.Key_5: 5,
    Qt.Key.Key_6: 6, Qt.Key.Key_7: 7, Qt.Key.Key_8: 8,
    Qt.Key.Key_9: 9,
}


class LayerController:
    """Handles layer add/delete/group/mask/reorder and property changes."""

    def __init__(self) -> None:
        self._mw = None
        self._numpad_first: int | None = None
        self._numpad_timer: QTimer | None = None

    def wire(self, main_window) -> None:
        """Connect to main window and wire menu/panel signals."""
        self._mw = main_window
        mw = main_window

        # Menu
        a = mw._menu.actions_map
        a["new_layer"].triggered.connect(self.on_add_layer)
        a["new_vector_layer"].triggered.connect(self.on_add_vector_layer)
        a["new_group"].triggered.connect(self.on_add_group)
        a["dup_layer"].triggered.connect(self.on_dup_layer)
        a["del_layer"].triggered.connect(self.on_del_layer)
        a["add_mask"].triggered.connect(self.on_add_mask)
        a["add_mask_black"].triggered.connect(self.on_add_mask_black)
        a["add_mask_standalone"].triggered.connect(self.on_add_mask_standalone)
        a["remove_mask_layer"].triggered.connect(self.on_remove_mask_layer)
        a["apply_mask_layer"].triggered.connect(self.on_apply_mask_layer)
        a["invert_mask_layer"].triggered.connect(self.on_invert_mask_layer)
        a["convert_to_mask"].triggered.connect(self.on_convert_to_mask)
        a["toggle_vis"].triggered.connect(self.on_toggle_vis_selected)
        a["flatten"].triggered.connect(self.on_flatten)
        a["merge_down"].triggered.connect(self.on_merge_down)
        a["resize_canvas"].triggered.connect(self.on_resize_canvas)
        a["resize_image"].triggered.connect(self.on_resize_image)

        # Layers panel
        lp = mw._layers_panel
        lp.layer_selected.connect(self.on_layer_selected)
        lp.add_requested.connect(self.on_add_layer)
        lp.duplicate_requested.connect(self.on_dup_layer)
        lp.delete_requested.connect(self.on_del_layer)
        lp.group_requested.connect(self.on_add_group)
        lp.mask_requested.connect(self.on_add_mask)
        lp.styles_requested.connect(self.on_layer_styles)
        lp.opacity_changed.connect(self.on_opacity)
        lp.blend_mode_changed.connect(self.on_blend_mode)
        lp.blend_mode_hovered.connect(self.on_blend_hover)
        lp.blend_mode_hover_ended.connect(self.on_blend_hover_end)
        lp.visibility_toggled.connect(self.on_toggle_vis)
        lp.lock_toggled.connect(self.on_toggle_lock)
        lp.layers_reordered.connect(self.on_layers_reordered)
        lp.layers_reparented.connect(self.on_layers_reparented)
        lp.layers_unparented.connect(self.on_layers_unparented)
        lp.mask_dropped_on_layer.connect(self.on_mask_dropped_on_layer)
        lp.adj_filter_dropped_on_layer.connect(self.on_adj_filter_dropped_on_layer)
        lp.rename_requested.connect(self.on_rename_layer)
        lp.adjustment_layer_requested.connect(mw._filter_ctrl.on_add_adjustment_layer)
        lp.edit_adjustment_requested.connect(mw._filter_ctrl.on_edit_adjustment_layer)
        lp.filter_layer_requested.connect(mw._filter_ctrl.on_add_filter_layer)
        lp.edit_filter_requested.connect(mw._filter_ctrl.on_edit_filter_layer)
        lp.multi_selection_changed.connect(self.on_panel_multi_selection)

        # Move tool auto-select
        move_tool = mw._tools._tools.get(ToolType.MOVE)
        if move_tool is not None:
            move_tool.on_layer_auto_selected = self.on_move_auto_select
            move_tool.on_deselect_all = self.on_move_deselect_all
            move_tool.on_marquee_select = self.on_move_marquee_select

    def on_layer_styles(self) -> None:
        """Open the Layer Styles dialog for the active layer."""
        mw = self._mw
        if not mw._doc:
            return
        layer = mw._doc.layers.active_layer
        if not layer:
            return

        old_styles = copy.deepcopy(layer.styles)
        dlg = LayerStylesDialog(existing_styles=layer.styles, parent=mw)

        _connected_panels: set[str] = set()

        def _preview() -> None:
            layer._styles = dlg.get_styles()
            mw._refresh()
            _wire_panels()

        def _wire_panels() -> None:
            for key, panel in dlg._panels.items():
                if key not in _connected_panels:
                    panel.changed.connect(_preview)
                    _connected_panels.add(key)

        _wire_panels()

        def _accept(styles: list) -> None:
            layer._styles = list(styles)
            mw._doc.save_snapshot(f"Layer Style \u2013 {layer.name}")
            mw._refresh()

        def _reject() -> None:
            layer._styles = old_styles
            mw._refresh()

        dlg.styles_accepted.connect(_accept)
        dlg.rejected.connect(_reject)
        dlg.exec()

    def on_add_layer(self) -> None:
        if self._mw._doc:
            self._mw.execute_command(AddLayerCommand())

    def on_add_vector_layer(self) -> None:
        if self._mw._doc:
            self._mw._doc.add_vector_layer()
            self._mw._refresh()

    def on_add_group(self) -> None:
        if not self._mw._doc:
            return
        mw = self._mw
        selected = mw._layers_panel.selected_layer_ids()
        mw.execute_command(AddGroupCommand(layer_ids=selected if len(selected) >= 1 else None))

    def on_dup_layer(self) -> None:
        if not self._mw._doc or not self._mw._doc.layers.active_layer:
            return
        mw = self._mw
        if mw._doc.selection.active and mw._doc.selection.mask is not None:
            mw._selection_ctrl.on_duplicate_selection()
        else:
            mw.execute_command(DuplicateLayerCommand(mw._doc.layers.active_layer.id))

    def on_del_layer(self) -> None:
        if not self._mw._doc or len(self._mw._doc.layers) <= 1:
            return
        mw = self._mw
        selected = mw._layers_panel.selected_layer_ids()
        if selected:
            for lid in selected:
                if len(mw._doc.layers) <= 1:
                    break
                if mw._doc.layers.get(lid):
                    mw.execute_command(RemoveLayerCommand(lid))
        elif mw._doc.layers.active_layer:
            mw.execute_command(RemoveLayerCommand(mw._doc.layers.active_layer.id))

    def on_add_mask(self) -> None:
        mw = self._mw
        if mw._doc and mw._doc.layers.active_layer:
            if mw._doc.selection.active and mw._doc.selection.mask is not None:
                mw._doc.selection_to_mask_layer()
                mw._refresh()
            else:
                mw.execute_command(AddMaskLayerCommand(fill_white=True))

    def on_add_mask_black(self) -> None:
        if self._mw._doc and self._mw._doc.layers.active_layer:
            self._mw.execute_command(AddMaskLayerCommand(fill_white=False))

    def on_add_mask_standalone(self) -> None:
        if self._mw._doc:
            self._mw.execute_command(AddMaskLayerCommand(standalone=True))

    def on_remove_mask_layer(self) -> None:
        if not self._mw._doc:
            return
        active = self._mw._doc.layers.active_layer
        if active and active.layer_type == LayerType.MASK:
            self._mw.execute_command(RemoveMaskLayerCommand(active.id))

    def on_apply_mask_layer(self) -> None:
        if not self._mw._doc:
            return
        active = self._mw._doc.layers.active_layer
        if active and active.layer_type == LayerType.MASK:
            self._mw.execute_command(ApplyMaskLayerCommand(active.id))

    def on_invert_mask_layer(self) -> None:
        if not self._mw._doc:
            return
        active = self._mw._doc.layers.active_layer
        if active and active.layer_type == LayerType.MASK:
            self._mw.execute_command(InvertMaskLayerCommand(active.id))

    def on_convert_to_mask(self) -> None:
        if not self._mw._doc:
            return
        active = self._mw._doc.layers.active_layer
        if active and active.layer_type not in (LayerType.MASK, LayerType.GROUP):
            self._mw.execute_command(ConvertToMaskCommand(active.id))

    def on_layer_selected(self, stack_index: int) -> None:
        if self._mw._doc:
            self._mw._doc.layers.active_index = stack_index

            if self._mw._tools.active_type == ToolType.NODE:
                al = self._mw._doc.layers.active_layer
                if al:
                    vl = getattr(al, "_vector_data", None)
                    if vl and not vl.selected_objects() and vl.objects:
                        vl.objects[-1].selected = True
                        if hasattr(self._mw, "_canvas"):
                            self._mw._canvas.update()

            self._mw._transform_ctrl.update_transform_box()
            self._mw._transform_panel.refresh(self._mw._doc)
            self._mw._tool_ctrl.update_properties_panel()

    def on_move_auto_select(self, stack_index: int) -> None:
        if not self._mw._doc:
            return
        # Sync the layers panel selection with the model's multi-selection
        self._sync_panel_selection()
        self._mw._transform_panel.refresh(self._mw._doc)
        self._mw._transform_ctrl.update_transform_box()

    def _sync_panel_selection(self) -> None:
        """Synchronise the layers panel's visual selection with LayerStack."""
        mw = self._mw
        if not mw._doc:
            return
        sel_indices = mw._doc.layers.selected_indices
        panel = mw._layers_panel
        # Refresh first so rows are up to date
        panel.refresh(mw._doc)
        # Now select the correct rows
        lst = panel._list
        lst.blockSignals(True)
        lst.clearSelection()
        row_ids = panel.row_layer_ids()
        for si in sel_indices:
            if 0 <= si < len(mw._doc.layers.layers):
                lid = mw._doc.layers.layers[si].id
                if lid in row_ids:
                    row = row_ids.index(lid)
                    item = lst.item(row)
                    if item:
                        item.setSelected(True)
        # Set current row to the active layer
        active = mw._doc.layers.active_layer
        if active and active.id in row_ids:
            lst.setCurrentRow(row_ids.index(active.id))
        lst.blockSignals(False)

    def on_move_deselect_all(self) -> None:
        """Called when the Move tool clicks on empty canvas — deselect all."""
        mw = self._mw
        if not mw._doc:
            return
        mw._layers_panel.refresh(mw._doc)
        mw._transform_ctrl.update_transform_box()
        mw._canvas.update()

    def on_move_marquee_select(self, indices: list[int]) -> None:
        """Called after a marquee drag-select completes in the Move tool."""
        mw = self._mw
        if not mw._doc:
            return
        self._sync_panel_selection()
        mw._transform_ctrl.update_transform_box()
        mw._canvas.update()

    def on_panel_multi_selection(self, layer_ids: list) -> None:
        """Sync panel multi-selection back to LayerStack and update bbox."""
        mw = self._mw
        if not mw._doc:
            return
        stack = mw._doc.layers
        # Build a set of selected indices from the panel's selected IDs
        new_sel: set[int] = set()
        for lid in layer_ids:
            for i, layer in enumerate(stack.layers):
                if layer.id == lid:
                    new_sel.add(i)
                    break
        stack._selected_indices = new_sel
        # Keep active_index pointing at something sensible
        if new_sel and stack.active_index not in new_sel:
            stack._active_index = max(new_sel)
        elif not new_sel:
            stack._active_index = -1
        mw._transform_ctrl.update_transform_box()

    def on_opacity(self, val: float) -> None:
        if self._mw._doc and self._mw._doc.layers.active_layer:
            self._mw._doc.layers.active_layer.opacity = val
            self._mw._refresh_canvas_only()

    def on_blend_mode(self, mode: BlendMode) -> None:
        self._mw._blend_preview_original = None
        if self._mw._doc and self._mw._doc.layers.active_layer:
            self._mw._doc.layers.active_layer.blend_mode = mode
            self._mw._refresh_canvas_only()

    def on_blend_hover(self, mode: BlendMode) -> None:
        if not self._mw._doc or not self._mw._doc.layers.active_layer:
            return
        if self._mw._blend_preview_original is None:
            self._mw._blend_preview_original = (
                self._mw._doc.layers.active_layer.blend_mode
            )
        self._mw._doc.layers.active_layer.blend_mode = mode
        self._mw._refresh_canvas_only()

    def on_blend_hover_end(self) -> None:
        if not self._mw._doc or not self._mw._doc.layers.active_layer:
            return
        if self._mw._blend_preview_original is not None:
            self._mw._doc.layers.active_layer.blend_mode = (
                self._mw._blend_preview_original
            )
            self._mw._blend_preview_original = None
            self._mw._refresh_canvas_only()

    def on_toggle_vis(self, layer_id: str) -> None:
        if self._mw._doc:
            layer = self._mw._doc.layers.get(layer_id)
            if layer:
                layer.visible = not layer.visible
                self._mw._refresh_canvas_only()
                self._mw._layers_panel.refresh(self._mw._doc, thumbnails=False)

    def on_toggle_lock(self, layer_id: str) -> None:
        if self._mw._doc:
            layer = self._mw._doc.layers.get(layer_id)
            if layer:
                layer.locked = not layer.locked
                self._mw._layers_panel.refresh_controls_only(self._mw._doc)
                self._mw._transform_ctrl.update_transform_box()

    def on_toggle_vis_selected(self) -> None:
        self._mw._layers_panel.toggle_visibility_for_selected()

    def on_rename_layer(self, layer_id: str, new_name: str) -> None:
        if self._mw._doc:
            self._mw.execute_command(RenameLayerCommand(layer_id, new_name))

    def on_layers_reordered(self, layer_ids: list[str], target_visual_row: int) -> None:
        if not self._mw._doc:
            return
        mw = self._mw
        display_ids = mw._layers_panel.row_layer_ids()
        drag_set = set(layer_ids)
        above_count = 0
        for i, lid in enumerate(display_ids):
            if i >= target_visual_row:
                break
            if lid in drag_set:
                above_count += 1
        remaining = [lid for lid in display_ids if lid not in drag_set]
        adjusted_row = max(0, min(target_visual_row - above_count, len(remaining)))
        for i, lid in enumerate(layer_ids):
            remaining.insert(adjusted_row + i, lid)
        new_stack_order = list(reversed(remaining))
        mw.execute_command(ReorderLayersCommand(new_stack_order))

    def on_layers_reparented(self, layer_ids: list[str], group_id: str) -> None:
        if not self._mw._doc:
            return
        self._mw.execute_command(MoveLayerCommand(layer_ids, target_parent_id=group_id))

    def on_layers_unparented(self, layer_ids: list[str]) -> None:
        if not self._mw._doc:
            return
        self._mw.execute_command(MoveLayerCommand(layer_ids, target_parent_id=None))

    def on_mask_dropped_on_layer(self, mask_id: str, target_id: str) -> None:
        if not self._mw._doc:
            return
        self._mw.execute_command(AttachMaskToLayerCommand(mask_id, target_id))

    def on_adj_filter_dropped_on_layer(self, adj_id: str, target_id: str) -> None:
        if not self._mw._doc:
            return
        self._mw.execute_command(AttachAdjustmentToLayerCommand(adj_id, target_id))

    def on_flatten(self) -> None:
        if self._mw._doc:
            self._mw.execute_command(FlattenCommand())

    def on_merge_down(self) -> None:
        if self._mw._doc:
            success = self._mw.execute_command(MergeDownCommand())
            if success is False:
                self._mw.statusBar().showMessage(
                    "Cannot merge down — no suitable layer below", 3000
                )

    def on_resize_canvas(self) -> None:
        if not self._mw._doc:
            return
        from ..dialogs.new_document import NewDocumentDialog
        dlg = NewDocumentDialog(self._mw)
        dlg.setWindowTitle("Canvas Size")
        dlg._width.setValue(self._mw._doc.width)
        dlg._height.setValue(self._mw._doc.height)
        if dlg.exec():
            w, h, _ = dlg.get_values()
            if w > 0 and h > 0:
                self._mw._doc._snapshot("Resize Canvas")
                self._mw._doc.resize(w, h)
                self._mw._refresh()

    def needs_rasterize_warning(self) -> bool:
        """Return True if the active tool would paint on a text layer."""
        mw = self._mw
        if mw._tools.active_type not in PAINTING_TOOLS:
            return False
        layer = mw._doc.layers.active_layer
        return layer is not None and layer.layer_type == LayerType.TEXT

    def ask_rasterize(self) -> bool:
        """Show a rasterization dialog. Return True if user accepted."""
        mw = self._mw
        reply = QMessageBox.warning(
            mw,
            "Rasterize Text Layer",
            "This type layer must be rasterized before it can be modified "
            "with this tool.  Once rasterized, the text will no longer be "
            "editable.\n\nRasterize the layer?",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Ok:
            self.rasterize_active_layer()
            return True
        return False

    def rasterize_active_layer(self) -> None:
        """Convert the active text layer into a plain raster layer."""
        mw = self._mw
        layer = mw._doc.layers.active_layer
        if layer is None:
            return
        mw._doc.save_snapshot("Rasterize Text")
        layer.layer_type = LayerType.RASTER
        if hasattr(layer, "_text_data"):
            try:
                del layer._text_data
            except AttributeError:
                layer._text_data = None
        layer.rasterize_transform()
        mw._refresh()

    def handle_numpad_opacity(self, key: int) -> bool:
        """Process a numpad digit for opacity. Returns True if consumed."""
        mw = self._mw
        digit = NUMPAD_MAP.get(key)
        if digit is None:
            return False
        if not mw._doc or not mw._doc.layers.active_layer:
            return False

        if self._numpad_timer is None:
            self._numpad_timer = QTimer(mw)
            self._numpad_timer.setSingleShot(True)
            self._numpad_timer.setInterval(500)
            self._numpad_timer.timeout.connect(self._numpad_commit)

        if self._numpad_first is not None:
            pct = self._numpad_first * 10 + digit
            pct = max(0, min(100, pct))
            self._numpad_first = None
            self._numpad_timer.stop()
            self._set_opacity_pct(pct)
            return True
        self._numpad_first = digit
        self._numpad_timer.start()
        return True

    def _numpad_commit(self) -> None:
        if self._numpad_first is not None:
            d = self._numpad_first
            pct = 100 if d == 0 else d * 10
            self._numpad_first = None
            self._set_opacity_pct(pct)

    def _set_opacity_pct(self, pct: int) -> None:
        mw = self._mw
        if mw._doc and mw._doc.layers.active_layer:
            mw._doc.layers.active_layer.opacity = pct / 100.0
            mw._layers_panel.refresh_controls_only(mw._doc)
            mw._refresh_canvas_only()
            mw.statusBar().showMessage(f"Opacity: {pct}%", 1500)

    def on_resize_image(self) -> None:
        if not self._mw._doc:
            return
        mw = self._mw
        from ..dialogs.new_document import NewDocumentDialog
        dlg = NewDocumentDialog(mw)
        dlg.setWindowTitle("Image Size")
        dlg._width.setValue(mw._doc.width)
        dlg._height.setValue(mw._doc.height)
        if dlg.exec():
            import cv2
            new_w, new_h, _ = dlg.get_values()
            if new_w < 1 or new_h < 1:
                return
            sx = new_w / max(mw._doc.width, 1)
            sy = new_h / max(mw._doc.height, 1)
            mw._doc._snapshot("Resize Image")
            for layer in mw._doc.layers.layers:
                px = layer.pixels
                lh, lw = px.shape[:2]
                nlw, nlh = max(1, round(lw * sx)), max(1, round(lh * sy))
                layer._pixels = cv2.resize(px, (nlw, nlh), interpolation=cv2.INTER_AREA)
                layer.width, layer.height = nlw, nlh
                ox, oy = layer.position
                layer.position = (round(ox * sx), round(oy * sy))
            mw._doc.resize(new_w, new_h)
            mw._refresh()
