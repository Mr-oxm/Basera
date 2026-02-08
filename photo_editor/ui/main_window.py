"""Main application window — assembles all panels, menus, and canvas."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QRectF, QTimer
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
        self._menu = EditorMenuBar(self)
        self.setMenuBar(self._menu)
        self._toolbar = EditorToolbar(self)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._toolbar)
        self._canvas = CanvasView(self)
        self.setCentralWidget(self._canvas)
        self._layers_panel = LayersPanel()
        self._dock(self._layers_panel, "Layers", Qt.DockWidgetArea.RightDockWidgetArea)
        self._history_panel = HistoryPanel()
        self._dock(self._history_panel, "History", Qt.DockWidgetArea.RightDockWidgetArea)
        self._adj_panel = AdjustmentsPanel()
        self._dock(self._adj_panel, "Adjustments", Qt.DockWidgetArea.RightDockWidgetArea)
        self._props_panel = PropertiesPanel()
        self._dock(self._props_panel, "Properties", Qt.DockWidgetArea.RightDockWidgetArea)
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
        lp.visibility_toggled.connect(self._on_toggle_vis)
        lp.lock_toggled.connect(self._on_toggle_lock)
        self._history_panel.state_selected.connect(self._on_history_jump)
        self._adj_panel.adjustment_requested.connect(self._on_adjustment)
        self._color_panel.fg_changed.connect(
            lambda c: self._tools.set_foreground_color(c.to_array()),
        )
        self._props_panel.value_changed.connect(self._on_prop_changed)

    # ---- Wiring: canvas -----------------------------------------------------

    def _wire_canvas(self) -> None:
        self._canvas.cursor_moved.connect(self._status.set_cursor_pos)
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

    def _refresh(self) -> None:
        if not self._doc:
            return
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
        active = self._doc.layers.active_layer
        if active:
            self._pipeline.invalidate(active.id)
        else:
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
                lx, ly = layer.position
                self._canvas.set_transform_box((lx, ly, layer.width, layer.height))
                return
        self._canvas.set_transform_box(None)

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
        if self._doc:
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
        if self._doc and self._doc.layers.active_layer:
            self._doc.layers.active_layer.blend_mode = mode
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
                self._layers_panel.refresh(self._doc)

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

    def _on_tool_selected(self, t: ToolType) -> None:
        self._tools.select(t)
        self._status.set_tool(t.name.replace("_", " ").title())
        self._canvas.set_tool_cursor(t)
        self._update_properties_panel()
        self._update_transform_box()

    def _on_canvas_press(self, x: int, y: int, pressure: float) -> None:
        self._dragging = True
        self._tools.on_press(self._doc, x, y, pressure)
        # For selection tools, track drag start for visual feedback
        tool_type = self._tools.active_type
        if tool_type in (ToolType.RECT_SELECT, ToolType.ELLIPSE_SELECT):
            self._drag_start = (x, y)

    def _on_canvas_move(self, x: int, y: int, pressure: float) -> None:
        self._tools.on_move(self._doc, x, y, pressure)
        # Update drag rect for selection tools
        tool_type = self._tools.active_type
        if tool_type in (ToolType.RECT_SELECT, ToolType.ELLIPSE_SELECT) and hasattr(self, "_drag_start"):
            sx, sy = self._drag_start
            dr = self._canvas._doc_rect()
            zx = dr.left() + (min(sx, x) / self._canvas._doc_w) * dr.width()
            zy = dr.top() + (min(sy, y) / self._canvas._doc_h) * dr.height()
            zw = abs(x - sx) / self._canvas._doc_w * dr.width()
            zh = abs(y - sy) / self._canvas._doc_h * dr.height()
            self._canvas.set_drag_rect(QRectF(zx, zy, zw, zh))
        else:
            # Schedule throttled render for painting tools
            self._schedule_render()

    def _on_canvas_release(self, x: int, y: int) -> None:
        self._dragging = False
        self._tools.on_release(self._doc, x, y)
        self._canvas.set_drag_rect(None)
        if hasattr(self, "_drag_start"):
            del self._drag_start
        # Full refresh to sync panels + selection overlay
        self._refresh()

    # ---- Properties panel ---------------------------------------------------

    def _update_properties_panel(self) -> None:
        self._props_panel.clear()
        tool = self._tools.active_tool
        if tool is None:
            return
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

    # ---- Adjustments / Filters ----------------------------------------------

    def _on_adjustment(self, name: str) -> None:
        if self._doc and run_adjustment(name, self._doc, self):
            self._refresh()

    def _on_filter(self, key: str) -> None:
        if self._doc and run_filter(key, self._doc, self):
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
