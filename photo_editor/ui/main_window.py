"""Main application window — assembles all panels, menus, and canvas."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QDockWidget, QFileDialog, QInputDialog, QMainWindow, QMessageBox,
)

from ..core.document import Document
from ..core.enums import BlendMode, LayerType, ToolType
from ..engine.render_pipeline import RenderPipeline
from ..transforms.transform_engine import TransformEngine
from ..utils.image_io import load_image, save_image
from .canvas_view import CanvasView
from .dialogs.new_document import NewDocumentDialog
from .filter_runner import run_adjustment, run_filter
from .menus import EditorMenuBar
from .panels.adjustments_panel import AdjustmentsPanel
from .panels.color_panel import ColorPanel
from .panels.history_panel import HistoryPanel
from .panels.layers_panel import LayersPanel
from .panels.properties_panel import PropertiesPanel
from .status_bar import EditorStatusBar
from .theme import DARK_STYLESHEET
from .tool_manager import ToolManager
from .toolbar import EditorToolbar

_IMG_FLT = "Images (*.png *.jpg *.jpeg *.webp *.tiff *.tif *.bmp)"


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Photo Editor")
        self.resize(1440, 900)
        self.setStyleSheet(DARK_STYLESHEET)
        self.setAcceptDrops(True)

        self._doc: Document | None = None
        self._pipeline = RenderPipeline()
        self._tools = ToolManager()

        # Blend-mode hover preview state
        self._blend_preview_original: BlendMode | None = None

        # Render throttle — max ~30 fps during drag
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(33)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._do_deferred_render)
        self._render_pending = False
        self._dragging = False

        self._build_ui()
        self._wire_menus()
        self._wire_panels()
        self._wire_canvas()
        self._new_document(1920, 1080)

    # ---- UI assembly --------------------------------------------------------

    def _build_ui(self) -> None:
        from PySide6.QtWidgets import QWidget, QVBoxLayout
        
        self._menu = EditorMenuBar(self)
        self.setMenuBar(self._menu)
        self._toolbar = EditorToolbar(self)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._toolbar)
        
        # Create horizontal properties panel (not docked)
        self._props_panel = PropertiesPanel()
        
        # Create a central widget with vertical layout: properties panel + canvas
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        
        # Add properties panel at top
        central_layout.addWidget(self._props_panel)
        
        # Add canvas below
        self._canvas = CanvasView(self)
        central_layout.addWidget(self._canvas)
        
        self.setCentralWidget(central)
        
        # Dock panels on the sides
        self._layers_panel = LayersPanel()
        self._dock(self._layers_panel, "Layers", Qt.DockWidgetArea.RightDockWidgetArea)
        self._history_panel = HistoryPanel()
        self._dock(self._history_panel, "History", Qt.DockWidgetArea.RightDockWidgetArea)
        self._adj_panel = AdjustmentsPanel()
        self._dock(self._adj_panel, "Adjustments", Qt.DockWidgetArea.RightDockWidgetArea)
        self._color_panel = ColorPanel()
        self._dock(self._color_panel, "Color", Qt.DockWidgetArea.LeftDockWidgetArea)
        self._status = EditorStatusBar(self)
        self.setStatusBar(self._status)

    def _dock(self, widget, title: str, area) -> None:
        d = QDockWidget(title, self)
        d.setWidget(widget)
        self.addDockWidget(area, d)

    # ---- Wiring: menus ------------------------------------------------------

    def _wire_menus(self) -> None:
        a = self._menu.actions_map
        a["new"].triggered.connect(self._on_new)
        a["open"].triggered.connect(self._on_open)
        a["place_image"].triggered.connect(self._on_place_image)
        a["save"].triggered.connect(self._on_save)
        a["save_as"].triggered.connect(self._on_save_as)
        a["export"].triggered.connect(self._on_save_as)
        a["quit"].triggered.connect(self.close)
        a["undo"].triggered.connect(self._on_undo)
        a["redo"].triggered.connect(self._on_redo)
        a["flip_h"].triggered.connect(lambda: self._transform("flip_h"))
        a["flip_v"].triggered.connect(lambda: self._transform("flip_v"))
        a["rotate_cw"].triggered.connect(lambda: self._transform("rotate_cw"))
        a["rotate_ccw"].triggered.connect(lambda: self._transform("rotate_ccw"))
        a["new_layer"].triggered.connect(self._on_add_layer)
        a["new_group"].triggered.connect(self._on_add_group)
        a["dup_layer"].triggered.connect(self._on_dup_layer)
        a["del_layer"].triggered.connect(self._on_del_layer)
        a["add_mask"].triggered.connect(self._on_add_mask)
        a["toggle_vis"].triggered.connect(self._on_toggle_vis_selected)
        a["flatten"].triggered.connect(self._on_flatten)
        a["select_all"].triggered.connect(self._on_select_all)
        a["deselect"].triggered.connect(self._on_deselect)
        a["invert_sel"].triggered.connect(self._on_invert_sel)
        a["zoom_in"].triggered.connect(lambda: self._zoom(1.25))
        a["zoom_out"].triggered.connect(lambda: self._zoom(1 / 1.25))
        a["zoom_fit"].triggered.connect(self._canvas.zoom_to_fit)
        a["zoom_100"].triggered.connect(lambda: self._canvas.set_zoom(1.0))
        for key, action in a.items():
            if key.startswith("filter_"):
                fkey = key[len("filter_"):]
                action.triggered.connect(lambda checked, k=fkey: self._on_filter(k))

    # ---- Wiring: panels -----------------------------------------------------

    def _wire_panels(self) -> None:
        self._toolbar.tool_selected.connect(self._on_tool_selected)
        lp = self._layers_panel
        lp.layer_selected.connect(self._on_layer_selected)
        lp.add_requested.connect(self._on_add_layer)
        lp.duplicate_requested.connect(self._on_dup_layer)
        lp.delete_requested.connect(self._on_del_layer)
        lp.group_requested.connect(self._on_add_group)
        lp.mask_requested.connect(self._on_add_mask)
        lp.opacity_changed.connect(self._on_opacity)
        lp.blend_mode_changed.connect(self._on_blend_mode)
        lp.blend_mode_hovered.connect(self._on_blend_hover)
        lp.blend_mode_hover_ended.connect(self._on_blend_hover_end)
        lp.visibility_toggled.connect(self._on_toggle_vis)
        lp.lock_toggled.connect(self._on_toggle_lock)
        lp.layers_reordered.connect(self._on_layers_reordered)
        lp.layers_reparented.connect(self._on_layers_reparented)
        lp.rename_requested.connect(self._on_rename_layer)
        self._history_panel.state_selected.connect(self._on_history_jump)
        self._adj_panel.adjustment_requested.connect(self._on_adjustment)
        self._color_panel.fg_changed.connect(self._on_fg_color_changed)
        self._props_panel.value_changed.connect(self._on_prop_changed)
        self._props_panel.text_property_changed.connect(self._on_text_prop_changed)

    # ---- Wiring: canvas -----------------------------------------------------

    def _wire_canvas(self) -> None:
        self._canvas.cursor_moved.connect(self._status.set_cursor_pos)
        self._canvas.cursor_moved.connect(self._on_canvas_hover)
        self._canvas.tool_pressed.connect(self._on_canvas_press)
        self._canvas.tool_moved.connect(self._on_canvas_move)
        self._canvas.tool_released.connect(self._on_canvas_release)

    # ---- Document lifecycle -------------------------------------------------

    def _new_document(self, w: int, h: int, dpi: int = 72) -> None:
        self._doc = Document(w, h)
        self._doc.dpi = dpi
        self._refresh()
        self._canvas.zoom_to_fit()
        self._status.set_document_info(self._doc.name, w, h)

    def _refresh(self, invalidate: bool = True) -> None:
        """Full UI refresh.

        Parameters
        ----------
        invalidate : bool
            If *True* (default), the render cache is marked stale so the
            composite is recomputed.  Pass *False* for operations that
            only change non-pixel state (layer selection, panel sync)
            to skip expensive recompositing.
        """
        if not self._doc:
            return
        if invalidate:
            self._pipeline.invalidate()
        result = self._pipeline.execute_to_uint8(self._doc)
        self._canvas.set_image(result)
        self._layers_panel.refresh(self._doc)
        self._history_panel.refresh(self._doc.history)
        self._update_selection_overlay()
        self._update_transform_box()

    def _refresh_canvas_only(self) -> None:
        """Re-render and update canvas only (skip panel updates)."""
        if not self._doc:
            return
        self._pipeline.invalidate()
        result = self._pipeline.execute_to_uint8(self._doc)
        self._canvas.set_image(result)
        self._update_transform_box()

    def _schedule_render(self) -> None:
        """Request a deferred render (throttled to ~30fps)."""
        if not self._render_pending:
            self._render_pending = True
            self._render_timer.start()

    def _do_deferred_render(self) -> None:
        """Timer callback — perform the actual canvas render."""
        self._render_pending = False
        self._refresh_canvas_only()

    def _update_selection_overlay(self) -> None:
        if self._doc and self._doc.selection._mask is not None:
            if self._doc.selection._mask.max() > 0:
                self._canvas.set_selection_mask(self._doc.selection._mask)
                return
        self._canvas.set_selection_mask(None)

    def _update_transform_box(self) -> None:
        """Show transform bounding box when the Move tool is active."""
        if self._tools.active_type == ToolType.MOVE and self._doc:
            layer = self._doc.layers.active_layer
            if layer:
                # For groups, compute bounding box from children
                if layer.layer_type == LayerType.GROUP:
                    box = self._group_bbox(layer)
                    if box:
                        self._canvas.set_transform_box(box)
                    else:
                        self._canvas.set_transform_box(None)
                    return

                tool = self._tools.active_tool
                # Ask the tool for rotation info (includes mid-drag angle).
                info = None
                if hasattr(tool, "rotation_info_for"):
                    info = tool.rotation_info_for(layer)
                if info is not None:
                    bw, bh, angle = info
                    lx, ly = layer.position
                    cx = lx + layer.width / 2
                    cy = ly + layer.height / 2
                    box = (int(cx - bw / 2), int(cy - bh / 2), bw, bh)
                    self._canvas.set_transform_box(box, angle)
                    return
                # Fall back: check the layer's own stored rotation
                if layer.transform_angle != 0.0 and layer.transform_base_w > 0:
                    bw = layer.transform_base_w
                    bh = layer.transform_base_h
                    lx, ly = layer.position
                    cx = lx + layer.width / 2
                    cy = ly + layer.height / 2
                    box = (int(cx - bw / 2), int(cy - bh / 2), bw, bh)
                    self._canvas.set_transform_box(box, layer.transform_angle)
                    return
                lx, ly = layer.position
                self._canvas.set_transform_box((lx, ly, layer.width, layer.height))
                return
        self._canvas.set_transform_box(None)

    def _group_bbox(self, group) -> tuple[int, int, int, int] | None:
        """Compute bounding box for a group from its children."""
        min_x, min_y = float("inf"), float("inf")
        max_x, max_y = float("-inf"), float("-inf")
        found = False
        for child in self._doc.layers:
            if child.parent_id != group.id:
                continue
            cx, cy = child.position
            min_x = min(min_x, cx)
            min_y = min(min_y, cy)
            max_x = max(max_x, cx + child.width)
            max_y = max(max_y, cy + child.height)
            found = True
        if not found:
            return None
        return (int(min_x), int(min_y), int(max_x - min_x), int(max_y - min_y))

    # ---- File menu handlers -------------------------------------------------

    def _on_new(self) -> None:
        dlg = NewDocumentDialog(self)
        if dlg.exec():
            self._new_document(*dlg.get_values())

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Image", "", _IMG_FLT)
        if not path:
            return
        img = load_image(path)
        h, w = img.shape[:2]
        self._doc = Document(w, h, name=Path(path).stem)
        self._doc.file_path = path
        self._doc.layers[0].pixels = img
        # First history entry captures the loaded image so undo never
        # goes back to a blank canvas.
        self._doc.save_snapshot("Open Image")
        self._refresh()
        self._canvas.zoom_to_fit()
        self._status.set_document_info(self._doc.name, w, h)

    def _on_place_image(self) -> None:
        if not self._doc:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Place Image as Layer", "", _IMG_FLT)
        if path:
            img = load_image(path)
            self._doc.place_image(img, name=Path(path).stem)
            self._refresh()

    def _on_save(self) -> None:
        if self._doc and self._doc.file_path:
            self._save_to(self._doc.file_path)
        else:
            self._on_save_as()

    def _on_save_as(self) -> None:
        if not self._doc:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save As", "", _IMG_FLT)
        if path:
            self._doc.file_path = path
            self._save_to(path)

    def _save_to(self, path: str) -> None:
        if self._doc:
            save_image(self._pipeline.execute(self._doc), path)
            self._doc.mark_clean()
            self.setWindowTitle(f"Photo Editor — {Path(path).name}")

    # ---- History ------------------------------------------------------------

    def _on_undo(self) -> None:
        if self._doc:
            self._doc.undo()
            self._refresh()

    def _on_redo(self) -> None:
        if self._doc:
            self._doc.redo()
            self._refresh()

    def _on_history_jump(self, index: int) -> None:
        if self._doc:
            self._doc.navigate_history(index)
            self._refresh()

    # ---- Layer ops ----------------------------------------------------------

    def _on_add_layer(self) -> None:
        if self._doc:
            self._doc.add_layer()
            self._refresh()

    def _on_add_group(self) -> None:
        if not self._doc:
            return
        selected = self._layers_panel.selected_layer_ids()
        if len(selected) > 1:
            # Group the selected layers into a new group
            self._doc.group_selected_layers(selected)
        else:
            self._doc.add_group()
        self._refresh()

    def _on_dup_layer(self) -> None:
        if self._doc and self._doc.layers.active_layer:
            self._doc.duplicate_layer(self._doc.layers.active_layer.id)
            self._refresh()

    def _on_del_layer(self) -> None:
        if self._doc and self._doc.layers.active_layer and len(self._doc.layers) > 1:
            self._doc.remove_layer(self._doc.layers.active_layer.id)
            self._refresh()

    def _on_add_mask(self) -> None:
        if self._doc and self._doc.layers.active_layer:
            self._doc.layers.active_layer.add_mask(fill_white=True)
            self._doc.save_snapshot("Add Mask")
            self._refresh()

    def _on_layer_selected(self, stack_index: int) -> None:
        if self._doc:
            self._doc.layers.active_index = stack_index
            self._update_transform_box()

    def _on_opacity(self, val: float) -> None:
        if self._doc and self._doc.layers.active_layer:
            self._doc.layers.active_layer.opacity = val
            self._refresh_canvas_only()

    def _on_blend_mode(self, mode: BlendMode) -> None:
        # Clear hover-preview state — the user committed a selection.
        self._blend_preview_original = None
        if self._doc and self._doc.layers.active_layer:
            self._doc.layers.active_layer.blend_mode = mode
            self._refresh_canvas_only()

    def _on_blend_hover(self, mode: BlendMode) -> None:
        """Temporarily preview a blend mode while hovering in the dropdown."""
        if not self._doc or not self._doc.layers.active_layer:
            return
        if self._blend_preview_original is None:
            self._blend_preview_original = self._doc.layers.active_layer.blend_mode
        self._doc.layers.active_layer.blend_mode = mode
        self._refresh_canvas_only()

    def _on_blend_hover_end(self) -> None:
        """Restore the original blend mode when the dropdown is dismissed."""
        if not self._doc or not self._doc.layers.active_layer:
            return
        if self._blend_preview_original is not None:
            self._doc.layers.active_layer.blend_mode = self._blend_preview_original
            self._blend_preview_original = None
            self._refresh_canvas_only()

    def _on_toggle_vis(self, layer_id: str) -> None:
        if self._doc:
            layer = self._doc.layers.get(layer_id)
            if layer:
                layer.visible = not layer.visible
                self._refresh_canvas_only()
                self._layers_panel.refresh(self._doc)

    def _on_toggle_lock(self, layer_id: str) -> None:
        if self._doc:
            layer = self._doc.layers.get(layer_id)
            if layer:
                layer.locked = not layer.locked
                # Lock doesn't affect pixel data — skip invalidation
                self._layers_panel.refresh(self._doc)
                self._update_transform_box()

    def _on_rename_layer(self, layer_id: str, new_name: str) -> None:
        if self._doc:
            layer = self._doc.layers.get(layer_id)
            if layer:
                layer.name = new_name
                self._doc.save_snapshot(f"Rename to {new_name}")
                self._refresh(invalidate=False)

    def _on_layers_reordered(self, layer_ids: list[str], target_visual_row: int) -> None:
        """Handle drag-drop reorder from the layers panel."""
        if not self._doc:
            return
        # Convert the visual display order to a new stack order.
        # The display is top→bottom (reverse of stack bottom→top).
        display_ids = self._layers_panel.row_layer_ids()

        # Remove the dragged ids from the display order
        remaining = [lid for lid in display_ids if lid not in layer_ids]

        # Clamp target row
        target_visual_row = max(0, min(target_visual_row, len(remaining)))

        # Insert dragged ids at the target position
        for i, lid in enumerate(layer_ids):
            remaining.insert(target_visual_row + i, lid)

        # Display order is reversed stack order.  Reverse to get stack order.
        new_stack_order = list(reversed(remaining))
        self._doc.layers.reorder_by_ids(new_stack_order)
        self._doc.save_snapshot("Reorder Layers")
        self._refresh()

    def _on_layers_reparented(self, layer_ids: list[str], group_id: str) -> None:
        """Handle drag-drop into a group from the layers panel."""
        if not self._doc:
            return
        self._doc.layers.reparent(layer_ids, group_id)
        self._doc.save_snapshot("Move to Group")
        self._refresh()

    def _on_toggle_vis_selected(self) -> None:
        self._layers_panel.toggle_visibility_for_selected()

    def _on_flatten(self) -> None:
        if self._doc:
            self._doc.flatten()
            self._refresh()

    # ---- Selection ----------------------------------------------------------

    def _on_select_all(self) -> None:
        if self._doc:
            self._doc.selection.select_all()
            self._update_selection_overlay()

    def _on_deselect(self) -> None:
        if self._doc:
            self._doc.selection.deselect()
            self._update_selection_overlay()

    def _on_invert_sel(self) -> None:
        if self._doc:
            self._doc.selection.invert()
            self._update_selection_overlay()

    # ---- Tools + Canvas -----------------------------------------------------

    # Tools that should display a real-time brush size cursor
    _BRUSH_CURSOR_TOOLS = {
        ToolType.BRUSH, ToolType.ERASER,
        ToolType.CLONE_STAMP, ToolType.HEALING_BRUSH,
    }

    def _on_tool_selected(self, t: ToolType) -> None:
        # Commit any in-progress text editing when switching away
        if self._tools.active_type == ToolType.TEXT and t != ToolType.TEXT:
            self._text_exit_editing()
        self._tools.select(t)
        self._status.set_tool(t.name.replace("_", " ").title())
        self._canvas.set_tool_cursor(t)
        self._update_properties_panel()
        self._update_transform_box()
        self._update_brush_cursor()
        # Setup text tool callbacks
        if t == ToolType.TEXT:
            self._text_setup()

    def _on_canvas_hover(self, x: int, y: int) -> None:
        """Handle non-drag mouse movement for cursor updates."""
        if self._tools.active_type == ToolType.TEXT:
            self._text_update_hover_cursor(x, y)

    # Tools that require rasterization of text / non-raster layers
    _PAINTING_TOOLS = {
        ToolType.BRUSH, ToolType.ERASER, ToolType.CLONE_STAMP,
        ToolType.HEALING_BRUSH, ToolType.GRADIENT, ToolType.PAINT_BUCKET,
    }

    def _on_canvas_press(self, x: int, y: int, pressure: float) -> None:
        self._dragging = True
        # Block painting tools on text layers unless rasterized
        if self._doc and self._needs_rasterize_warning():
            if not self._ask_rasterize():
                self._dragging = False
                return
        self._tools.on_press(self._doc, x, y, pressure)
        tool_type = self._tools.active_type
        if tool_type in (ToolType.RECT_SELECT, ToolType.ELLIPSE_SELECT):
            self._drag_start = (x, y)
        elif tool_type == ToolType.TEXT:
            self._text_update_overlay()

    def _on_canvas_move(self, x: int, y: int, pressure: float) -> None:
        tool_type = self._tools.active_type
        self._tools.on_move(self._doc, x, y, pressure)
        
        if tool_type in (ToolType.RECT_SELECT, ToolType.ELLIPSE_SELECT) and hasattr(self, "_drag_start"):
            sx, sy = self._drag_start
            dr = self._canvas._doc_rect()
            zx = dr.left() + (min(sx, x) / self._canvas._doc_w) * dr.width()
            zy = dr.top() + (min(sy, y) / self._canvas._doc_h) * dr.height()
            zw = abs(x - sx) / self._canvas._doc_w * dr.width()
            zh = abs(y - sy) / self._canvas._doc_h * dr.height()
            self._canvas.set_drag_rect(QRectF(zx, zy, zw, zh))
        elif tool_type == ToolType.TEXT:
            # Update overlay to show drawing preview or editing state
            self._text_update_overlay()
            # Update cursor shape on hover (only when not dragging)
            if not self._dragging:
                self._text_update_hover_cursor(x, y)
        else:
            self._schedule_render()

    def _on_canvas_release(self, x: int, y: int) -> None:
        self._dragging = False
        self._tools.on_release(self._doc, x, y)
        self._canvas.set_drag_rect(None)
        if hasattr(self, "_drag_start"):
            del self._drag_start
        self._refresh()
        # Update text overlay after release (may have created a new text layer)
        if self._tools.active_type == ToolType.TEXT:
            self._text_update_overlay()

    # ---- Properties panel ---------------------------------------------------

    def _update_properties_panel(self) -> None:
        tool_type = self._tools.active_type
        tool = self._tools.active_tool
        if tool is None:
            self._props_panel.clear()
            self._props_panel.set_text_mode(False)
            return

        # Text tool uses its own specialised properties bar
        if tool_type == ToolType.TEXT:
            self._props_panel.clear()
            self._props_panel.set_text_mode(True, tool)
            return

        self._props_panel.set_text_mode(False)
        self._props_panel.clear()
        self._props_panel.set_title(f"{tool.name} Properties")
        for key, (val, lo, hi) in self._tools.get_properties().items():
            label = key.replace("_", " ").title()
            if isinstance(val, float) and hi <= 1:
                self._props_panel.add_slider(key, label, int(val * 100), int(lo * 100), int(hi * 100))
            else:
                self._props_panel.add_slider(key, label, int(val), int(lo), int(hi))

    def _on_prop_changed(self, key: str, value: object) -> None:
        props = self._tools.get_properties()
        if key in props:
            _, lo, hi = props[key]
            if isinstance(lo, float) and hi <= 1:
                self._tools.set_property(key, float(value) / 100.0)
            else:
                self._tools.set_property(key, float(value))
        if key in ("size", "hardness", "opacity", "flow"):
            self._update_brush_cursor()

    def _on_text_prop_changed(self, key: str, value: object) -> None:
        """Handle property changes from the text properties bar."""
        tool = self._tools.active_tool
        if tool is None or self._tools.active_type != ToolType.TEXT:
            return
        tool.apply_property(key, value)
        self._text_update_overlay()

    # ---- Brush cursor --------------------------------------------------------

    def _update_brush_cursor(self) -> None:
        """Generate the actual dab preview and push it to the canvas."""
        tool_type = self._tools.active_type
        if tool_type in self._BRUSH_CURSOR_TOOLS:
            tool = self._tools.active_tool
            if tool is None:
                self._canvas.hide_brush_preview()
                return
            # Ask the tool to generate its preview dab (exact stamp)
            dab = tool.generate_preview_dab() if hasattr(tool, "generate_preview_dab") else None
            if dab is not None:
                is_eraser = tool_type == ToolType.ERASER
                self._canvas.set_brush_dab(dab, is_eraser=is_eraser)
            else:
                self._canvas.hide_brush_preview()
            # Use blank cursor — the painted dab replaces the system cursor
            self._canvas.setCursor(Qt.CursorShape.BlankCursor)
        else:
            self._canvas.hide_brush_preview()

    def _on_fg_color_changed(self, color) -> None:
        """Forward foreground colour to tools and update brush preview."""
        self._tools.set_foreground_color(color.to_array())
        self._update_brush_cursor()

    # ---- Adjustments / Filters ----------------------------------------------

    def _preview_render(self) -> None:
        """Re-render the canvas for a live filter/adjustment preview."""
        if not self._doc:
            return
        active = self._doc.layers.active_layer
        if active:
            self._pipeline.invalidate(active.id)
        else:
            self._pipeline.invalidate()
        result = self._pipeline.execute_to_uint8(self._doc)
        self._canvas.set_image(result)

    def _on_adjustment(self, name: str) -> None:
        if self._doc and run_adjustment(name, self._doc, self, preview_fn=self._preview_render):
            self._refresh()

    def _on_filter(self, key: str) -> None:
        if self._doc and run_filter(key, self._doc, self, preview_fn=self._preview_render):
            self._refresh()

    # ---- Image transforms ---------------------------------------------------

    def _transform(self, op: str) -> None:
        if not self._doc or not self._doc.layers.active_layer:
            return
        layer = self._doc.layers.active_layer
        if layer.locked:
            return
        self._doc.save_snapshot(op.replace("_", " ").title())
        px = layer.pixels
        if op == "flip_h":
            layer.pixels = TransformEngine.flip_h(px)
        elif op == "flip_v":
            layer.pixels = TransformEngine.flip_v(px)
        elif op == "rotate_cw":
            layer.pixels = TransformEngine.rotate(px, -90)
        elif op == "rotate_ccw":
            layer.pixels = TransformEngine.rotate(px, 90)
        self._refresh()

    # ---- Text tool management -----------------------------------------------

    def _text_setup(self) -> None:
        """Configure the text tool with callbacks.

        If the active layer is already a text layer, automatically enter
        editing mode so the user doesn't have to click on it again after
        switching from Move (or any other tool).
        """
        tool = self._tools.active_tool
        if tool is None:
            return
        tool.set_refresh_callback(self._text_on_refresh)
        tool.set_overlay_callback(self._text_update_overlay)
        self._canvas.set_key_handler(self._text_on_key)

        # Auto-enter editing on the active text layer
        if self._doc and not tool.is_editing:
            layer = self._doc.layers.active_layer
            if layer is not None and layer.layer_type == LayerType.TEXT:
                td = getattr(layer, "_text_data", None)
                if td is not None:
                    tool._start_editing(layer, self._doc)
                    self._text_update_overlay()
                    self._refresh()

    def _text_on_refresh(self) -> None:
        """Called by the text tool when it needs a visual refresh."""
        self._pipeline.invalidate()
        result = self._pipeline.execute_to_uint8(self._doc)
        self._canvas.set_image(result)
        self._history_panel.refresh(self._doc.history)
        self._layers_panel.refresh(self._doc)
        self._text_update_overlay()

    def _text_on_key(self, key: int, text: str, modifiers) -> bool:
        """Forward key events to the text tool."""
        tool = self._tools.active_tool
        if tool is None or self._tools.active_type != ToolType.TEXT:
            return False
        consumed = tool.on_key_press(key, text, modifiers)
        if consumed:
            self._text_update_overlay()
        return consumed

    def _text_update_overlay(self) -> None:
        """Sync the text editing overlay state to the canvas."""
        tool = self._tools.active_tool
        if tool is None or self._tools.active_type != ToolType.TEXT:
            self._canvas.set_text_editing(False)
            self._canvas.set_text_box(None)
            self._canvas.set_text_draw_rect(None)
            return

        # Drawing preview
        if tool.is_drawing:
            self._canvas.set_text_editing(False)
            self._canvas.set_text_box(None)
            self._canvas.set_text_draw_rect(tool.draw_rect)
            return

        self._canvas.set_text_draw_rect(None)

        # Editing mode
        if tool.is_editing and tool.text_data is not None:
            td = tool.text_data
            self._canvas.set_text_editing(True)
            box = tool.editing_box()
            angle = tool.editing_rotation()
            self._canvas.set_text_box(box, angle)

            # Cursor position
            cx, cy = td.cursor_to_xy(td.cursor_pos)
            ch = td.cursor_line_height(td.cursor_pos)
            self._canvas.set_text_cursor(cx, cy, ch)

            # Selection rectangles
            sel_rects = []
            if td.has_selection:
                lo, hi = td.selection_range
                lines = td.compute_layout()
                pos = 0
                for line in lines:
                    line_len = sum(len(g.char) for g in line.glyphs)
                    line_end = pos + line_len
                    if line_end <= lo or pos >= hi:
                        pos = line_end
                        continue
                    # This line has some selection
                    sel_start_in_line = max(lo, pos) - pos
                    sel_end_in_line = min(hi, line_end) - pos
                    # Compute x positions
                    x0 = line.x_offset
                    x1 = line.x_offset
                    ci = 0
                    for g in line.glyphs:
                        if ci == sel_start_in_line:
                            x0 = g.x
                        if ci == sel_end_in_line:
                            x1 = g.x
                            break
                        ci += len(g.char)
                    else:
                        x1 = line.x_offset + sum(g.advance for g in line.glyphs)
                    sel_rects.append((int(x0), int(line.y),
                                     int(x1 - x0), int(line.height)))
                    pos = line_end
            self._canvas.set_text_selection_rects(sel_rects)
            # Also hide transform box when editing text
            self._canvas.set_transform_box(None)
        else:
            self._canvas.set_text_editing(False)
            self._canvas.set_text_box(None)
            self._canvas.set_text_selection_rects([])

    def _text_update_hover_cursor(self, x: int, y: int) -> None:
        """Change the mouse cursor when hovering over text box handles."""
        tool = self._tools.active_tool
        if tool is None or self._tools.active_type != ToolType.TEXT:
            return
        hint = tool.hit_test_cursor_shape(x, y)
        if hint is None:
            self._canvas.setCursor(QCursor(Qt.CursorShape.IBeamCursor))
        elif hint == "text":
            self._canvas.setCursor(QCursor(Qt.CursorShape.IBeamCursor))
        elif hint in ("resize_tl", "resize_br"):
            self._canvas.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        elif hint in ("resize_tr", "resize_bl"):
            self._canvas.setCursor(QCursor(Qt.CursorShape.SizeBDiagCursor))
        elif hint in ("resize_t", "resize_b"):
            self._canvas.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
        elif hint in ("resize_l", "resize_r"):
            self._canvas.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        else:
            self._canvas.setCursor(QCursor(Qt.CursorShape.IBeamCursor))

    def _text_exit_editing(self) -> None:
        """Commit text editing and clean up overlay."""
        tool = self._tools.active_tool
        if tool is not None and hasattr(tool, "commit_editing"):
            tool.commit_editing(self._doc)
        self._canvas.set_text_editing(False)
        self._canvas.set_text_box(None)
        self._canvas.set_text_draw_rect(None)
        self._canvas.set_text_selection_rects([])
        self._canvas.set_key_handler(None)

    # ---- Rasterize text layer ------------------------------------------------

    def _needs_rasterize_warning(self) -> bool:
        """Return True if the active tool would paint on a text layer."""
        if self._tools.active_type not in self._PAINTING_TOOLS:
            return False
        layer = self._doc.layers.active_layer
        return layer is not None and layer.layer_type == LayerType.TEXT

    def _ask_rasterize(self) -> bool:
        """Show a rasterization dialog.  Return True if user accepted."""
        reply = QMessageBox.warning(
            self,
            "Rasterize Text Layer",
            "This type layer must be rasterized before it can be modified "
            "with this tool.  Once rasterized, the text will no longer be "
            "editable.\n\nRasterize the layer?",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Ok:
            self._rasterize_active_layer()
            return True
        return False

    def _rasterize_active_layer(self) -> None:
        """Convert the active text layer into a plain raster layer."""
        layer = self._doc.layers.active_layer
        if layer is None:
            return
        self._doc.save_snapshot("Rasterize Text")
        layer.layer_type = LayerType.RASTER
        # Discard text data — the current pixels are kept as-is
        if hasattr(layer, "_text_data"):
            try:
                del layer._text_data
            except AttributeError:
                layer._text_data = None
        # Clear any lingering transform bookkeeping
        layer.transform_angle = 0.0
        layer.transform_base_w = 0
        layer.transform_base_h = 0
        layer._transform_original = None
        self._refresh()

    # ---- Zoom ---------------------------------------------------------------

    def _zoom(self, factor: float) -> None:
        self._canvas.set_zoom(self._canvas.zoom * factor)
        self._status.set_zoom(self._canvas.zoom)

    # ---- Drag & drop --------------------------------------------------------

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if not path:
                continue
            try:
                img = load_image(path)
                if self._doc:
                    self._doc.place_image(img, name=Path(path).stem)
                else:
                    h, w = img.shape[:2]
                    self._doc = Document(w, h, name=Path(path).stem)
                    self._doc.layers[0].pixels = img
                self._refresh()
                self._canvas.zoom_to_fit()
            except Exception as exc:
                QMessageBox.warning(self, "Error", str(exc))
            break
