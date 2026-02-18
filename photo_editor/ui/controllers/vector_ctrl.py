"""Vector tool — fill, stroke, shape params, node actions, key handling."""

from __future__ import annotations

from PySide6.QtCore import Qt

from ...core.enums import ToolType


class VectorController:
    """Handles vector properties bar and vector tool actions (pen, node, shape)."""

    def __init__(self) -> None:
        self._mw = None

    def wire(self, main_window) -> None:
        """Connect to main window and wire panel signals."""
        self._mw = main_window
        mw = main_window

        mw._props_panel.vector_property_changed.connect(self.on_vector_prop_changed)
        mw._props_panel.vector_action.connect(self.on_vector_action)

    def on_vector_prop_changed(self, key: str, value: object) -> None:
        mw = self._mw
        tool = mw._tools.active_tool
        if tool is None:
            return
        tt = mw._tools.active_type

        if key == "fill_color" and isinstance(value, tuple):
            tool.fill_color = value
        elif key == "stroke_color" and isinstance(value, tuple):
            tool.stroke_color = value
        elif key == "stroke_width":
            tool.stroke_width = float(value)
        elif key == "shape_type" and tt == ToolType.VECTOR_SHAPE:
            from ...vector.shape_tool import VectorShapeType
            name = str(value).upper().replace(" ", "_")
            try:
                tool.shape_type = VectorShapeType[name]
            except KeyError:
                pass
            mw._props_panel.vector_bar.set_shape_type(str(value))
        elif key == "param_a" and tt == ToolType.VECTOR_SHAPE:
            self._set_shape_param_a(tool, float(value))
        elif key == "param_b" and tt == ToolType.VECTOR_SHAPE:
            self._set_shape_param_b(tool, float(value))
        elif key == "fill_paint":
            tool.fill_paint = value
        elif key == "stroke_paint":
            tool.stroke_paint = value

        if key in ("fill_color", "stroke_color", "stroke_width", "fill_paint", "stroke_paint"):
            self._apply_style_to_selected_objects(key, value)

    def _apply_style_to_selected_objects(self, key: str, value: object) -> None:
        mw = self._mw
        doc = mw._doc
        if doc is None:
            return

        from ...vector.style import SolidPaint, GradientPaint
        from ...vector.rasterizer import rasterize_vector_layer_tight

        any_changed = False
        for layer in doc.layers.layers:
            vl = getattr(layer, "_vector_data", None)
            if vl is None:
                continue

            changed = False
            for obj in vl.objects:
                if not obj.selected:
                    continue
                if key == "fill_color" and isinstance(value, tuple):
                    for fill in obj.style.fills:
                        if isinstance(fill.paint, SolidPaint):
                            fill.paint.color = value
                            changed = True
                elif key == "stroke_color" and isinstance(value, tuple):
                    for stroke in obj.style.strokes:
                        if isinstance(stroke.paint, SolidPaint):
                            stroke.paint.color = value
                            changed = True
                elif key == "stroke_width":
                    for stroke in obj.style.strokes:
                        stroke.width = float(value)
                        changed = True
                elif key == "fill_paint":
                    paint = value
                    if isinstance(paint, GradientPaint):
                        paint = self._gradient_to_object_space(paint, obj)
                    if obj.style.fills:
                        obj.style.fills[0].paint = paint
                    else:
                        obj.style.add_fill()
                        obj.style.fills[0].paint = paint
                    obj.invalidate()
                    changed = True
                elif key == "stroke_paint":
                    paint = value
                    if isinstance(paint, GradientPaint):
                        paint = self._gradient_to_object_space(paint, obj)
                    if obj.style.strokes:
                        obj.style.strokes[0].paint = paint
                    else:
                        obj.style.add_stroke()
                        obj.style.strokes[0].paint = paint
                    obj.invalidate()
                    changed = True

            if changed:
                any_changed = True
                rasterize_vector_layer_tight(doc, layer=layer)

        if any_changed:
            mw._schedule_render()

    def _gradient_to_object_space(self, paint, obj):
        """Set gradient start/end to cover the object's bounding box."""
        from ...vector.style import GradientPaint, GradientType
        from ...vector.geometry import Vec2

        bb = obj.local_bbox()
        if bb.is_empty:
            return paint
        if paint.gradient_type == GradientType.LINEAR:
            return GradientPaint(
                gradient_type=GradientType.LINEAR,
                stops=paint.stops,
                start=Vec2(bb.min_pt.x, bb.min_pt.y),
                end=Vec2(bb.max_pt.x, bb.max_pt.y),
            )
        cx = (bb.min_pt.x + bb.max_pt.x) / 2
        cy = (bb.min_pt.y + bb.max_pt.y) / 2
        r = max(bb.width, bb.height) / 2
        return GradientPaint(
            gradient_type=GradientType.RADIAL,
            stops=paint.stops,
            start=Vec2(cx, cy),
            end=Vec2(cx, cy),
            radius=r,
        )

    def _set_shape_param_a(self, tool, val: float) -> None:
        from ...vector.shape_tool import VectorShapeType
        _map = {
            VectorShapeType.RECTANGLE: "corner_radius",
            VectorShapeType.POLYGON: "polygon_sides",
            VectorShapeType.STAR: "star_points",
            VectorShapeType.ARROW: "arrow_head_length",
            VectorShapeType.CROSS: "cross_arm_ratio",
            VectorShapeType.RING: "ring_thickness",
            VectorShapeType.TRAPEZOID: "trapezoid_top_ratio",
            VectorShapeType.PARALLELOGRAM: "parallelogram_skew",
            VectorShapeType.CRESCENT: "crescent_offset",
            VectorShapeType.SPEECH_BUBBLE: "speech_tail_position",
        }
        attr = _map.get(tool.shape_type)
        if attr:
            if attr in ("polygon_sides", "star_points"):
                setattr(tool, attr, max(3, int(val)))
            else:
                setattr(tool, attr, val)

    def _set_shape_param_b(self, tool, val: float) -> None:
        from ...vector.shape_tool import VectorShapeType
        _map = {
            VectorShapeType.STAR: "star_inner_ratio",
            VectorShapeType.ARROW: "arrow_shaft_width",
        }
        attr = _map.get(tool.shape_type)
        if attr:
            setattr(tool, attr, val)

    def on_vector_action(self, action: str) -> None:
        mw = self._mw
        tool = mw._tools.active_tool
        if tool is None or mw._doc is None:
            return
        tt = mw._tools.active_type
        if tt == ToolType.NODE:
            if action == "delete_nodes":
                tool.delete_selected_nodes(mw._doc)
            elif action == "break_path":
                tool.break_path_at_node(mw._doc)
            elif action == "toggle_mode":
                tool.toggle_node_mode(mw._doc)
            elif action == "set_sharp":
                from ...vector.path import HandleMode
                tool.set_node_mode(mw._doc, HandleMode.SHARP)
            elif action == "set_smooth":
                from ...vector.path import HandleMode
                tool.set_node_mode(mw._doc, HandleMode.SMOOTH)
            elif action == "set_symmetric":
                from ...vector.path import HandleMode
                tool.set_node_mode(mw._doc, HandleMode.SYMMETRIC)
            elif action == "select_all":
                tool.select_all_nodes(mw._doc)
            mw._schedule_render()
            mw._canvas.update()

    def handle_key_press(self, key: int, event) -> bool:
        """Handle Pen/Node tool keys. Returns True if the key was consumed."""
        mw = self._mw
        tool_type = mw._tools.active_type
        tool = mw._tools.active_tool
        if tool is None:
            return False

        if tool_type == ToolType.PEN:
            if key in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if hasattr(tool, "finish_open_path"):
                    tool.finish_open_path(mw._doc)
                    mw._refresh()
                    event.accept()
                    return True

        if tool_type == ToolType.NODE:
            if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                if hasattr(tool, "delete_selected_nodes"):
                    tool.delete_selected_nodes(mw._doc)
                    mw._refresh()
                    event.accept()
                    return True
            if key == Qt.Key.Key_Tab:
                if hasattr(tool, "toggle_node_mode"):
                    tool.toggle_node_mode(mw._doc)
                    mw._refresh()
                    event.accept()
                    return True

        return False
