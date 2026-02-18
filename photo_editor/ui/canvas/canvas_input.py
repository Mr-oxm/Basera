"""Canvas mouse and keyboard event handling."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QKeyEvent, QMouseEvent, QWheelEvent

from ...core.enums import ToolType
from .canvas_cursors import build_source_cursor

if TYPE_CHECKING:
    from ..canvas_view import CanvasView  # noqa: F401


class CanvasInputHandler:
    """Handles mouse and keyboard events for the canvas."""

    def __init__(self, canvas: "CanvasView") -> None:
        self._canvas = canvas

    def handle_wheel(self, event: QWheelEvent) -> None:
        """Handle zoom via scroll wheel."""
        c = self._canvas
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        c._zoom = max(0.01, min(c._zoom * factor, 32.0))
        c.update()
        c.view_changed.emit()

    def handle_mouse_press(self, event: QMouseEvent) -> bool:
        """Handle mouse press. Returns True if fully handled (no further processing)."""
        c = self._canvas
        if event.button() == Qt.MouseButton.MiddleButton:
            c._panning = True
            c._last_mouse = event.position()
            c.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            return True
        if event.button() == Qt.MouseButton.LeftButton:
            hit_guide = c._hit_test_guide(event.position())
            if hit_guide is not None:
                c._dragging_canvas_guide = hit_guide
                c.guide_grabbed.emit(hit_guide)
                c.setCursor(QCursor(
                    Qt.CursorShape.SplitVCursor if hit_guide.orientation == Qt.Orientation.Horizontal
                    else Qt.CursorShape.SplitHCursor
                ))
                return True
            pos = event.position()
            c.widget_pressed.emit(pos.x(), pos.y())
            dx, dy = c._canvas_to_doc(pos)
            c.tool_pressed.emit(dx, dy, 1.0)
            return True
        return False

    def handle_mouse_move(self, event: QMouseEvent) -> bool:
        """Handle mouse move. Returns True if fully handled."""
        c = self._canvas
        if c._panning:
            delta = event.position() - c._last_mouse
            c._pan += delta
            c._last_mouse = event.position()
            c.update()
            c.view_changed.emit()
            return True

        if c._dragging_canvas_guide is not None:
            g = c._dragging_canvas_guide
            dr = c._doc_rect()
            if g.orientation == Qt.Orientation.Horizontal:
                sy = dr.height() / c._doc_h if c._doc_h else 1
                doc_pos = (event.position().y() - dr.top()) / sy if sy else 0
            else:
                sx = dr.width() / c._doc_w if c._doc_w else 1
                doc_pos = (event.position().x() - dr.left()) / sx if sx else 0
            g.position = doc_pos
            c.guide_drag_moved.emit(g, doc_pos)
            c.update()
            return True

        dx, dy = c._canvas_to_doc(event.position())
        c.cursor_moved.emit(dx, dy)

        if c._brush_size > 0:
            c._brush_cursor_pos = event.position()
            c._brush_cursor_visible = True
            if (c._source_pos is not None
                    and c._current_tool_type in (ToolType.CLONE_STAMP, ToolType.HEALING_BRUSH)):
                c.update()
            else:
                radius = int((c._brush_size / 2) * c._zoom) + 4
                cx, cy = int(event.position().x()), int(event.position().y())
                c.update(cx - radius, cy - radius, radius * 2, radius * 2)

        if event.buttons() & Qt.MouseButton.LeftButton:
            c.widget_moved.emit(event.position().x(), event.position().y())
            c.tool_moved.emit(dx, dy, 1.0)
        elif c._transform_box is not None:
            c._update_transform_cursor(event.position())

        return True

    def handle_mouse_release(self, event: QMouseEvent) -> bool:
        """Handle mouse release. Returns True if fully handled."""
        c = self._canvas
        if event.button() == Qt.MouseButton.MiddleButton:
            c._panning = False
            c.set_tool_cursor(c._current_tool_type)
            return True
        if event.button() == Qt.MouseButton.LeftButton:
            if c._dragging_canvas_guide is not None:
                g = c._dragging_canvas_guide
                dr = c._doc_rect()
                if g.orientation == Qt.Orientation.Horizontal:
                    sy = dr.height() / c._doc_h if c._doc_h else 1
                    doc_pos = (event.position().y() - dr.top()) / sy if sy else 0
                    delete = event.position().y() < dr.top() - 20
                else:
                    sx = dr.width() / c._doc_w if c._doc_w else 1
                    doc_pos = (event.position().x() - dr.left()) / sx if sx else 0
                    delete = event.position().x() < dr.left() - 20
                g.position = doc_pos
                c.guide_drag_released.emit(g, doc_pos, delete)
                c._dragging_canvas_guide = None
                c.unsetCursor()
                return True
            c.widget_released.emit()
            dx, dy = c._canvas_to_doc(event.position())
            c.tool_released.emit(dx, dy)
            c._drag_rect = None
            return True
        return False

    def handle_mouse_double_click(self, event: QMouseEvent) -> bool:
        """Handle mouse double-click. Returns True if handled."""
        if event.button() == Qt.MouseButton.LeftButton:
            c = self._canvas
            dx, dy = c._canvas_to_doc(event.position())
            c.tool_double_clicked.emit(dx, dy)
            return True
        return False

    def handle_leave(self) -> None:
        """Handle mouse leave."""
        c = self._canvas
        c._brush_cursor_visible = False
        c.update()

    def handle_enter(self) -> None:
        """Handle mouse enter."""
        c = self._canvas
        if c._brush_size > 0:
            c._brush_cursor_visible = True
            c.update()

    def handle_key_press(self, event: QKeyEvent) -> bool:
        """Handle key press. Returns True if consumed (don't pass to super)."""
        c = self._canvas
        if event.key() == Qt.Key.Key_Alt:
            if c._current_tool_type in (ToolType.CLONE_STAMP, ToolType.HEALING_BRUSH):
                c._alt_held = True
                c.setCursor(build_source_cursor())
                event.accept()
                return True
        if c._key_handler is not None and c._text_editing:
            consumed = c._key_handler(event.key(), event.text(), event.modifiers())
            if consumed:
                event.accept()
                return True
        return False

    def handle_key_release(self, event: QKeyEvent) -> bool:
        """Handle key release. Returns True if consumed."""
        c = self._canvas
        if event.key() == Qt.Key.Key_Alt and c._alt_held:
            c._alt_held = False
            if c._brush_size > 0:
                c.setCursor(QCursor(Qt.CursorShape.BlankCursor))
            else:
                c.set_tool_cursor(c._current_tool_type)
            event.accept()
            return True
        return False
