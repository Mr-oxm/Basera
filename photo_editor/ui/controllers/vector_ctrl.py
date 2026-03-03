"""Vector tool — fill, stroke, shape params, node actions, key handling."""

from __future__ import annotations

from PySide6.QtCore import Qt

from ...core.enums import ToolType


class VectorController:
    """Handles vector properties bar and vector tool actions (pen, node, shape)."""

    # Map action string → BooleanOp enum member name
    _BOOL_OP_MAP = {
        "bool_union": "UNION",
        "bool_subtract": "SUBTRACT",
        "bool_intersect": "INTERSECT",
        "bool_exclude": "EXCLUDE",
        "bool_divide": "DIVIDE",
    }

    def __init__(self) -> None:
        self._mw = None

    def wire(self, main_window) -> None:
        """Connect to main window and wire panel signals."""
        self._mw = main_window
        mw = main_window

        mw._props_panel.vector_property_changed.connect(self.on_vector_prop_changed)
        mw._props_panel.vector_action.connect(self.on_vector_action)

        # Boolean hover preview wiring
        mw._props_panel.vector_boolean_hover.connect(self._on_bool_hover)
        mw._props_panel.vector_boolean_hover_end.connect(self._on_bool_hover_end)

        # Wire boolean selection callback on the node tool once it's created.
        # We install the callback every time the node tool becomes active; see
        # refresh_bool_state() which is called from on_vector_action and the
        # tool_changed path in main_window.
        self._install_bool_callback()

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
        elif key == "fill_none":
            tool.fill_none = bool(value)
        elif key == "stroke_none":
            tool.stroke_none = bool(value)

        if key in ("fill_color", "stroke_color", "stroke_width",
                   "fill_paint", "stroke_paint", "fill_none", "stroke_none"):
            self._apply_style_to_selected_objects(key, value)

    def _apply_style_to_selected_objects(self, key: str, value: object) -> None:
        mw = self._mw
        if mw is None:
            return
        doc = mw._doc
        if doc is None:
            return

        from ...vector.style import SolidPaint, GradientPaint
        from ...vector.rasterizer import rasterize_vector_layer_tight

        selected_layer_ids = set()
        if hasattr(mw, "_layers_panel"):
            selected_layer_ids = set(mw._layers_panel.selected_layer_ids())
        else:
            if doc.layers.active_layer:
                selected_layer_ids.add(doc.layers.active_layer.id)

        any_changed = False
        for layer in doc.layers.layers:
            if layer.id not in selected_layer_ids:
                continue

            vl = getattr(layer, "_vector_data", None)
            if vl is None:
                continue

            changed = False
            for obj in vl.objects:
                if not obj.selected:
                    continue
                if key == "fill_color" and isinstance(value, tuple):
                    if not obj.style.fills:
                        obj.style.add_fill()
                    for fill in obj.style.fills:
                        if isinstance(fill.paint, SolidPaint):
                            fill.paint.color = value
                        else:
                            fill.paint = SolidPaint(color=value)
                        changed = True
                elif key == "stroke_color" and isinstance(value, tuple):
                    if not obj.style.strokes:
                        obj.style.add_stroke()
                    for stroke in obj.style.strokes:
                        if isinstance(stroke.paint, SolidPaint):
                            stroke.paint.color = value
                        else:
                            stroke.paint = SolidPaint(color=value)
                        changed = True
                elif key == "stroke_width":
                    for stroke in obj.style.strokes:
                        stroke.width = float(value)
                        changed = True
                elif key == "fill_paint":
                    paint = value
                    if isinstance(paint, GradientPaint):
                        paint = self._gradient_to_object_space(paint, obj)
                    elif hasattr(paint, "color"):
                        import copy
                        paint = copy.deepcopy(paint)
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
                    elif hasattr(paint, "color"):
                        import copy
                        paint = copy.deepcopy(paint)
                    if obj.style.strokes:
                        obj.style.strokes[0].paint = paint
                    else:
                        obj.style.add_stroke()
                        obj.style.strokes[0].paint = paint
                    obj.invalidate()
                    changed = True

                elif key == "fill_none":
                    # Toggle fill visibility (keep the paint intact)
                    is_none = bool(value)
                    if obj.style.fills:
                        for fill in obj.style.fills:
                            fill.visible = not is_none
                    else:
                        # No fills yet — add a default one if re-enabling
                        if not is_none:
                            from ...vector.style import VectorFill, SolidPaint
                            obj.style.fills.append(VectorFill(SolidPaint((0.8, 0.8, 0.8, 1.0))))
                    obj.invalidate()
                    changed = True
                elif key == "stroke_none":
                    # Toggle stroke visibility (keep the paint intact)
                    is_none = bool(value)
                    if obj.style.strokes:
                        for stroke in obj.style.strokes:
                            stroke.visible = not is_none
                    else:
                        # No strokes yet — add a default one if re-enabling
                        if not is_none:
                            from ...vector.style import VectorStroke, SolidPaint
                            obj.style.strokes.append(VectorStroke(SolidPaint((0.0, 0.0, 0.0, 1.0)), width=1.0))
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
        import copy

        bb = obj.local_bbox()
        if bb.is_empty:
            return paint
            
        stops = copy.deepcopy(paint.stops)
        if paint.gradient_type == GradientType.LINEAR:
            return GradientPaint(
                gradient_type=GradientType.LINEAR,
                stops=stops,
                start=Vec2(bb.min_pt.x, bb.min_pt.y),
                end=Vec2(bb.max_pt.x, bb.max_pt.y),
            )
        cx = (bb.min_pt.x + bb.max_pt.x) / 2
        cy = (bb.min_pt.y + bb.max_pt.y) / 2
        r = max(bb.width, bb.height) / 2
        return GradientPaint(
            gradient_type=GradientType.RADIAL,
            stops=stops,
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

        # ---- Boolean operations ----
        if action in self._BOOL_OP_MAP:
            if tt == ToolType.NODE:
                result = tool.do_boolean(mw._doc, action)
                if result is not None:
                    mw._refresh()
                self._clear_bool_preview()
            return

        # ---- Pick-segments mode ----
        if action == "pick_segments_enter":
            if tt == ToolType.NODE:
                ok = tool.enter_pick_segments(mw._doc)
                if ok:
                    mw._props_panel.vector_bar.enter_pick_segments()
                    # Expose pick_segments state to canvas for overlay
                    mw._canvas._pick_segments_state = tool.pick_segments
                    mw._canvas.update()
                else:
                    # Uncheck the button — enter failed
                    mw._props_panel.vector_bar.exit_pick_segments()
            return

        if action == "pick_segments_apply":
            if tt == ToolType.NODE:
                new_ids = tool.apply_pick_segments(mw._doc)
                mw._props_panel.vector_bar.exit_pick_segments()
                mw._canvas._pick_segments_state = None
                if new_ids:
                    mw._refresh()
                else:
                    mw._canvas.update()
            return

        if action == "pick_segments_cancel":
            if tt == ToolType.NODE:
                tool.cancel_pick_segments()
                mw._props_panel.vector_bar.exit_pick_segments()
                mw._canvas._pick_segments_state = None
                mw._canvas.update()
            return

        # ---- Node actions (existing) ----
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

    # ---- Boolean hover preview -------------------------------------------

    def _on_bool_hover(self, action: str) -> None:
        """Compute and show a boolean result preview on the canvas."""
        mw = self._mw
        if mw is None or mw._doc is None:
            return
        tool = mw._tools.active_tool
        if tool is None or mw._tools.active_type != ToolType.NODE:
            return

        op_name = self._BOOL_OP_MAP.get(action)
        if op_name is None:
            return

        from ...vector.boolean import BooleanOp
        from ...vector.boolean_ops import compute_preview_path

        op = BooleanOp[op_name]
        ids = list(tool._bool_selected_layer_ids)
        preview = compute_preview_path(mw._doc, ids, op)
        mw._canvas._bool_preview_path = preview
        mw._canvas._bool_source_ids = set(ids)
        mw._canvas.update()

    def _on_bool_hover_end(self) -> None:
        self._clear_bool_preview()

    def _clear_bool_preview(self) -> None:
        mw = self._mw
        if mw is None:
            return
        mw._canvas._bool_preview_path = None
        mw._canvas._bool_source_ids = set()
        mw._canvas.update()

    # ---- Boolean selection callback --------------------------------------

    def _install_bool_callback(self) -> None:
        """Install the selection-changed callback on the node tool if present."""
        mw = self._mw
        if mw is None:
            return
        tool = mw._tools.active_tool
        if tool is None or mw._tools.active_type != ToolType.NODE:
            return
        if hasattr(tool, "on_bool_selection_changed"):
            tool.on_bool_selection_changed = self._refresh_bool_toolbar

    def refresh_bool_state(self) -> None:
        """Public entry: (re-)install callback & refresh toolbar state.

        Call this whenever the Node tool becomes active.
        """
        self._install_bool_callback()
        self._refresh_bool_toolbar()

    def _refresh_bool_toolbar(self) -> None:
        """Push current multi-layer selection count into the vector bar."""
        mw = self._mw
        if mw is None or mw._doc is None:
            return
        tool = mw._tools.active_tool
        if tool is None or mw._tools.active_type != ToolType.NODE:
            return
        count = tool.bool_selected_count()
        first, second = "", ""
        if count >= 2:
            first, second = tool.bool_layer_names(mw._doc)
        mw._props_panel.vector_bar.update_boolean_state(count, first, second)

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
            # ---- Pick-segments cancel on Escape ----
            if key == Qt.Key.Key_Escape:
                if hasattr(tool, "pick_segments") and tool.pick_segments.active:
                    self.on_vector_action("pick_segments_cancel")
                    event.accept()
                    return True

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

            # ---- Boolean keyboard shortcuts (Ctrl+Shift + letter) ----
            from PySide6.QtWidgets import QApplication
            mods = QApplication.keyboardModifiers()
            ctrl_shift = (Qt.KeyboardModifier.ControlModifier
                          | Qt.KeyboardModifier.ShiftModifier)
            if mods & ctrl_shift == ctrl_shift:
                _key_map = {
                    Qt.Key.Key_U: "bool_union",
                    Qt.Key.Key_S: "bool_subtract",
                    Qt.Key.Key_I: "bool_intersect",
                    Qt.Key.Key_E: "bool_exclude",
                    Qt.Key.Key_D: "bool_divide",
                }
                action = _key_map.get(key)
                if action:
                    self.on_vector_action(action)
                    event.accept()
                    return True

        return False
