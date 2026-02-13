"""Main application window — assembles all panels, menus, and canvas."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QCursor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QDockWidget, QFileDialog, QInputDialog, QMainWindow, QMessageBox,
)

from ..core.color_engine import ColorManager
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
from .shortcut_manager import ShortcutManager
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

        # Wire up Move tool auto-select callback
        move_tool = self._tools._tools.get(ToolType.MOVE)
        if move_tool is not None:
            move_tool.on_layer_auto_selected = self._on_move_auto_select

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
        self._sel_moving = False
        self._sel_move_start: tuple[int, int] = (0, 0)
        self._sel_move_orig_mask: object = None   # saved mask before drag
        self._sel_move_total_dx: int = 0
        self._sel_move_total_dy: int = 0

        # Deferred panel refresh — coalesced to avoid rebuilding panels
        # dozens of times per second during interactive operations.
        self._panel_refresh_timer = QTimer(self)
        self._panel_refresh_timer.setInterval(200)  # 5 fps panel updates
        self._panel_refresh_timer.setSingleShot(True)
        self._panel_refresh_timer.timeout.connect(self._do_deferred_panel_refresh)
        self._panel_refresh_pending = False

        self._shortcut_mgr = ShortcutManager.instance()

        self._build_ui()
        self._wire_menus()
        self._wire_panels()
        self._wire_canvas()
        self._wire_file_tabs()
        self._wire_shortcuts()
        self._new_document(1920, 1080)

    # ---- UI assembly --------------------------------------------------------

    def _build_ui(self) -> None:
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QToolBar
        from .widgets.rulers import HorizontalRuler, VerticalRuler, RulerCorner, Guide, RULER_SIZE
        
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
        
        # Central widget: file tabs + rulers + canvas
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        
        # File tab bar at the top of the central area
        self._file_tabs = FileTabBar()
        central_layout.addWidget(self._file_tabs)
        
        # Grid: rulers + canvas
        ruler_grid = QWidget()
        grid = QGridLayout(ruler_grid)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)

        self._ruler_corner = RulerCorner()
        self._h_ruler = HorizontalRuler()
        self._v_ruler = VerticalRuler()
        self._canvas = CanvasView(self)

        grid.addWidget(self._ruler_corner, 0, 0)
        grid.addWidget(self._h_ruler, 0, 1)
        grid.addWidget(self._v_ruler, 1, 0)
        grid.addWidget(self._canvas, 1, 1)

        # Rulers default visible
        self._rulers_visible = True
        self._guides: list = []

        # Wire ruler signals
        for ruler in (self._h_ruler, self._v_ruler):
            ruler.guide_created.connect(self._on_guide_created)
            ruler.guide_moved.connect(self._on_guide_moved)
            ruler.guide_deleted.connect(self._on_guide_deleted)

        central_layout.addWidget(ruler_grid, 1)
        
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
        a["resize_canvas"].triggered.connect(self._on_resize_canvas)
        a["resize_image"].triggered.connect(self._on_resize_image)
        a["new_layer"].triggered.connect(self._on_add_layer)
        a["new_group"].triggered.connect(self._on_add_group)
        a["dup_layer"].triggered.connect(self._on_dup_layer)
        a["del_layer"].triggered.connect(self._on_del_layer)
        a["add_mask"].triggered.connect(self._on_add_mask)
        a["add_mask_black"].triggered.connect(self._on_add_mask_black)
        a["add_mask_standalone"].triggered.connect(self._on_add_mask_standalone)
        a["remove_mask_layer"].triggered.connect(self._on_remove_mask_layer)
        a["apply_mask_layer"].triggered.connect(self._on_apply_mask_layer)
        a["invert_mask_layer"].triggered.connect(self._on_invert_mask_layer)
        a["convert_to_mask"].triggered.connect(self._on_convert_to_mask)
        a["toggle_vis"].triggered.connect(self._on_toggle_vis_selected)
        a["flatten"].triggered.connect(self._on_flatten)
        a["merge_down"].triggered.connect(self._on_merge_down)
        a["select_all"].triggered.connect(self._on_select_all)
        a["deselect"].triggered.connect(self._on_deselect)
        a["invert_sel"].triggered.connect(self._on_invert_sel)
        a["feather_sel"].triggered.connect(self._on_feather_sel)
        a["grow_sel"].triggered.connect(self._on_grow_sel)
        a["shrink_sel"].triggered.connect(self._on_shrink_sel)
        a["delete_sel"].triggered.connect(self._on_delete_selection)
        a["fill_fg"].triggered.connect(lambda: self._on_fill_selection("fg"))
        a["fill_bg"].triggered.connect(lambda: self._on_fill_selection("bg"))
        a["cut"].triggered.connect(self._on_cut)
        a["copy"].triggered.connect(self._on_copy)
        a["paste"].triggered.connect(self._on_paste)
        a["duplicate_sel"].triggered.connect(self._on_duplicate_selection)
        a["selection_to_mask"].triggered.connect(self._on_selection_to_mask)
        a["zoom_in"].triggered.connect(lambda: self._zoom(1.25))
        a["zoom_out"].triggered.connect(lambda: self._zoom(1 / 1.25))
        a["zoom_fit"].triggered.connect(self._canvas.zoom_to_fit)
        a["zoom_100"].triggered.connect(lambda: self._canvas.set_zoom(1.0))
        a["toggle_grid"].triggered.connect(self._on_toggle_grid)
        a["toggle_rulers"].triggered.connect(self._on_toggle_rulers)
        a["toggle_guides"].triggered.connect(self._on_toggle_guides)
        # Keyboard Shortcuts dialog
        if "keyboard_shortcuts" in a:
            a["keyboard_shortcuts"].triggered.connect(self._on_keyboard_shortcuts)
        if "about" in a:
            a["about"].triggered.connect(self._on_about)
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
        lp.mask_dropped_on_layer.connect(self._on_mask_dropped_on_layer)
        lp.adj_filter_dropped_on_layer.connect(self._on_adj_filter_dropped_on_layer)
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
        self._props_panel.align_requested.connect(self._on_align_requested)
        self._props_panel.zoom_action.connect(self._on_zoom_action)
        self._props_panel.selection_property_changed.connect(self._on_sel_prop_changed)
        self._props_panel.selection_action.connect(self._on_sel_action)
        self._props_panel.crop_property_changed.connect(self._on_crop_prop_changed)
        self._props_panel.crop_apply.connect(self._on_crop_apply)
        self._props_panel.crop_cancel.connect(self._on_crop_cancel)

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
        # Widget-coord signals for the pan tool
        self._canvas.widget_pressed.connect(self._on_widget_press)
        self._canvas.widget_moved.connect(self._on_widget_move)
        self._canvas.widget_released.connect(self._on_widget_release)
        # View change → sync rulers
        self._canvas.view_changed.connect(self._update_rulers)
        # Guide interaction on canvas
        self._canvas.guide_drag_moved.connect(self._on_canvas_guide_drag_moved)
        self._canvas.guide_drag_released.connect(self._on_canvas_guide_drag_released)

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
        self._update_rulers()

    def _refresh_canvas_only(self) -> None:
        """Re-render and update canvas only (skip panel updates)."""
        if not self._doc:
            return
        active = self._doc.layers.active_layer
        self._pipeline.invalidate(active.id if active else None)
        result = self._pipeline.execute_to_uint8(self._doc)
        self._canvas.set_image(result, force=True)
        self._update_transform_box()
        self._update_rulers()

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
                # If a selection is active, fit the box to the selection mask
                if self._doc.selection.active and self._doc.selection._mask is not None:
                    import numpy as np
                    mask = self._doc.selection._mask
                    rows = np.any(mask > 0.5, axis=1)
                    cols = np.any(mask > 0.5, axis=0)
                    if np.any(rows) and np.any(cols):
                        y0, y1 = int(np.where(rows)[0][0]), int(np.where(rows)[0][-1])
                        x0, x1 = int(np.where(cols)[0][0]), int(np.where(cols)[0][-1])
                        # Offset by floating selection drag if in progress
                        tool = self._tools.active_tool
                        fdx = fdy = 0
                        if tool is not None and getattr(tool, '_floating', False):
                            fdx = getattr(tool, '_float_dx', 0)
                            fdy = getattr(tool, '_float_dy', 0)
                        self._canvas.set_transform_box(
                            (x0 + fdx, y0 + fdy, x1 - x0 + 1, y1 - y0 + 1))
                    else:
                        self._canvas.set_transform_box(None)
                    return

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
        if len(selected) >= 1:
            # Group all selected layers (including single) into a new group
            self._doc.group_selected_layers(selected)
        else:
            self._doc.add_group()
        self._pipeline.engine.invalidate_all()
        self._refresh()

    def _on_dup_layer(self) -> None:
        if not self._doc or not self._doc.layers.active_layer:
            return
        # Ctrl+J is context-dependent: selection active → duplicate via selection
        if self._doc.selection.active and self._doc.selection.mask is not None:
            self._on_duplicate_selection()
        else:
            self._doc.duplicate_layer(self._doc.layers.active_layer.id)
            self._refresh()

    def _on_del_layer(self) -> None:
        if not self._doc or len(self._doc.layers) <= 1:
            return
        # Delete all selected layers (multi-select support)
        selected = self._layers_panel.selected_layer_ids()
        if selected:
            for lid in selected:
                if len(self._doc.layers) <= 1:
                    break
                if self._doc.layers.get(lid):
                    self._doc.remove_layer(lid)
        elif self._doc.layers.active_layer:
            self._doc.remove_layer(self._doc.layers.active_layer.id)
        self._refresh()

    def _on_add_mask(self) -> None:
        if self._doc and self._doc.layers.active_layer:
            # If there's an active selection, convert it to a mask layer
            if self._doc.selection.active and self._doc.selection.mask is not None:
                self._doc.selection_to_mask_layer()
            else:
                self._doc.add_mask_layer(fill_white=True)
            self._refresh()

    def _on_add_mask_black(self) -> None:
        if self._doc and self._doc.layers.active_layer:
            self._doc.add_mask_layer(fill_white=False)
            self._refresh()

    def _on_add_mask_standalone(self) -> None:
        if self._doc:
            self._doc.add_mask_layer(target_id="__standalone__", fill_white=True)
            self._refresh()

    def _on_remove_mask_layer(self) -> None:
        if not self._doc:
            return
        active = self._doc.layers.active_layer
        if active and active.layer_type == LayerType.MASK:
            self._doc.remove_mask_layer(active.id)
            self._refresh()

    def _on_apply_mask_layer(self) -> None:
        if not self._doc:
            return
        active = self._doc.layers.active_layer
        if active and active.layer_type == LayerType.MASK:
            self._doc.apply_mask_layer(active.id)
            self._refresh()

    def _on_invert_mask_layer(self) -> None:
        if not self._doc:
            return
        active = self._doc.layers.active_layer
        if active and active.layer_type == LayerType.MASK:
            from ..masks.mask_manager import MaskManager
            self._doc.save_snapshot("Invert Mask Layer")
            MaskManager.invert_mask_layer(active)
            self._refresh()

    def _on_convert_to_mask(self) -> None:
        if not self._doc:
            return
        active = self._doc.layers.active_layer
        if active and active.layer_type not in (LayerType.MASK, LayerType.GROUP):
            self._doc.convert_layer_to_mask(active.id)
            self._refresh()

    def _on_selection_to_mask(self) -> None:
        if not self._doc:
            return
        if self._doc.selection.active:
            self._doc.selection_to_mask_layer()
            self._refresh()

    def _on_layer_selected(self, stack_index: int) -> None:
        if self._doc:
            self._doc.layers.active_index = stack_index
            self._update_transform_box()

    def _on_move_auto_select(self, stack_index: int) -> None:
        """Called by MoveTool when it auto-selects a different layer."""
        if not self._doc:
            return
        # Sync the layers panel highlight and transform box
        self._layers_panel.refresh(self._doc)
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

        # Count how many dragged items sit above the target row — after
        # removal, the insertion index must be shifted down by that count.
        drag_set = set(layer_ids)
        above_count = 0
        for i, lid in enumerate(display_ids):
            if i >= target_visual_row:
                break
            if lid in drag_set:
                above_count += 1

        # Remove the dragged ids from the display order
        remaining = [lid for lid in display_ids if lid not in drag_set]

        # Clamp adjusted target row
        adjusted_row = max(0, min(target_visual_row - above_count, len(remaining)))

        # Insert dragged ids at the target position
        for i, lid in enumerate(layer_ids):
            remaining.insert(adjusted_row + i, lid)

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

    def _on_mask_dropped_on_layer(self, mask_id: str, target_id: str) -> None:
        """Attach a mask layer to a target layer via drag-drop."""
        if not self._doc:
            return
        mask = self._doc.layers.get(mask_id)
        target = self._doc.layers.get(target_id)
        if mask is None or target is None:
            return
        if mask.layer_type != LayerType.MASK:
            return
        # Detach from old parent if any
        if mask.parent_id:
            old_parent = self._doc.layers.get(mask.parent_id)
            if old_parent and mask_id in old_parent.mask_layers:
                old_parent.mask_layers.remove(mask_id)
        # Attach to new target
        mask.parent_id = target_id
        mask.ex_parent_id = None  # Clear ex-parent since it's now attached
        if mask_id not in target.mask_layers:
            target.mask_layers.append(mask_id)
        # Reposition just before the target in the stack
        self._doc.layers.reposition_before(mask_id, target_id)
        self._doc.save_snapshot("Attach Mask to Layer")
        self._pipeline.engine.invalidate_all()
        self._refresh()

    def _on_adj_filter_dropped_on_layer(self, adj_id: str, target_id: str) -> None:
        """Attach an adjustment/filter layer to a target layer via drag-drop."""
        if not self._doc:
            return
        adj_layer = self._doc.layers.get(adj_id)
        target = self._doc.layers.get(target_id)
        if adj_layer is None or target is None:
            return
        if adj_layer.layer_type not in (LayerType.ADJUSTMENT, LayerType.FILTER):
            return
        # Remove from old parent's children if any
        if adj_layer.parent_id:
            old_parent = self._doc.layers.get(adj_layer.parent_id)
            if old_parent and adj_id in old_parent.children:
                old_parent.children.remove(adj_id)
        # Set new parent
        adj_layer.parent_id = target_id
        # Reposition just before the target in the stack
        self._doc.layers.reposition_before(adj_id, target_id)
        self._doc.save_snapshot("Attach Adjustment to Layer")
        self._pipeline.engine.invalidate_all()
        self._refresh()

    def _on_toggle_vis_selected(self) -> None:
        self._layers_panel.toggle_visibility_for_selected()

    def _on_flatten(self) -> None:
        if self._doc:
            self._doc.flatten()
            self._refresh()

    def _on_merge_down(self) -> None:
        if self._doc:
            if not self._doc.merge_down():
                self.statusBar().showMessage("Cannot merge down — no suitable layer below", 3000)
            else:
                self._refresh()

    def _on_resize_canvas(self) -> None:
        """Resize the document canvas (keeps layer pixel data, changes bounds)."""
        if not self._doc:
            return
        from .dialogs.new_document import NewDocumentDialog
        dlg = NewDocumentDialog(self)
        dlg.setWindowTitle("Canvas Size")
        # Pre-fill with current dimensions
        dlg._width.setValue(self._doc.width)
        dlg._height.setValue(self._doc.height)
        if dlg.exec():
            w, h, _ = dlg.get_values()
            if w > 0 and h > 0:
                self._doc._snapshot("Resize Canvas")
                self._doc.resize(w, h)
                self._refresh()

    def _on_resize_image(self) -> None:
        """Resize / resample the entire image (scales all layers)."""
        if not self._doc:
            return
        from .dialogs.new_document import NewDocumentDialog
        dlg = NewDocumentDialog(self)
        dlg.setWindowTitle("Image Size")
        dlg._width.setValue(self._doc.width)
        dlg._height.setValue(self._doc.height)
        if dlg.exec():
            import cv2
            new_w, new_h, _ = dlg.get_values()
            if new_w < 1 or new_h < 1:
                return
            sx = new_w / max(self._doc.width, 1)
            sy = new_h / max(self._doc.height, 1)
            self._doc._snapshot("Resize Image")
            for layer in self._doc.layers.layers:
                px = layer.pixels
                lh, lw = px.shape[:2]
                nlw, nlh = max(1, round(lw * sx)), max(1, round(lh * sy))
                layer._pixels = cv2.resize(px, (nlw, nlh), interpolation=cv2.INTER_AREA)
                layer.width, layer.height = nlw, nlh
                ox, oy = layer.position
                layer.position = (round(ox * sx), round(oy * sy))
            self._doc.resize(new_w, new_h)
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

    def _on_feather_sel(self) -> None:
        """Feather (blur) the current selection edges."""
        if not self._doc or not self._doc.selection.active:
            return
        radius, ok = QInputDialog.getInt(
            self, "Feather Selection", "Feather radius (px):", 5, 1, 250)
        if ok:
            self._doc.selection.feather(radius)
            self._update_selection_overlay()

    def _on_grow_sel(self) -> None:
        """Expand the current selection."""
        if not self._doc or not self._doc.selection.active:
            return
        pixels, ok = QInputDialog.getInt(
            self, "Grow Selection", "Grow by (px):", 5, 1, 250)
        if ok:
            self._doc.selection.grow(pixels)
            self._update_selection_overlay()

    def _on_shrink_sel(self) -> None:
        """Shrink the current selection."""
        if not self._doc or not self._doc.selection.active:
            return
        pixels, ok = QInputDialog.getInt(
            self, "Shrink Selection", "Shrink by (px):", 5, 1, 250)
        if ok:
            self._doc.selection.shrink(pixels)
            self._update_selection_overlay()

    def _on_delete_selection(self) -> None:
        """Delete (clear to transparent) the selected region on the active layer."""
        if not self._doc:
            return
        layer = self._doc.layers.active_layer
        if layer is None:
            return
        mask = self._doc.selection._mask
        if mask is None:
            return
        self._doc._snapshot("Delete Selection")
        lx, ly = layer.position
        h, w = layer.pixels.shape[:2]
        # Extract the portion of the document-level selection that overlaps the layer
        layer_mask = self._extract_layer_mask(mask, lx, ly, w, h)
        if layer_mask is not None:
            # Set alpha to 0 where selected
            layer.pixels[..., 3] *= (1.0 - layer_mask)
        self._refresh()

    def _on_fill_selection(self, which: str) -> None:
        """Fill the selected region with foreground or background color."""
        if not self._doc:
            return
        layer = self._doc.layers.active_layer
        if layer is None:
            return
        import numpy as np
        if which == "fg":
            color = self._color_panel._mgr.foreground.to_array()
        else:
            color = self._color_panel._mgr.background.to_array()
        # Ensure RGBA float32
        if len(color) < 4:
            color = np.array([*color[:3], 1.0], dtype=np.float32)
        self._doc._snapshot("Fill Selection")
        mask = self._doc.selection._mask
        lx, ly = layer.position
        h, w = layer.pixels.shape[:2]
        if mask is not None:
            layer_mask = self._extract_layer_mask(mask, lx, ly, w, h)
            if layer_mask is not None:
                for c in range(4):
                    layer.pixels[..., c] = (
                        layer.pixels[..., c] * (1.0 - layer_mask) + color[c] * layer_mask
                    )
        else:
            # No selection — fill entire layer
            layer.pixels[..., :] = color
        self._refresh()

    def _on_cut(self) -> None:
        """Copy selected area then delete it."""
        self._on_copy()
        self._on_delete_selection()

    def _on_copy(self) -> None:
        """Copy selected region of the active layer to an internal clipboard."""
        if not self._doc:
            return
        layer = self._doc.layers.active_layer
        if layer is None:
            return
        import numpy as np
        mask = self._doc.selection._mask
        lx, ly = layer.position
        h, w = layer.pixels.shape[:2]
        if mask is not None:
            layer_mask = self._extract_layer_mask(mask, lx, ly, w, h)
            if layer_mask is None:
                return
            copied = layer.pixels.copy()
            copied[..., 3] *= layer_mask
        else:
            copied = layer.pixels.copy()
        self._clipboard = copied.copy()
        self._clipboard_pos = (lx, ly)
        self._status.showMessage("Copied to clipboard", 2000)

    def _on_paste(self) -> None:
        """Paste clipboard content as a new layer."""
        if not hasattr(self, "_clipboard") or self._clipboard is None:
            return
        if not self._doc:
            return
        from ..core.layer import Layer
        import numpy as np
        new_layer = Layer(
            name="Pasted Layer",
            width=self._clipboard.shape[1],
            height=self._clipboard.shape[0],
        )
        new_layer.pixels = self._clipboard.copy()
        if hasattr(self, "_clipboard_pos"):
            new_layer.position = list(self._clipboard_pos)
        self._doc._snapshot("Paste")
        self._doc.layers.add(new_layer)
        self._refresh()

    def _on_duplicate_selection(self) -> None:
        """Create a new layer from the selected pixels of the active layer."""
        if not self._doc or not self._doc.selection.active:
            return
        layer = self._doc.layers.active_layer
        if layer is None:
            return
        import numpy as np
        from ..core.layer import Layer
        mask = self._doc.selection._mask
        lx, ly = layer.position
        h, w = layer.pixels.shape[:2]
        layer_mask = self._extract_layer_mask(mask, lx, ly, w, h)
        if layer_mask is None:
            return
        # Copy pixels masked by selection
        copied = layer.pixels.copy()
        copied[..., 3] *= layer_mask
        # Crop to bounding box of non-zero alpha
        alpha = copied[..., 3]
        rows = np.any(alpha > 0, axis=1)
        cols = np.any(alpha > 0, axis=0)
        if not np.any(rows) or not np.any(cols):
            return
        y0, y1 = np.where(rows)[0][[0, -1]]
        x0, x1 = np.where(cols)[0][[0, -1]]
        cropped = copied[y0:y1 + 1, x0:x1 + 1].copy()
        new_layer = Layer(
            name=f"{layer.name} copy",
            width=cropped.shape[1],
            height=cropped.shape[0],
        )
        new_layer.pixels = cropped
        new_layer.position = [lx + int(x0), ly + int(y0)]
        self._doc._snapshot("Duplicate Selection")
        self._doc.layers.add(new_layer)
        self._refresh()
        self._status.showMessage("Duplicated selection to new layer", 2000)

    def _extract_layer_mask(self, doc_mask, lx: int, ly: int,
                            w: int, h: int):
        """Extract the portion of the doc-level selection mask that overlaps the layer."""
        import numpy as np
        dh, dw = doc_mask.shape[:2]
        dst_y1 = max(0, ly)
        dst_y2 = min(dh, ly + h)
        dst_x1 = max(0, lx)
        dst_x2 = min(dw, lx + w)
        if dst_y2 <= dst_y1 or dst_x2 <= dst_x1:
            return None
        layer_mask = np.zeros((h, w), dtype=np.float32)
        src_y1 = dst_y1 - ly
        src_y2 = dst_y2 - ly
        src_x1 = dst_x1 - lx
        src_x2 = dst_x2 - lx
        layer_mask[src_y1:src_y2, src_x1:src_x2] = doc_mask[dst_y1:dst_y2, dst_x1:dst_x2]
        return layer_mask

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
        # Commit floating selection when leaving the move tool
        if self._tools.active_type == ToolType.MOVE and t != ToolType.MOVE:
            tool = self._tools.active_tool
            if tool is not None and getattr(tool, '_floating', False):
                tool.commit_float(self._doc)
                self._update_selection_overlay()
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
        # Wire up crop tool callbacks
        if t == ToolType.CROP:
            self._crop_setup()

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

    def _on_zoom_action(self, action: str) -> None:
        """Handle zoom actions from the zoom properties bar."""
        if action == "zoom_in":
            self._canvas.set_zoom(self._canvas.zoom * 1.5)
        elif action == "zoom_out":
            self._canvas.set_zoom(self._canvas.zoom / 1.5)
        elif action == "fit":
            if self._doc:
                vw = self._canvas.width()
                vh = self._canvas.height()
                scale = min(vw / self._doc.width, vh / self._doc.height) * 0.95
                self._canvas.set_zoom(scale)
                from PySide6.QtCore import QPointF
                self._canvas._pan = QPointF(0, 0)
                self._canvas.update()
        elif action == "reset":
            self._canvas.set_zoom(1.0)
            from PySide6.QtCore import QPointF
            self._canvas._pan = QPointF(0, 0)
            self._canvas.update()

    def _on_pan_tool(self, dx_screen: float, dy_screen: float) -> None:
        """Called when the pan tool requests a pan delta (screen pixels)."""
        from PySide6.QtCore import QPointF
        self._canvas._pan += QPointF(dx_screen, dy_screen)
        self._canvas.update()

    def _on_widget_press(self, wx: float, wy: float) -> None:
        """Forward widget-coord press to the pan tool."""
        if self._tools.active_type == ToolType.PAN:
            tool = self._tools.active_tool
            if tool is not None:
                tool.begin_pan(wx, wy)

    def _on_widget_move(self, wx: float, wy: float) -> None:
        """Forward widget-coord move to the pan tool."""
        if self._tools.active_type == ToolType.PAN:
            tool = self._tools.active_tool
            if tool is not None:
                tool.update_pan(wx, wy)

    def _on_widget_release(self) -> None:
        """Forward widget-coord release to the pan tool."""
        if self._tools.active_type == ToolType.PAN:
            tool = self._tools.active_tool
            if tool is not None:
                tool.end_pan()

    def _on_canvas_hover(self, x: int, y: int) -> None:
        """Handle non-drag mouse movement for cursor updates."""
        # Update ruler cursor position indicators
        if hasattr(self, '_h_ruler') and self._rulers_visible:
            dr = self._canvas._doc_rect()
            if self._canvas._doc_w > 0 and self._canvas._doc_h > 0:
                wx = dr.left() + (x / self._canvas._doc_w) * dr.width()
                wy = dr.top() + (y / self._canvas._doc_h) * dr.height()
                self._h_ruler.set_cursor_position(wx)
                self._v_ruler.set_cursor_position(wy)
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

        # Override selection mode from keyboard modifiers
        _SEL_TOOLS = {ToolType.RECT_SELECT, ToolType.ELLIPSE_SELECT,
                      ToolType.LASSO, ToolType.MAGIC_WAND}
        tool_type = self._tools.active_type
        if tool_type in _SEL_TOOLS:
            tool = self._tools.active_tool
            if tool is not None and hasattr(tool, "mode"):
                shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
                alt = bool(modifiers & Qt.KeyboardModifier.AltModifier)
                if shift and alt:
                    tool.mode = "intersect"
                elif shift:
                    tool.mode = "add"
                elif alt:
                    tool.mode = "subtract"
                # else: keep the mode from the properties bar

            # Check if click is inside existing selection → move selection mode
            # Only for rect, ellipse, and lasso tools (not magic wand)
            if (tool_type in (ToolType.RECT_SELECT, ToolType.ELLIPSE_SELECT, ToolType.LASSO)
                    and self._doc and self._doc.selection._mask is not None
                    and not shift and not alt):
                mask = self._doc.selection._mask
                if (0 <= y < mask.shape[0] and 0 <= x < mask.shape[1]
                        and mask[y, x] > 0.5):
                    self._doc.save_snapshot("Move Selection")
                    self._sel_moving = True
                    self._sel_move_start = (x, y)
                    self._sel_move_orig_mask = self._doc.selection._mask.copy()
                    self._sel_move_total_dx = 0
                    self._sel_move_total_dy = 0
                    self._dragging = True
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
        # Move selection mask by dragging (using original mask + total offset)
        if self._sel_moving and self._doc and self._sel_move_orig_mask is not None:
            ox, oy = self._sel_move_start
            self._sel_move_total_dx += x - ox
            self._sel_move_total_dy += y - oy
            self._sel_move_start = (x, y)
            # Recompute mask from original + total offset (no incremental clipping)
            import numpy as np
            orig = self._sel_move_orig_mask
            h, w = orig.shape
            dx, dy = self._sel_move_total_dx, self._sel_move_total_dy
            new_mask = np.zeros_like(orig)
            sx0 = max(0, -dx)
            sy0 = max(0, -dy)
            sx1 = min(w, w - dx)
            sy1 = min(h, h - dy)
            dx0 = max(0, dx)
            dy0 = max(0, dy)
            dx1 = dx0 + (sx1 - sx0)
            dy1 = dy0 + (sy1 - sy0)
            if sx1 > sx0 and sy1 > sy0:
                new_mask[dy0:dy1, dx0:dx1] = orig[sy0:sy1, sx0:sx1]
            self._doc.selection._mask = new_mask
            self._update_selection_overlay()
            self._canvas.update()
            return

        tool_type = self._tools.active_type
        self._tools.on_move(self._doc, x, y, pressure)
        
        if tool_type in (ToolType.RECT_SELECT, ToolType.ELLIPSE_SELECT) and hasattr(self, "_drag_start"):
            sx, sy = self._drag_start
            dr = self._canvas._doc_rect()
            zx = dr.left() + (min(sx, x) / self._canvas._doc_w) * dr.width()
            zy = dr.top() + (min(sy, y) / self._canvas._doc_h) * dr.height()
            zw = abs(x - sx) / self._canvas._doc_w * dr.width()
            zh = abs(y - sy) / self._canvas._doc_h * dr.height()
            is_ellipse = (tool_type == ToolType.ELLIPSE_SELECT)
            self._canvas.set_drag_rect(QRectF(zx, zy, zw, zh), ellipse=is_ellipse)
        elif tool_type == ToolType.LASSO:
            # Feed live lasso path to canvas for preview
            tool = self._tools.active_tool
            if tool is not None and hasattr(tool, '_points') and tool._drawing:
                self._canvas.set_lasso_points(list(tool._points))
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
        if self._sel_moving:
            self._sel_moving = False
            self._sel_move_orig_mask = None
            self._update_selection_overlay()
            self._canvas.update()
            # Refresh history panel so the snapshot shows up
            if self._doc:
                self._history_panel.refresh(self._doc.history)
            return
        tool_type = self._tools.active_type
        self._tools.on_release(self._doc, x, y)
        self._canvas.set_drag_rect(None)
        self._canvas.set_lasso_points(None)
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
            self._props_panel.set_text_mode(False)  # clears all modes
            return

        # Move tool uses its own alignment properties bar
        if tool_type == ToolType.MOVE:
            self._props_panel.clear()
            self._props_panel.set_move_mode(True)
            return

        # Crop tool uses its own specialised properties bar
        if tool_type == ToolType.CROP:
            self._props_panel.clear()
            self._props_panel.set_crop_mode(True, tool)
            return

        # Zoom tool uses its own properties bar
        if tool_type == ToolType.ZOOM:
            self._props_panel.clear()
            self._props_panel.set_zoom_mode(True)
            return

        # Selection tools use their own properties bar
        _SEL_TOOLS = {ToolType.RECT_SELECT, ToolType.ELLIPSE_SELECT,
                      ToolType.LASSO, ToolType.MAGIC_WAND}
        if tool_type in _SEL_TOOLS:
            self._props_panel.clear()
            is_wand = (tool_type == ToolType.MAGIC_WAND)
            self._props_panel.set_selection_mode(True, tool, is_wand=is_wand)
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
        self._props_panel.set_move_mode(False)
        self._props_panel.set_crop_mode(False)
        self._props_panel.set_zoom_mode(False)
        self._props_panel.set_selection_mode(False)
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

    def _on_align_requested(self, action: str) -> None:
        """Handle alignment/distribution requests from the Move properties bar."""
        from ..tools.move_tool import MoveTool
        if self._doc is None:
            return
        method = getattr(MoveTool, action, None)
        if method is not None:
            method(self._doc)
            self._refresh()

    # ---- Selection tool property/action handlers ----------------------------

    def _on_sel_prop_changed(self, key: str, value: object) -> None:
        """Handle property changes from the selection properties bar."""
        tool = self._tools.active_tool
        if tool is None:
            return
        if key == "mode" and hasattr(tool, "mode"):
            tool.mode = str(value)
        elif key == "feather" and hasattr(tool, "feather"):
            tool.feather = int(value)
        elif key == "tolerance" and hasattr(tool, "tolerance"):
            tool.tolerance = int(value)
        elif key == "contiguous" and hasattr(tool, "contiguous"):
            tool.contiguous = bool(value)

    def _on_sel_action(self, action: str) -> None:
        """Handle action buttons from the selection properties bar."""
        if action == "delete":
            self._on_delete_selection()
        elif action == "fill_fg":
            self._on_fill_selection("fg")
        elif action == "fill_bg":
            self._on_fill_selection("bg")
        elif action == "duplicate":
            self._on_duplicate_selection()
        elif action == "invert":
            self._on_invert_sel()
        elif action == "deselect":
            self._on_deselect()

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

    # ---- Crop tool ------------------------------------------------------------

    def _crop_setup(self) -> None:
        """Wire callbacks for the crop tool."""
        tool = self._tools.active_tool
        if tool is None:
            return
        tool.set_overlay_callback(self._on_crop_overlay)
        tool.set_crop_callback(self._on_crop_execute)
        tool.set_cancel_callback(lambda: self._canvas.set_crop_box(None))
        # Auto-create a bounding box around the active layer
        if self._doc is not None:
            tool.auto_box_for_layer(self._doc)
            self._props_panel.crop_bar.sync_from_tool(tool)

    def _on_crop_overlay(self, box) -> None:
        """Update the canvas crop box overlay and the properties bar dimensions."""
        self._canvas.set_crop_box(box)
        if box is not None:
            self._props_panel.crop_bar.set_dimensions(*box)
        else:
            self._props_panel.crop_bar.clear_dimensions()

    def _on_crop_prop_changed(self, key: str, value: object) -> None:
        """Handle property changes from the crop properties bar."""
        tool = self._tools.active_tool
        if tool is None or self._tools.active_type != ToolType.CROP:
            return
        if key == "crop_mode":
            from ..tools.crop_tool import CropMode
            tool.mode = CropMode.CANVAS if value == "canvas" else CropMode.LAYER

    def _on_crop_apply(self) -> None:
        """Commit the current crop box."""
        tool = self._tools.active_tool
        if tool is None or self._tools.active_type != ToolType.CROP:
            return
        if self._doc is None:
            return
        tool.apply(self._doc)

    def _on_crop_cancel(self) -> None:
        """Discard the crop box."""
        tool = self._tools.active_tool
        if tool is None or self._tools.active_type != ToolType.CROP:
            return
        tool.cancel()

    def _on_crop_execute(self, x: int, y: int, w: int, h: int, mode) -> None:
        """Execute the actual crop operation."""
        from ..tools.crop_tool import CropMode
        if self._doc is None:
            return

        if mode == CropMode.CANVAS:
            self._crop_canvas(x, y, w, h)
        else:
            self._crop_layer(x, y, w, h)

    def _crop_canvas(self, x: int, y: int, w: int, h: int) -> None:
        """Crop the canvas — only adjusts document size and layer offsets.

        Layer pixel data is NOT modified.  Layers that extend beyond the
        new canvas simply overflow (their pixels are preserved intact).
        """
        doc = self._doc
        if doc is None:
            return
        doc.save_snapshot("Crop Canvas")
        for layer in doc.layers:
            px, py = layer.position
            layer.position = (px - x, py - y)
        doc.resize(w, h)
        self._refresh()

    def _crop_layer(self, x: int, y: int, w: int, h: int) -> None:
        """Crop only the active layer's pixel data.

        Only raster layers can be cropped directly.  Non-raster layers
        (text, adjustment, etc.) require rasterization first.
        """
        doc = self._doc
        if doc is None:
            return
        layer = doc.layers.active_layer
        if layer is None:
            return
        # Non-raster layers must be rasterized before cropping
        if layer.layer_type != LayerType.RASTER:
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.warning(
                self,
                "Rasterize Layer",
                "This layer must be rasterized before it can be cropped.\n"
                "Once rasterized the layer will no longer be editable "
                "in its original form.\n\nRasterize the layer?",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Ok:
                return
            # Rasterize
            doc.save_snapshot(f"Rasterize {layer.name}")
            layer.layer_type = LayerType.RASTER
            if hasattr(layer, "_text_data"):
                try:
                    del layer._text_data
                except AttributeError:
                    layer._text_data = None
            layer.rasterize_transform()
        doc.save_snapshot("Crop Layer")
        px, py = layer.position
        lh, lw = layer.pixels.shape[:2]
        # Source region in the layer's pixel array
        sy0 = max(0, y - py)
        sx0 = max(0, x - px)
        sy1 = min(lh, y + h - py)
        sx1 = min(lw, x + w - px)
        if sy1 > sy0 and sx1 > sx0:
            cropped = layer.pixels[sy0:sy1, sx0:sx1].copy()
        else:
            cropped = np.zeros((max(1, h), max(1, w), 4), dtype=np.float32)
        layer.pixels = cropped
        layer.position = (x, y)
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
        """Create a new adjustment layer for the given adjustment *name*.

        By default, the adjustment is attached as a child of the active
        layer so it only affects that layer (like Affinity Photo).
        """
        if not self._doc:
            return
        adj_cls = _adj_map().get(name)
        if adj_cls is None:
            return
        adj = adj_cls()
        # Remember the selected layer *before* add_layer changes active
        prev_active = self._doc.layers.active_layer
        layer = self._doc.add_layer(name=name, layer_type=LayerType.ADJUSTMENT)
        layer.adjustment = adj
        layer.adjustment_params = dict(adj.default_params)
        # Parent under the previously active layer
        if prev_active is not None:
            parent = prev_active
            # If active is itself a child layer, parent under its parent instead
            if prev_active.parent_id:
                p = self._doc.layers.get(prev_active.parent_id)
                if p:
                    parent = p
            if parent.layer_type not in (LayerType.ADJUSTMENT, LayerType.FILTER, LayerType.MASK):
                layer.parent_id = parent.id
                self._doc.layers.reposition_before(layer.id, parent.id)
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
        """Create a new filter layer for the given filter display name.

        By default, the filter is attached as a child of the active
        layer so it only affects that layer (like Affinity Photo).
        """
        if not self._doc:
            return
        fmap = _filter_name_map()
        filt_cls = fmap.get(display_name)
        if filt_cls is None:
            return
        filt = filt_cls()
        # Remember the selected layer *before* add_layer changes active
        prev_active = self._doc.layers.active_layer
        layer = self._doc.add_layer(name=display_name, layer_type=LayerType.FILTER)
        layer.adjustment = filt
        layer.adjustment_params = dict(filt.default_params)
        # Parent under the previously active layer
        if prev_active is not None:
            parent = prev_active
            if prev_active.parent_id:
                p = self._doc.layers.get(prev_active.parent_id)
                if p:
                    parent = p
            if parent.layer_type not in (LayerType.ADJUSTMENT, LayerType.FILTER, LayerType.MASK):
                layer.parent_id = parent.id
                self._doc.layers.reposition_before(layer.id, parent.id)
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
        self._update_rulers()

    # ---- View toggles -------------------------------------------------------

    def _on_toggle_grid(self) -> None:
        self._show_grid = not getattr(self, "_show_grid", False)
        state = "on" if self._show_grid else "off"
        self.statusBar().showMessage(f"Grid {state} (not yet implemented)", 2000)

    def _on_toggle_rulers(self) -> None:
        self._rulers_visible = not self._rulers_visible
        self._ruler_corner.setVisible(self._rulers_visible)
        self._h_ruler.setVisible(self._rulers_visible)
        self._v_ruler.setVisible(self._rulers_visible)
        state = "on" if self._rulers_visible else "off"
        self.statusBar().showMessage(f"Rulers {state}", 2000)

    def _on_toggle_guides(self) -> None:
        self._show_guides = not getattr(self, "_show_guides", True)
        self._canvas.set_guides(self._guides if self._show_guides else [])
        state = "on" if self._show_guides else "off"
        self.statusBar().showMessage(f"Guides {state}", 2000)

    # ---- Ruler / guide management -------------------------------------------

    def _update_rulers(self) -> None:
        """Sync rulers with current canvas zoom/pan state."""
        if not hasattr(self, '_h_ruler') or not self._rulers_visible:
            return
        dr = self._canvas._doc_rect()
        dw = self._canvas._doc_w or 1
        dh = self._canvas._doc_h or 1

        # Horizontal ruler: origin is the widget-x of doc-coord 0
        h_zoom = dr.width() / dw
        h_origin = dr.left()
        self._h_ruler.set_view_params(h_zoom, h_origin, dw)

        # Vertical ruler: origin is the widget-y of doc-coord 0
        v_zoom = dr.height() / dh
        v_origin = dr.top()
        self._v_ruler.set_view_params(v_zoom, v_origin, dh)

        # Each ruler needs the *other* axis params for guide creation.
        # The perpendicular origin must account for the ruler bar offset:
        # the canvas widget starts at RULER_SIZE px below/right of the
        # ruler's origin, so doc-coord-0 in ruler space = RULER_SIZE + canvas origin.
        from .widgets.rulers import RULER_SIZE
        self._h_ruler.set_perp_view_params(v_zoom, v_origin + RULER_SIZE, dh)
        self._v_ruler.set_perp_view_params(h_zoom, h_origin + RULER_SIZE, dw)

        # Layer bounds
        layer = self._doc.layers.active_layer if self._doc else None
        if layer and layer.layer_type not in (LayerType.GROUP, LayerType.MASK):
            lx, ly = layer.position
            lh, lw = layer.pixels.shape[:2]
            self._h_ruler.set_layer_bounds(float(lx), float(lx + lw))
            self._v_ruler.set_layer_bounds(float(ly), float(ly + lh))
        else:
            self._h_ruler.set_layer_bounds(None, None)
            self._v_ruler.set_layer_bounds(None, None)

        # Pass guides to rulers
        self._h_ruler.set_guides(self._guides)
        self._v_ruler.set_guides(self._guides)

    def _on_guide_created(self, guide) -> None:
        self._guides.append(guide)
        self._canvas.set_preview_guide(None)  # clear preview
        self._canvas.set_guides(self._guides)
        self._h_ruler.set_guides(self._guides)
        self._v_ruler.set_guides(self._guides)

    def _on_guide_moved(self, guide, new_pos: float) -> None:
        guide.position = new_pos
        # Show preview on canvas while dragging from ruler
        if guide not in self._guides:
            self._canvas.set_preview_guide(guide)
        else:
            self._canvas.set_guides(self._guides)
        self._h_ruler.set_guides(self._guides)
        self._v_ruler.set_guides(self._guides)

    def _on_guide_deleted(self, guide) -> None:
        if guide in self._guides:
            self._guides.remove(guide)
        self._canvas.set_preview_guide(None)
        self._canvas.set_guides(self._guides)
        self._h_ruler.set_guides(self._guides)
        self._v_ruler.set_guides(self._guides)

    # ---- Canvas guide interaction -------------------------------------------

    def _on_canvas_guide_drag_moved(self, guide, new_pos: float) -> None:
        """Guide is being dragged on the canvas."""
        guide.position = new_pos
        self._canvas.set_guides(self._guides)
        self._h_ruler.set_guides(self._guides)
        self._v_ruler.set_guides(self._guides)

    def _on_canvas_guide_drag_released(self, guide, pos: float, delete: bool) -> None:
        """Guide drag finished on canvas — update or delete."""
        if delete:
            if guide in self._guides:
                self._guides.remove(guide)
        else:
            guide.position = pos
        self._canvas.set_guides(self._guides)
        self._h_ruler.set_guides(self._guides)
        self._v_ruler.set_guides(self._guides)

    # ---- Numpad opacity (Affinity-style) ------------------------------------

    _NUMPAD_MAP = {
        Qt.Key.Key_0: 0, Qt.Key.Key_1: 1, Qt.Key.Key_2: 2,
        Qt.Key.Key_3: 3, Qt.Key.Key_4: 4, Qt.Key.Key_5: 5,
        Qt.Key.Key_6: 6, Qt.Key.Key_7: 7, Qt.Key.Key_8: 8,
        Qt.Key.Key_9: 9,
    }

    def _init_numpad_state(self) -> None:
        self._numpad_first: int | None = None
        self._numpad_timer = QTimer(self)
        self._numpad_timer.setSingleShot(True)
        self._numpad_timer.setInterval(500)  # 500ms window for second digit
        self._numpad_timer.timeout.connect(self._numpad_commit)

    def _handle_numpad_opacity(self, key: int) -> bool:
        """Process a numpad digit for opacity. Returns True if consumed."""
        digit = self._NUMPAD_MAP.get(key)
        if digit is None:
            return False
        if not self._doc or not self._doc.layers.active_layer:
            return False

        if not hasattr(self, '_numpad_timer'):
            self._init_numpad_state()

        if self._numpad_first is not None:
            # Second digit — combine: first*10 + second → percentage
            pct = self._numpad_first * 10 + digit
            pct = max(0, min(100, pct))
            self._numpad_first = None
            self._numpad_timer.stop()
            self._set_opacity_pct(pct)
            return True
        else:
            # First digit — wait for possible second
            self._numpad_first = digit
            self._numpad_timer.start()
            return True

    def _numpad_commit(self) -> None:
        """Timer expired — commit single digit as opacity (1→10%, ... 0→100%)."""
        if self._numpad_first is not None:
            d = self._numpad_first
            pct = 100 if d == 0 else d * 10
            self._numpad_first = None
            self._set_opacity_pct(pct)

    def _set_opacity_pct(self, pct: int) -> None:
        """Set active layer opacity to *pct* percent."""
        if self._doc and self._doc.layers.active_layer:
            self._doc.layers.active_layer.opacity = pct / 100.0
            self._layers_panel.refresh_controls_only(self._doc)
            self._refresh_canvas_only()
            self.statusBar().showMessage(f"Opacity: {pct}%", 1500)

    # ---- Key event handling -------------------------------------------------

    def keyPressEvent(self, event) -> None:
        # Don't intercept during text editing
        if (self._tools.active_type == ToolType.TEXT
                and self._canvas._text_editing):
            return super().keyPressEvent(event)

        key = event.key()
        mods = event.modifiers()

        # Numpad digits (no modifiers) → opacity
        if not mods and self._handle_numpad_opacity(key):
            return

        super().keyPressEvent(event)

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

    # ---- Keyboard shortcuts system ------------------------------------------

    # Mapping from shortcut action_id → ToolType
    _TOOL_SHORTCUT_MAP = {
        "tool_move":            ToolType.MOVE,
        "tool_rect_select":     ToolType.RECT_SELECT,
        "tool_ellipse_select":  ToolType.ELLIPSE_SELECT,
        "tool_lasso":           ToolType.LASSO,
        "tool_magic_wand":      ToolType.MAGIC_WAND,
        "tool_crop":            ToolType.CROP,
        "tool_eyedropper":      ToolType.EYEDROPPER,
        "tool_healing_brush":   ToolType.HEALING_BRUSH,
        "tool_clone_stamp":     ToolType.CLONE_STAMP,
        "tool_brush":           ToolType.BRUSH,
        "tool_eraser":          ToolType.ERASER,
        "tool_gradient":        ToolType.GRADIENT,
        "tool_paint_bucket":    ToolType.PAINT_BUCKET,
        "tool_text":            ToolType.TEXT,
        "tool_shape":           ToolType.SHAPE,
        "tool_zoom":            ToolType.ZOOM,
        "tool_pan":             ToolType.PAN,
    }

    def _wire_shortcuts(self) -> None:
        """Build QShortcuts for tool switching, color, and brush size.

        These are re-created whenever the shortcut manager emits
        ``shortcuts_changed`` (preset change or manual rebind).
        """
        self._active_shortcuts: list[QShortcut] = []
        self._rebuild_shortcuts()
        self._shortcut_mgr.shortcuts_changed.connect(self._rebuild_shortcuts)

    def _rebuild_shortcuts(self) -> None:
        """Tear down and re-create all QShortcut objects."""
        # Remove old shortcuts
        for sc in self._active_shortcuts:
            sc.setEnabled(False)
            sc.deleteLater()
        self._active_shortcuts.clear()

        mgr = self._shortcut_mgr

        # ---- Tool shortcuts -------------------------------------------------
        for action_id, tool_type in self._TOOL_SHORTCUT_MAP.items():
            key_seq = mgr.binding(action_id)
            if not key_seq:
                continue
            sc = QShortcut(QKeySequence(key_seq), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            tt = tool_type  # capture for lambda
            sc.activated.connect(lambda t=tt: self._shortcut_tool(t))
            self._active_shortcuts.append(sc)

        # ---- Color shortcuts ------------------------------------------------
        swap_key = mgr.binding("swap_colors")
        if swap_key:
            sc = QShortcut(QKeySequence(swap_key), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(self._shortcut_swap_colors)
            self._active_shortcuts.append(sc)

        reset_key = mgr.binding("reset_colors")
        if reset_key:
            sc = QShortcut(QKeySequence(reset_key), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(self._shortcut_reset_colors)
            self._active_shortcuts.append(sc)

        # ---- Brush size shortcuts -------------------------------------------
        inc_key = mgr.binding("brush_size_increase")
        if inc_key:
            sc = QShortcut(QKeySequence(inc_key), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(lambda: self._shortcut_brush_size(5))
            self._active_shortcuts.append(sc)

        dec_key = mgr.binding("brush_size_decrease")
        if dec_key:
            sc = QShortcut(QKeySequence(dec_key), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(lambda: self._shortcut_brush_size(-5))
            self._active_shortcuts.append(sc)

        # ---- Fullscreen shortcut --------------------------------------------
        fs_key = mgr.binding("toggle_fullscreen")
        if fs_key:
            sc = QShortcut(QKeySequence(fs_key), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(self._shortcut_toggle_fullscreen)
            self._active_shortcuts.append(sc)

    # ---- Shortcut callbacks -------------------------------------------------

    # Tools that share the same shortcut key cycle through each other
    _TOOL_CYCLE_GROUPS: list[tuple[ToolType, ...]] = [
        (ToolType.RECT_SELECT, ToolType.ELLIPSE_SELECT),
    ]

    def _shortcut_tool(self, tool_type: ToolType) -> None:
        """Activate a tool via keyboard shortcut, cycling if same key pressed again."""
        # Don't hijack shortcuts while text editing
        if (self._tools.active_type == ToolType.TEXT
                and self._canvas._text_editing):
            return
        # Cycle through tool group if pressing the same key again
        current = self._tools.active_type
        for group in self._TOOL_CYCLE_GROUPS:
            if tool_type in group and current in group:
                idx = group.index(current)
                tool_type = group[(idx + 1) % len(group)]
                break
        self._toolbar.select_tool(tool_type)

    def _shortcut_swap_colors(self) -> None:
        if (self._tools.active_type == ToolType.TEXT
                and self._canvas._text_editing):
            return
        ColorManager.instance().swap()

    def _shortcut_reset_colors(self) -> None:
        if (self._tools.active_type == ToolType.TEXT
                and self._canvas._text_editing):
            return
        ColorManager.instance().reset()

    def _shortcut_brush_size(self, delta: int) -> None:
        """Increase or decrease the current tool's brush size."""
        tool = self._tools.active_tool
        if tool and hasattr(tool, 'size'):
            new_size = max(1, tool.size + delta)
            tool.size = new_size
            self._update_properties_panel()
            self._update_brush_cursor()

    def _shortcut_toggle_fullscreen(self) -> None:
        if (self._tools.active_type == ToolType.TEXT
                and self._canvas._text_editing):
            return
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _on_keyboard_shortcuts(self) -> None:
        """Open the keyboard shortcuts editor dialog."""
        from .dialogs.shortcuts_dialog import KeyboardShortcutsDialog
        dlg = KeyboardShortcutsDialog(self)
        dlg.exec()

    def _on_about(self) -> None:
        """Show the About dialog."""
        QMessageBox.about(
            self,
            "About Photo Editor",
            "<h3>Photo Editor</h3>"
            "<p>A professional raster image editor built with PySide6.</p>"
            "<p>Features include layers, masks, blending modes, "
            "filters, adjustments, and more.</p>",
        )
