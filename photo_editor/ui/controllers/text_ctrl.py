"""Text tool — editing, overlay, key handling."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor

from ...core.enums import LayerType, ToolType


class TextController:
    """Handles text tool setup, overlay, key events, and exit editing."""

    def __init__(self) -> None:
        self._mw = None

    def wire(self, main_window) -> None:
        """Connect to main window and wire panel signals."""
        self._mw = main_window
        mw = main_window

        mw._props_panel.text_property_changed.connect(self.on_text_prop_changed)

    def setup(self) -> None:
        """Wire callbacks for the text tool (called when text tool is selected)."""
        mw = self._mw
        tool = mw._tools.active_tool
        if tool is None:
            return
        tool.set_refresh_callback(self.on_refresh)
        tool.set_overlay_callback(self.update_overlay)
        mw._canvas.set_key_handler(self.on_key)

        if mw._doc and not tool.is_editing:
            layer = mw._doc.layers.active_layer
            if layer is not None and layer.layer_type == LayerType.TEXT:
                td = getattr(layer, "_text_data", None)
                if td is not None:
                    tool._start_editing(layer, mw._doc)
                    self.update_overlay()
                    mw._refresh()

    def on_text_prop_changed(self, key: str, value: object) -> None:
        mw = self._mw
        tool = mw._tools.active_tool
        if tool is None or mw._tools.active_type != ToolType.TEXT:
            return
        tool.apply_property(key, value)
        self.update_overlay()

    def on_refresh(self) -> None:
        mw = self._mw
        mw._schedule_render()
        mw._schedule_panel_refresh()
        self.update_overlay()

    def on_key(self, key: int, text: str, modifiers) -> bool:
        mw = self._mw
        tool = mw._tools.active_tool
        if tool is None or mw._tools.active_type != ToolType.TEXT:
            return False
        consumed = tool.on_key_press(key, text, modifiers)
        if consumed:
            self.update_overlay()
        return consumed

    def update_overlay(self) -> None:
        mw = self._mw
        tool = mw._tools.active_tool
        if tool is None or mw._tools.active_type != ToolType.TEXT:
            if mw._text_editing_active:
                mw._text_editing_active = False
                mw._shortcut_ctrl.update_text_editing_shortcuts(False)
            mw._canvas.set_text_editing(False)
            mw._canvas.set_text_box(None)
            mw._canvas.set_text_draw_rect(None)
            return

        if tool.is_drawing:
            if mw._text_editing_active:
                mw._text_editing_active = False
                mw._shortcut_ctrl.update_text_editing_shortcuts(False)
            mw._canvas.set_text_editing(False)
            mw._canvas.set_text_box(None)
            mw._canvas.set_text_draw_rect(tool.draw_rect)
            return

        mw._canvas.set_text_draw_rect(None)

        is_editing = (tool.is_editing and tool.text_data is not None)
        if mw._text_editing_active != is_editing:
            mw._text_editing_active = is_editing
            mw._shortcut_ctrl.update_text_editing_shortcuts(is_editing)

        if is_editing:
            td = tool.text_data
            mw._canvas.set_text_editing(True)
            box = tool.editing_box()
            angle = tool.editing_rotation()
            mw._canvas.set_text_box(box, angle)

            cx, cy = td.cursor_to_xy(td.cursor_pos)
            ch = td.cursor_line_height(td.cursor_pos)
            mw._canvas.set_text_cursor(cx, cy, ch)

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
                    sel_start_in_line = max(lo, pos) - pos
                    sel_end_in_line = min(hi, line_end) - pos
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
            mw._canvas.set_text_selection_rects(sel_rects)
            mw._canvas.set_transform_box(None)
        else:
            mw._canvas.set_text_editing(False)
            mw._canvas.set_text_box(None)
            mw._canvas.set_text_selection_rects([])

    def update_hover_cursor(self, x: int, y: int) -> None:
        mw = self._mw
        tool = mw._tools.active_tool
        if tool is None or mw._tools.active_type != ToolType.TEXT:
            return
        hint = tool.hit_test_cursor_shape(x, y)
        if hint is None or hint == "text":
            mw._canvas.setCursor(QCursor(Qt.CursorShape.IBeamCursor))
        elif hint in ("resize_tl", "resize_br"):
            mw._canvas.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        elif hint in ("resize_tr", "resize_bl"):
            mw._canvas.setCursor(QCursor(Qt.CursorShape.SizeBDiagCursor))
        elif hint in ("resize_t", "resize_b"):
            mw._canvas.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
        elif hint in ("resize_l", "resize_r"):
            mw._canvas.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        else:
            mw._canvas.setCursor(QCursor(Qt.CursorShape.IBeamCursor))

    def exit_editing(self) -> None:
        mw = self._mw
        tool = mw._tools.active_tool
        if tool is not None and hasattr(tool, "commit_editing"):
            tool.commit_editing(mw._doc)

        if mw._text_editing_active:
            mw._text_editing_active = False
            mw._shortcut_ctrl.update_text_editing_shortcuts(False)

        mw._canvas.set_text_editing(False)
        mw._canvas.set_text_box(None)
        mw._canvas.set_text_draw_rect(None)
        mw._canvas.set_text_selection_rects([])
        mw._canvas.set_key_handler(None)
