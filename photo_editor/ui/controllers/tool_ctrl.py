"""Tool selection, properties panel, eyedropper, pan, brush cursor, clone preview."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt

from ...core.enums import ToolType


class ToolController:
    """Handles tool selection, properties panel, eyedropper, pan widget, brush cursor, clone preview."""

    BRUSH_CURSOR_TOOLS = {
        ToolType.BRUSH, ToolType.ERASER,
        ToolType.CLONE_STAMP, ToolType.HEALING_BRUSH,
    }

    def __init__(self) -> None:
        self._mw = None

    def wire(self, main_window) -> None:
        """Connect to main window and wire toolbar/panel/canvas signals."""
        self._mw = main_window
        mw = main_window

        mw._toolbar.tool_selected.connect(self.on_tool_selected)
        mw._props_panel.value_changed.connect(self.on_prop_changed)
        mw._props_panel.brush_property_changed.connect(self.on_brush_prop_changed)

        mw._canvas.widget_pressed.connect(self.on_widget_press)
        mw._canvas.widget_moved.connect(self.on_widget_move)
        mw._canvas.widget_released.connect(self.on_widget_release)

    def on_tool_selected(self, t: ToolType) -> None:
        mw = self._mw
        if mw._tools.active_type == ToolType.TEXT and t != ToolType.TEXT:
            mw._text_ctrl.exit_editing()
        if mw._tools.active_type == ToolType.MOVE and t != ToolType.MOVE:
            tool = mw._tools.active_tool
            if tool is not None and getattr(tool, '_floating', False):
                tool.commit_float(mw._doc)
                mw._selection_ctrl.update_selection_overlay()
        if (mw._tools.active_type in (ToolType.CLONE_STAMP, ToolType.HEALING_BRUSH)
                and t not in (ToolType.CLONE_STAMP, ToolType.HEALING_BRUSH)):
            mw._canvas.set_source_position(None)
            mw._canvas.set_source_drawing(False)
            mw._canvas.set_clone_preview(None)
        mw._tools.select(t)
        mw._status.set_tool(t.name.replace("_", " ").title())
        mw._canvas.set_tool_cursor(t)

        if t == ToolType.NODE and mw._doc and mw._doc.layers.active_layer:
            vl = getattr(mw._doc.layers.active_layer, "_vector_data", None)
            if vl and not vl.selected_objects() and vl.objects:
                vl.objects[-1].selected = True
                mw._refresh()

        self.update_properties_panel()
        mw._transform_ctrl.update_transform_box()
        self.update_brush_cursor()

        # Ensure boolean toolbar state is correct when entering Node tool
        if t == ToolType.NODE:
            mw._vector_ctrl.refresh_bool_state()
        if t in (ToolType.CLONE_STAMP, ToolType.HEALING_BRUSH):
            tool = mw._tools.active_tool
            if tool is not None and tool.source_set:
                mw._canvas.set_source_position((tool.source_x, tool.source_y))
        if t == ToolType.TEXT:
            mw._text_ctrl.setup()
        if t == ToolType.GRADIENT:
            mw._gradient_ctrl.setup()
        if t == ToolType.EYEDROPPER:
            tool = mw._tools.active_tool
            if tool is not None:
                tool.set_color_callback(self.on_eyedropper_sample)
        if t == ToolType.ZOOM:
            tool = mw._tools.active_tool
            if tool is not None:
                tool.set_zoom_callback(mw._view_ctrl.on_zoom_tool)
        if t == ToolType.PAN:
            tool = mw._tools.active_tool
            if tool is not None:
                tool.set_pan_callback(mw._view_ctrl.on_pan_tool)
        if t == ToolType.CROP:
            mw._crop_ctrl.setup()

    def on_eyedropper_sample(self, rgba) -> None:
        from ...core.color import Color
        mw = self._mw
        mw._tools.set_foreground_color(rgba)
        if hasattr(mw, "_color_panel"):
            c = Color.from_array(rgba)
            mw._color_panel._mgr.foreground = c

    def on_widget_press(self, wx: float, wy: float) -> None:
        mw = self._mw
        if mw._tools.active_type == ToolType.PAN:
            tool = mw._tools.active_tool
            if tool is not None:
                tool.begin_pan(wx, wy)

    def on_widget_move(self, wx: float, wy: float) -> None:
        mw = self._mw
        if mw._tools.active_type == ToolType.PAN:
            tool = mw._tools.active_tool
            if tool is not None:
                tool.update_pan(wx, wy)

    def on_widget_release(self) -> None:
        mw = self._mw
        if mw._tools.active_type == ToolType.PAN:
            tool = mw._tools.active_tool
            if tool is not None:
                tool.end_pan()

    def update_properties_panel(self) -> None:
        mw = self._mw
        tool_type = mw._tools.active_type
        tool = mw._tools.active_tool
        if tool is None:
            mw._props_panel.clear()
            mw._props_panel.set_text_mode(False)
            return

        if tool_type == ToolType.MOVE:
            mw._props_panel.clear()
            mw._props_panel.set_move_mode(True)
            return
        if tool_type == ToolType.CROP:
            mw._props_panel.clear()
            mw._props_panel.set_crop_mode(True, tool)
            return
        if tool_type == ToolType.ZOOM:
            mw._props_panel.clear()
            mw._props_panel.set_zoom_mode(True)
            return
        _SEL_TOOLS = {ToolType.RECT_SELECT, ToolType.ELLIPSE_SELECT,
                      ToolType.LASSO, ToolType.MAGIC_WAND}
        if tool_type in _SEL_TOOLS:
            mw._props_panel.clear()
            is_wand = (tool_type == ToolType.MAGIC_WAND)
            mw._props_panel.set_selection_mode(True, tool, is_wand=is_wand)
            return
        if tool_type == ToolType.TEXT:
            mw._props_panel.clear()
            mw._props_panel.set_text_mode(True, tool)
            return
        if tool_type == ToolType.GRADIENT:
            mw._props_panel.clear()
            mw._props_panel.set_gradient_mode(True, tool)
            return
        _VEC_TOOLS = {ToolType.PEN: "pen", ToolType.NODE: "node",
                      ToolType.VECTOR_SHAPE: "shape"}
        if tool_type in _VEC_TOOLS:
            mw._props_panel.clear()
            active_object = None
            if mw._doc and mw._doc.layers.active_layer:
                vl = getattr(mw._doc.layers.active_layer, "_vector_data", None)
                if vl:
                    objs = vl.selected_objects()
                    if objs:
                        active_object = objs[0]
            mw._props_panel.set_vector_mode(True, tool, mode=_VEC_TOOLS[tool_type], active_object=active_object)
            return

        # Brush-type tools use specialised bar
        _BRUSH_TOOLS = {ToolType.BRUSH, ToolType.ERASER,
                        ToolType.CLONE_STAMP, ToolType.HEALING_BRUSH}
        if tool_type in _BRUSH_TOOLS:
            mw._props_panel.clear()
            mw._props_panel.set_brush_mode(True, tool)
            return

        mw._props_panel.set_text_mode(False)
        mw._props_panel.set_gradient_mode(False)
        mw._props_panel.set_move_mode(False)
        mw._props_panel.set_crop_mode(False)
        mw._props_panel.set_zoom_mode(False)
        mw._props_panel.set_selection_mode(False)
        mw._props_panel.set_vector_mode(False)
        mw._props_panel.set_brush_mode(False)
        mw._props_panel.clear()
        mw._props_panel.set_title(f"{tool.name} Properties")
        for key, (val, lo, hi) in mw._tools.get_properties().items():
            label = key.replace("_", " ").title()
            if isinstance(val, float) and hi <= 1:
                mw._props_panel.add_slider(key, label, int(val * 100), int(lo * 100), int(hi * 100))
            else:
                mw._props_panel.add_slider(key, label, int(val), int(lo), int(hi))

    def on_prop_changed(self, key: str, value: object) -> None:
        mw = self._mw
        props = mw._tools.get_properties()
        if key in props:
            _, lo, hi = props[key]
            if isinstance(lo, float) and hi <= 1:
                mw._tools.set_property(key, float(value) / 100.0)
            else:
                mw._tools.set_property(key, float(value))
        if key in ("size", "hardness", "opacity", "flow"):
            self.update_brush_cursor()

    def on_brush_prop_changed(self, key: str, value: object) -> None:
        """Handle property changes from the brush properties bar."""
        mw = self._mw
        tool = mw._tools.active_tool
        if tool is None:
            return
        if key == "blend_mode":
            # Store blend mode on the tool (informational for now)
            return
        if key == "rotation":
            # Rotation is informational for preset-based brushes
            return
        if hasattr(tool, key):
            if isinstance(getattr(tool, key), int):
                setattr(tool, key, int(value))
            else:
                setattr(tool, key, float(value))
        if key in ("size", "hardness", "opacity", "flow"):
            self.update_brush_cursor()

    def apply_brush_preset(self, preset) -> None:
        """Apply a brush preset's settings to the current brush-type tool."""
        mw = self._mw
        tool = mw._tools.active_tool
        if tool is None:
            return
        if hasattr(tool, "size"):
            tool.size = preset.size
        if hasattr(tool, "hardness"):
            tool.hardness = preset.hardness
        if hasattr(tool, "spacing"):
            tool.spacing = preset.spacing
        if hasattr(tool, "opacity"):
            tool.opacity = preset.opacity
        if hasattr(tool, "flow"):
            tool.flow = preset.flow
        # Re-sync the properties bar
        self.update_properties_panel()
        self.update_brush_cursor()

    def update_brush_cursor(self) -> None:
        mw = self._mw
        tool_type = mw._tools.active_type
        if tool_type in self.BRUSH_CURSOR_TOOLS:
            tool = mw._tools.active_tool
            if tool is None:
                mw._canvas.hide_brush_preview()
                return
            dab = tool.generate_preview_dab() if hasattr(tool, "generate_preview_dab") else None
            if dab is not None:
                is_eraser = tool_type == ToolType.ERASER
                mw._canvas.set_brush_dab(dab, is_eraser=is_eraser)
            else:
                mw._canvas.hide_brush_preview()
            mw._canvas.setCursor(Qt.CursorShape.BlankCursor)
        else:
            mw._canvas.hide_brush_preview()

    def update_clone_preview(self, cursor_x: int, cursor_y: int) -> None:
        mw = self._mw
        tool = mw._tools.active_tool
        if tool is None or not getattr(tool, "source_set", False):
            mw._canvas.set_clone_preview(None)
            return
        if mw._doc is None:
            return
        layer = mw._doc.layers.active_layer
        if layer is None:
            mw._canvas.set_clone_preview(None)
            return

        lx, ly = layer.position
        pixels = layer.pixels
        h, w = pixels.shape[:2]
        radius = max(1, tool.size // 2)

        if tool._offset_locked:
            ox, oy = tool._offset_x, tool._offset_y
        else:
            ox = tool.source_x - cursor_x
            oy = tool.source_y - cursor_y

        cx_doc = cursor_x - lx
        cy_doc = cursor_y - ly
        sx_doc = cx_doc + ox
        sy_doc = cy_doc + oy

        d = radius * 2 + 1
        preview = np.zeros((d, d, 4), dtype=np.uint8)
        y0s = sy_doc - radius
        x0s = sx_doc - radius
        cy0 = max(0, -y0s)
        cx0 = max(0, -x0s)
        cy1 = min(d, h - y0s)
        cx1 = min(d, w - x0s)
        if cy1 <= cy0 or cx1 <= cx0:
            mw._canvas.set_clone_preview(None)
            return

        src = pixels[y0s + cy0:y0s + cy1, x0s + cx0:x0s + cx1]
        patch = np.clip(src * 255, 0, 255).astype(np.uint8)

        yy, xx = np.mgrid[cy0:cy1, cx0:cx1]
        dist = np.sqrt((xx - radius) ** 2 + (yy - radius) ** 2).astype(np.float32)
        mask = np.clip(1.0 - dist / max(radius, 1), 0, 1)
        hardness = getattr(tool, "hardness", 0.7)
        mask = mask ** (1.0 / max(hardness, 0.01))
        mask[dist > radius] = 0.0

        preview[cy0:cy1, cx0:cx1, :3] = patch[..., :3]
        preview[cy0:cy1, cx0:cx1, 3] = np.clip(mask * 200, 0, 255).astype(np.uint8)

        mw._canvas.set_clone_preview(preview)
