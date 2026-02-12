"""Main application window — assembles all panels, menus, and canvas."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication, QDockWidget, QFileDialog, QInputDialog, QMainWindow, QMessageBox,
)

from ..core.document import Document
from ..core.enums import BlendMode, LayerType, ToolType
from ..engine.render_pipeline import RenderPipeline
from ..transforms.transform_engine import TransformEngine
from ..utils.image_io import load_image, save_image
from .canvas_view import CanvasView
from .dialogs.layer_styles_dialog import LayerStylesDialog
from .dialogs.new_document import NewDocumentDialog
from .file_tab_bar import FileTabBar
from .filter_runner import _adj_map, _filter_name_map, run_adjustment, run_filter
from .menus import EditorMenuBar
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

        # Multi-document tracking: list of (Document, str|None) pairs
        self._open_docs: list[tuple[Document, str | None]] = []

        # Blend-mode hover preview state
        self._blend_preview_original: BlendMode | None = None

        # Render throttle — max ~30 fps during drag
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(33)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._do_deferred_render)
        self._render_pending = False
        self._dragging = False

        # Deferred panel refresh — coalesced to avoid rebuilding panels
        # dozens of times per second during interactive operations.
        self._panel_refresh_timer = QTimer(self)
        self._panel_refresh_timer.setInterval(200)  # 5 fps panel updates
        self._panel_refresh_timer.setSingleShot(True)
        self._panel_refresh_timer.timeout.connect(self._do_deferred_panel_refresh)
        self._panel_refresh_pending = False

        self._build_ui()
        self._wire_menus()
        self._wire_panels()
        self._wire_canvas()
        self._wire_file_tabs()
        self._new_document(1920, 1080)

    # ---- UI assembly --------------------------------------------------------

    def _build_ui(self) -> None:
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolBar
        
        self._menu = EditorMenuBar(self)
        self.setMenuBar(self._menu)

        # Properties panel as a toolbar directly under the menu bar
        self._props_panel = PropertiesPanel()
        self._props_toolbar = QToolBar("Properties", self)
        self._props_toolbar.setMovable(False)
        self._props_toolbar.setFloatable(False)
        self._props_toolbar.addWidget(self._props_panel)
        self._props_toolbar.setStyleSheet(
            "QToolBar { background: #333333; border: none; border-bottom: 1px solid #444; spacing: 0; padding: 0; }"
            "QToolBar > QWidget { background: #333333; }"
        )
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._props_toolbar)

        self._toolbar = EditorToolbar(self)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._toolbar)
        
        # Central widget: file tabs + canvas
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        
        # File tab bar at the top of the central area
        self._file_tabs = FileTabBar()
        central_layout.addWidget(self._file_tabs)
        
        # Canvas below the tabs
        self._canvas = CanvasView(self)
        central_layout.addWidget(self._canvas)
        
        self.setCentralWidget(central)
        
        # Dock panels on the sides
        self._layers_panel = LayersPanel()
        self._layers_dock = self._dock(self._layers_panel, "Layers", Qt.DockWidgetArea.RightDockWidgetArea)
        self._history_panel = HistoryPanel()
        self._dock(self._history_panel, "History", Qt.DockWidgetArea.RightDockWidgetArea)
        self._color_panel = ColorPanel()
        self._color_dock = self._dock(self._color_panel, "Color", Qt.DockWidgetArea.RightDockWidgetArea)
        self.tabifyDockWidget(self._layers_dock, self._color_dock)
        self._layers_dock.raise_()
        self._status = EditorStatusBar(self)
        self.setStatusBar(self._status)

    def _dock(self, widget, title: str, area) -> QDockWidget:
        d = QDockWidget(title, self)
        d.setWidget(widget)
        self.addDockWidget(area, d)
        return d

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
                action.triggered.connect(lambda checked, k=fkey: self._on_menu_filter(k))

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
        lp.styles_requested.connect(self._on_layer_styles)
        lp.opacity_changed.connect(self._on_opacity)
        lp.blend_mode_changed.connect(self._on_blend_mode)
        lp.blend_mode_hovered.connect(self._on_blend_hover)
        lp.blend_mode_hover_ended.connect(self._on_blend_hover_end)
        lp.visibility_toggled.connect(self._on_toggle_vis)
        lp.lock_toggled.connect(self._on_toggle_lock)
        lp.layers_reordered.connect(self._on_layers_reordered)
        lp.layers_reparented.connect(self._on_layers_reparented)
        lp.layers_unparented.connect(self._on_layers_unparented)
        lp.rename_requested.connect(self._on_rename_layer)
        lp.adjustment_layer_requested.connect(self._on_add_adjustment_layer)
        lp.edit_adjustment_requested.connect(self._on_edit_adjustment_layer)
        lp.filter_layer_requested.connect(self._on_add_filter_layer)
        lp.edit_filter_requested.connect(self._on_edit_filter_layer)
        self._history_panel.state_selected.connect(self._on_history_jump)
        self._color_panel.fg_changed.connect(self._on_fg_color_changed)
        self._props_panel.value_changed.connect(self._on_prop_changed)
        self._props_panel.text_property_changed.connect(self._on_text_prop_changed)
        self._props_panel.gradient_property_changed.connect(self._on_gradient_prop_changed)

    # ---- Wiring: file tabs --------------------------------------------------

    def _wire_file_tabs(self) -> None:
        self._file_tabs.tab_selected.connect(self._on_tab_selected)
        self._file_tabs.tab_close_requested.connect(self._on_tab_close)

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
        self._open_docs.append((self._doc, None))
        self._file_tabs.add_tab(self._doc.name)
        self._refresh()
        self._canvas.zoom_to_fit()
        self._status.set_document_info(self._doc.name, w, h)

    def _refresh(self, invalidate: bool = True, layer_id: str | None = None) -> None:
        """Full UI refresh.

        Parameters
        ----------
        invalidate : bool
            If *True* (default), the render cache is marked stale so the
            composite is recomputed.  Pass *False* for operations that
            only change non-pixel state (layer selection, panel sync)
            to skip expensive recompositing.
        layer_id : str | None
            Optional layer that changed.  When set the engine can use
            its incremental cache instead of a full rebuild.
        """
        if not self._doc:
            return
        if invalidate:
            self._pipeline.invalidate(layer_id)
        result = self._pipeline.execute_to_uint8(self._doc)
        self._canvas.set_image(result, force=invalidate)
        self._layers_panel.refresh(self._doc)
        self._history_panel.refresh(self._doc.history)
        self._update_selection_overlay()
        self._update_transform_box()

    def _refresh_canvas_only(self) -> None:
        """Re-render and update canvas only (skip panel updates)."""
        if not self._doc:
            return
        active = self._doc.layers.active_layer
        self._pipeline.invalidate(active.id if active else None)
        result = self._pipeline.execute_to_uint8(self._doc)
        self._canvas.set_image(result, force=True)
        self._update_transform_box()

    def _refresh_lightweight(self) -> None:
        """Re-render canvas + lightweight panel sync (no thumbnails)."""
        if not self._doc:
            return
        active = self._doc.layers.active_layer
        self._pipeline.invalidate(active.id if active else None)
        result = self._pipeline.execute_to_uint8(self._doc)
        self._canvas.set_image(result, force=True)
        self._layers_panel.refresh_controls_only(self._doc)
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

    def _schedule_panel_refresh(self) -> None:
        """Request a deferred panel refresh (throttled to ~5fps)."""
        if not self._panel_refresh_pending:
            self._panel_refresh_pending = True
            self._panel_refresh_timer.start()

    def _do_deferred_panel_refresh(self) -> None:
        """Timer callback — perform the actual panel refresh."""
        self._panel_refresh_pending = False
        if self._doc:
            self._layers_panel.refresh(self._doc, thumbnails=False)
            self._history_panel.refresh(self._doc.history)

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
        self._open_docs.append((self._doc, path))
        self._file_tabs.add_tab(Path(path).name, tooltip=path)
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
            # Update the tab text and stored path
            idx = self._file_tabs.current_index()
            if 0 <= idx < len(self._open_docs):
                self._open_docs[idx] = (self._doc, path)
                self._file_tabs.set_tab_text(idx, Path(path).name)

    # ---- Tab management -----------------------------------------------------

    def _on_tab_selected(self, index: int) -> None:
        """Switch to the document at the given tab index."""
        if index < 0 or index >= len(self._open_docs):
            return
        doc, path = self._open_docs[index]
        self._doc = doc
        self._refresh()
        self._canvas.zoom_to_fit()
        name = Path(path).name if path else doc.name
        self._status.set_document_info(name, doc.width, doc.height)
        self.setWindowTitle(f"Photo Editor — {name}")

    def _on_tab_close(self, index: int) -> None:
        """Close the document at the given tab index."""
        if index < 0 or index >= len(self._open_docs):
            return
        # Don't close the last tab — keep at least one document open
        if self._file_tabs.count() <= 1:
            return
        self._open_docs.pop(index)
        self._file_tabs.remove_tab(index)
        # Switch to whatever tab is now current
        new_idx = self._file_tabs.current_index()
        if 0 <= new_idx < len(self._open_docs):
            self._on_tab_selected(new_idx)

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
        self._pipeline.engine.invalidate_all()
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
                self._layers_panel.refresh(self._doc, thumbnails=False)

    def _on_toggle_lock(self, layer_id: str) -> None:
        if self._doc:
            layer = self._doc.layers.get(layer_id)
            if layer:
                layer.locked = not layer.locked
                # Lock doesn't affect pixel data — skip invalidation
                self._layers_panel.refresh_controls_only(self._doc)
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
        self._pipeline.engine.invalidate_all()
        self._refresh()

    def _on_layers_reparented(self, layer_ids: list[str], group_id: str) -> None:
        """Handle drag-drop into a group from the layers panel."""
        if not self._doc:
            return
        self._doc.layers.reparent(layer_ids, group_id)
        self._doc.save_snapshot("Move to Group")
        self._pipeline.engine.invalidate_all()
        self._refresh()

    def _on_layers_unparented(self, layer_ids: list[str]) -> None:
        """Handle drag-drop out of a group — remove layers from their group."""
        if not self._doc:
            return
        self._doc.layers.reparent(layer_ids, None)
        self._doc.save_snapshot("Remove from Group")
        self._pipeline.engine.invalidate_all()
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
        # Clear clone/heal source overlay when switching away
        if (self._tools.active_type in (ToolType.CLONE_STAMP, ToolType.HEALING_BRUSH)
                and t not in (ToolType.CLONE_STAMP, ToolType.HEALING_BRUSH)):
            self._canvas.set_source_position(None)
            self._canvas.set_source_drawing(False)
            self._canvas.set_clone_preview(None)
        self._tools.select(t)
        self._status.set_tool(t.name.replace("_", " ").title())
        self._canvas.set_tool_cursor(t)
        self._update_properties_panel()
        self._update_transform_box()
        self._update_brush_cursor()
        # Restore source overlay if switching to clone/heal with a source set
        if t in (ToolType.CLONE_STAMP, ToolType.HEALING_BRUSH):
            tool = self._tools.active_tool
            if tool is not None and tool.source_set:
                self._canvas.set_source_position((tool.source_x, tool.source_y))
        # Setup text tool callbacks
        if t == ToolType.TEXT:
            self._text_setup()
        # Wire up gradient tool callbacks
        if t == ToolType.GRADIENT:
            self._gradient_setup()
        # Wire up eyedropper colour callback
        if t == ToolType.EYEDROPPER:
            tool = self._tools.active_tool
            if tool is not None:
                tool.set_color_callback(self._on_eyedropper_sample)
        # Wire up zoom tool callback
        if t == ToolType.ZOOM:
            tool = self._tools.active_tool
            if tool is not None:
                tool.set_zoom_callback(self._on_zoom_tool)
        # Wire up pan tool callback
        if t == ToolType.PAN:
            tool = self._tools.active_tool
            if tool is not None:
                tool.set_pan_callback(self._on_pan_tool)

    def _on_eyedropper_sample(self, rgba) -> None:
        """Called when the eyedropper samples a colour."""
        from ..core.color import Color
        self._tools.set_foreground_color(rgba)
        if hasattr(self, "_color_panel"):
            c = Color.from_array(rgba)
            self._color_panel._mgr.foreground = c

    def _on_zoom_tool(self, factor: float) -> None:
        """Called when the zoom tool requests a zoom change."""
        self._canvas.set_zoom(self._canvas.zoom * factor)

    def _on_pan_tool(self, dx: int, dy: int) -> None:
        """Called when the pan tool requests a pan delta."""
        from PySide6.QtCore import QPointF
        self._canvas._pan += QPointF(dx * self._canvas.zoom, dy * self._canvas.zoom)
        self._canvas.update()

    def _on_canvas_hover(self, x: int, y: int) -> None:
        """Handle non-drag mouse movement for cursor updates."""
        if self._tools.active_type == ToolType.TEXT:
            self._text_update_hover_cursor(x, y)
        elif self._tools.active_type in (ToolType.CLONE_STAMP, ToolType.HEALING_BRUSH):
            tool = self._tools.active_tool
            if tool is not None and tool.source_set:
                # Compute where sampling would happen if user clicked here
                if tool._offset_locked:
                    ox, oy = tool._offset_x, tool._offset_y
                else:
                    ox = tool.source_x - x
                    oy = tool.source_y - y
                self._canvas.set_source_offset((ox, oy))
            self._update_clone_preview(x, y)

    # Tools that require rasterization of text / non-raster layers
    _PAINTING_TOOLS = {
        ToolType.BRUSH, ToolType.ERASER, ToolType.CLONE_STAMP,
        ToolType.HEALING_BRUSH, ToolType.GRADIENT, ToolType.PAINT_BUCKET,
    }

    def _on_canvas_press(self, x: int, y: int, pressure: float) -> None:
        self._dragging = True

        # Alt+click sets the clone / heal source point
        modifiers = QApplication.keyboardModifiers()
        if modifiers & Qt.KeyboardModifier.AltModifier:
            tool_type = self._tools.active_type
            if tool_type in (ToolType.CLONE_STAMP, ToolType.HEALING_BRUSH):
                tool = self._tools.active_tool
                if tool is not None:
                    tool.set_source(x, y)
                    self._canvas.set_source_position((x, y))
                    self._status.showMessage(f"Source set at ({x}, {y})", 2000)
                self._dragging = False
                return

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
        elif tool_type in (ToolType.CLONE_STAMP, ToolType.HEALING_BRUSH):
            tool = self._tools.active_tool
            if tool is not None and tool.source_set:
                self._canvas.set_source_offset((tool._offset_x, tool._offset_y))
                self._canvas.set_source_drawing(True)

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
        tool_type = self._tools.active_type
        self._tools.on_release(self._doc, x, y)
        self._canvas.set_drag_rect(None)
        if hasattr(self, "_drag_start"):
            del self._drag_start
        # End clone/heal drawing state
        if tool_type in (ToolType.CLONE_STAMP, ToolType.HEALING_BRUSH):
            self._canvas.set_source_drawing(False)
        active = self._doc.layers.active_layer if self._doc else None
        self._refresh(layer_id=active.id if active else None)
        # Update text overlay after release (may have created a new text layer)
        if tool_type == ToolType.TEXT:
            self._text_update_overlay()

    # ---- Properties panel ---------------------------------------------------

    def _update_properties_panel(self) -> None:
        tool_type = self._tools.active_type
        tool = self._tools.active_tool
        if tool is None:
            self._props_panel.clear()
            self._props_panel.set_text_mode(False)
            self._props_panel.set_gradient_mode(False)
            return

        # Text tool uses its own specialised properties bar
        if tool_type == ToolType.TEXT:
            self._props_panel.clear()
            self._props_panel.set_text_mode(True, tool)
            return

        # Gradient tool uses its own specialised properties bar
        if tool_type == ToolType.GRADIENT:
            self._props_panel.clear()
            self._props_panel.set_gradient_mode(True, tool)
            return

        self._props_panel.set_text_mode(False)
        self._props_panel.set_gradient_mode(False)
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

    # ---- Gradient tool -------------------------------------------------------

    def _gradient_setup(self) -> None:
        """Wire callbacks for the gradient tool."""
        tool = self._tools.active_tool
        if tool is None:
            return
        tool.set_preview_callback(self._schedule_render)
        tool.set_handles_callback(self._on_gradient_handles)

    def _on_gradient_handles(self, start, end, stops, visible) -> None:
        """Update the canvas gradient-handle overlay."""
        self._canvas.set_gradient_handles(start, end, stops, visible)

    def _on_gradient_prop_changed(self, key: str, value: object) -> None:
        """Handle property changes from the gradient properties bar."""
        tool = self._tools.active_tool
        if tool is None or self._tools.active_type != ToolType.GRADIENT:
            return
        if key == "gradient_type":
            tool.gradient_type = str(value)
            if tool.is_editing:
                tool._reapply_gradient()
                self._refresh()
        elif key == "opacity":
            tool.opacity = float(value)
            if tool.is_editing:
                tool._reapply_gradient()
                self._refresh()
        elif key == "reverse":
            tool.reverse_gradient()
            self._refresh()
        elif key == "gradient_fill":
            # Received a ColorFill from the gradient editor — extract stops
            fill = value
            if hasattr(fill, "stops"):
                tool.stops = list(fill.stops)
            # Map fill class → gradient_type string
            from ..core.color import LinearGradient, RadialGradient
            from ..core.color_engine import ConicalGradient, DiamondGradient
            _cls_map = {
                LinearGradient: "linear",
                RadialGradient: "radial",
                ConicalGradient: "conical",
                DiamondGradient: "diamond",
            }
            gtype = _cls_map.get(type(fill))
            if gtype:
                tool.gradient_type = gtype
            self._refresh()

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

    # ---- Clone/Heal live preview --------------------------------------------

    def _update_clone_preview(self, cursor_x: int, cursor_y: int) -> None:
        """Generate a live preview patch of what clone/heal would paint at (cursor_x, cursor_y).

        This samples pixels from the source area and shows them translucently
        at the cursor position before the user clicks.
        """
        tool = self._tools.active_tool
        if tool is None or not getattr(tool, "source_set", False):
            self._canvas.set_clone_preview(None)
            return
        if self._doc is None:
            return
        layer = self._doc.layers.active_layer
        if layer is None:
            self._canvas.set_clone_preview(None)
            return

        lx, ly = layer.position
        pixels = layer.pixels  # float32 RGBA
        h, w = pixels.shape[:2]
        radius = max(1, tool.size // 2)

        # Compute source center (using existing offset if locked, else from source point)
        if tool._offset_locked:
            ox, oy = tool._offset_x, tool._offset_y
        else:
            ox = tool.source_x - cursor_x
            oy = tool.source_y - cursor_y

        cx_doc = cursor_x - lx
        cy_doc = cursor_y - ly
        sx_doc = cx_doc + ox
        sy_doc = cy_doc + oy

        # Build circular preview patch from source area
        d = radius * 2 + 1
        preview = np.zeros((d, d, 4), dtype=np.uint8)
        # Source region bounds
        y0s = sy_doc - radius
        x0s = sx_doc - radius
        # Clip to valid
        cy0 = max(0, -y0s)
        cx0 = max(0, -x0s)
        cy1 = min(d, h - y0s)
        cx1 = min(d, w - x0s)
        if cy1 <= cy0 or cx1 <= cx0:
            self._canvas.set_clone_preview(None)
            return

        src = pixels[y0s + cy0:y0s + cy1, x0s + cx0:x0s + cx1]
        patch = np.clip(src * 255, 0, 255).astype(np.uint8)

        # Circular mask
        yy, xx = np.mgrid[cy0:cy1, cx0:cx1]
        dist = np.sqrt((xx - radius) ** 2 + (yy - radius) ** 2).astype(np.float32)
        mask = np.clip(1.0 - dist / max(radius, 1), 0, 1)
        hardness = getattr(tool, "hardness", 0.7)
        mask = mask ** (1.0 / max(hardness, 0.01))
        mask[dist > radius] = 0.0

        preview[cy0:cy1, cx0:cx1, :3] = patch[..., :3]
        preview[cy0:cy1, cx0:cx1, 3] = np.clip(mask * 200, 0, 255).astype(np.uint8)

        self._canvas.set_clone_preview(preview)

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
        self._canvas.set_image(result, force=True)

    def _on_adjustment(self, name: str) -> None:
        if self._doc and run_adjustment(name, self._doc, self, preview_fn=self._preview_render):
            self._refresh()

    def _on_add_adjustment_layer(self, name: str) -> None:
        """Create a new adjustment layer for the given adjustment *name*."""
        if not self._doc:
            return
        adj_cls = _adj_map().get(name)
        if adj_cls is None:
            return
        adj = adj_cls()
        layer = self._doc.add_layer(name=name, layer_type=LayerType.ADJUSTMENT)
        layer.adjustment = adj
        layer.adjustment_params = dict(adj.default_params)
        self._refresh()
        # Open the edit dialog immediately (skip for param-less adjustments like Invert)
        if adj.default_params:
            self._on_edit_adjustment_layer(layer.id)

    def _on_edit_adjustment_layer(self, layer_id: str) -> None:
        """Open a dialog to edit an existing adjustment layer's parameters."""
        if not self._doc:
            return
        layer = self._doc.layers.get(layer_id)
        if layer is None or layer.layer_type != LayerType.ADJUSTMENT:
            return
        adj = layer.adjustment
        if adj is None:
            return
        # If no params (e.g. Invert), nothing to edit
        if not adj.default_params:
            return

        from .dialogs.filter_dialog import FilterDialog

        current_params = dict(layer.adjustment_params) if layer.adjustment_params else dict(adj.default_params)
        dlg = FilterDialog(f"Adjustment — {adj.name}", current_params, parent=self)

        def _on_preview(params: dict) -> None:
            layer.adjustment_params = params
            self._pipeline.engine.invalidate_all()
            self._pipeline.invalidate()
            result = self._pipeline.execute_to_uint8(self._doc)
            self._canvas.set_image(result, force=True)

        dlg.params_changed.connect(_on_preview)

        # Show initial preview with current params
        _on_preview(current_params)

        old_params = dict(current_params)
        if dlg.exec():
            layer.adjustment_params = dlg.get_params()
            self._doc.save_snapshot(f"Edit {adj.name}")
            self._refresh()
        else:
            # Cancelled — restore original params
            layer.adjustment_params = old_params
            self._pipeline.engine.invalidate_all()
            self._pipeline.invalidate()
            self._refresh()

    def _on_add_filter_layer(self, display_name: str) -> None:
        """Create a new filter layer for the given filter display name."""
        if not self._doc:
            return
        fmap = _filter_name_map()
        filt_cls = fmap.get(display_name)
        if filt_cls is None:
            return
        filt = filt_cls()
        layer = self._doc.add_layer(name=display_name, layer_type=LayerType.FILTER)
        layer.adjustment = filt
        layer.adjustment_params = dict(filt.default_params)
        self._refresh()
        # Open the edit dialog immediately (skip for param-less filters)
        if filt.default_params:
            self._on_edit_filter_layer(layer.id)

    def _on_edit_filter_layer(self, layer_id: str) -> None:
        """Open a dialog to edit an existing filter layer's parameters."""
        if not self._doc:
            return
        layer = self._doc.layers.get(layer_id)
        if layer is None or layer.layer_type != LayerType.FILTER:
            return
        filt = layer.adjustment
        if filt is None:
            return
        if not filt.default_params:
            return

        from .dialogs.filter_dialog import FilterDialog

        current_params = dict(layer.adjustment_params) if layer.adjustment_params else dict(filt.default_params)
        dlg = FilterDialog(f"Filter \u2014 {filt.name}", current_params, parent=self)

        def _on_preview(params: dict) -> None:
            layer.adjustment_params = params
            self._pipeline.engine.invalidate_all()
            self._pipeline.invalidate()
            result = self._pipeline.execute_to_uint8(self._doc)
            self._canvas.set_image(result, force=True)

        dlg.params_changed.connect(_on_preview)
        _on_preview(current_params)

        old_params = dict(current_params)
        if dlg.exec():
            layer.adjustment_params = dlg.get_params()
            self._doc.save_snapshot(f"Edit {filt.name}")
            self._refresh()
        else:
            layer.adjustment_params = old_params
            self._pipeline.engine.invalidate_all()
            self._pipeline.invalidate()
            self._refresh()

    def _on_menu_filter(self, key: str) -> None:
        """Menu bar filter entry — create a filter layer by internal key."""
        if not self._doc:
            return
        from .filter_runner import _filter_map
        filt_cls = _filter_map().get(key)
        if filt_cls is None:
            return
        filt = filt_cls()
        self._on_add_filter_layer(filt.name)

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
        """Called by the text tool when it needs a visual refresh.

        Uses the same 30fps throttle as other tools to avoid blocking
        the event loop on every keystroke.
        """
        self._schedule_render()
        self._schedule_panel_refresh()
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
        # Bake any non-destructive transforms and clear bookkeeping
        layer.rasterize_transform()
        self._refresh()

    # ---- Layer Styles -------------------------------------------------------

    def _on_layer_styles(self) -> None:
        """Open the Layer Styles dialog for the active layer."""
        if not self._doc:
            return
        layer = self._doc.layers.active_layer
        if not layer:
            return

        # Snapshot the current styles so we can revert on Cancel
        import copy
        old_styles = copy.deepcopy(layer.styles)

        dlg = LayerStylesDialog(existing_styles=layer.styles, parent=self)

        # ---- Live preview: apply on every parameter tweak ----
        _connected_panels: set[str] = set()

        def _preview() -> None:
            layer._styles = dlg.get_styles()
            self._refresh()
            # Re-wire any newly added panels (from the "+" button)
            _wire_panels()

        def _wire_panels() -> None:
            for key, panel in dlg._panels.items():
                if key not in _connected_panels:
                    panel.changed.connect(_preview)
                    _connected_panels.add(key)

        _wire_panels()

        def _accept(styles: list) -> None:
            layer._styles = list(styles)
            self._doc.save_snapshot(f"Layer Style \u2013 {layer.name}")
            self._refresh()

        def _reject() -> None:
            layer._styles = old_styles
            self._refresh()

        dlg.styles_accepted.connect(_accept)
        dlg.rejected.connect(_reject)
        dlg.exec()

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
