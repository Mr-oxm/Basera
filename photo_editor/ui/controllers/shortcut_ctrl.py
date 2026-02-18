"""Keyboard shortcuts — tool switching, colors, brush size, fullscreen."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut

from ...core.color_engine import ColorManager
from ...core.enums import ToolType


TOOL_SHORTCUT_MAP = {
    "tool_move": ToolType.MOVE,
    "tool_rect_select": ToolType.RECT_SELECT,
    "tool_ellipse_select": ToolType.ELLIPSE_SELECT,
    "tool_lasso": ToolType.LASSO,
    "tool_magic_wand": ToolType.MAGIC_WAND,
    "tool_crop": ToolType.CROP,
    "tool_eyedropper": ToolType.EYEDROPPER,
    "tool_healing_brush": ToolType.HEALING_BRUSH,
    "tool_clone_stamp": ToolType.CLONE_STAMP,
    "tool_brush": ToolType.BRUSH,
    "tool_eraser": ToolType.ERASER,
    "tool_gradient": ToolType.GRADIENT,
    "tool_paint_bucket": ToolType.PAINT_BUCKET,
    "tool_text": ToolType.TEXT,
    "tool_shape": ToolType.SHAPE,
    "tool_pen": ToolType.PEN,
    "tool_node": ToolType.NODE,
    "tool_vector_shape": ToolType.VECTOR_SHAPE,
    "tool_zoom": ToolType.ZOOM,
    "tool_pan": ToolType.PAN,
}

TOOL_CYCLE_GROUPS: list[tuple[ToolType, ...]] = [
    (ToolType.RECT_SELECT, ToolType.ELLIPSE_SELECT),
]


class ShortcutController:
    """Handles QShortcut creation and callbacks for tools, colors, brush size, fullscreen."""

    def __init__(self) -> None:
        self._mw = None
        self._active_shortcuts: list[QShortcut] = []

    def wire(self, main_window) -> None:
        self._mw = main_window
        self._rebuild_shortcuts()
        main_window._shortcut_mgr.shortcuts_changed.connect(self._rebuild_shortcuts)

    def _rebuild_shortcuts(self) -> None:
        mw = self._mw
        for sc in self._active_shortcuts:
            sc.setEnabled(False)
            sc.deleteLater()
        self._active_shortcuts.clear()

        mgr = mw._shortcut_mgr

        for action_id, tool_type in TOOL_SHORTCUT_MAP.items():
            key_seq = mgr.binding(action_id)
            if not key_seq:
                continue
            sc = QShortcut(QKeySequence(key_seq), mw)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            tt = tool_type
            sc.activated.connect(lambda t=tt: self._on_tool(t))
            self._active_shortcuts.append(sc)

        swap_key = mgr.binding("swap_colors")
        if swap_key:
            sc = QShortcut(QKeySequence(swap_key), mw)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(self._on_swap_colors)
            self._active_shortcuts.append(sc)

        reset_key = mgr.binding("reset_colors")
        if reset_key:
            sc = QShortcut(QKeySequence(reset_key), mw)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(self._on_reset_colors)
            self._active_shortcuts.append(sc)

        inc_key = mgr.binding("brush_size_increase")
        if inc_key:
            sc = QShortcut(QKeySequence(inc_key), mw)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(lambda: self._on_brush_size(5))
            self._active_shortcuts.append(sc)

        dec_key = mgr.binding("brush_size_decrease")
        if dec_key:
            sc = QShortcut(QKeySequence(dec_key), mw)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(lambda: self._on_brush_size(-5))
            self._active_shortcuts.append(sc)

        fs_key = mgr.binding("toggle_fullscreen")
        if fs_key:
            sc = QShortcut(QKeySequence(fs_key), mw)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(self._on_toggle_fullscreen)
            self._active_shortcuts.append(sc)

    def update_text_editing_shortcuts(self, editing: bool) -> None:
        """Disable single-key shortcuts during text editing to prevent conflicts."""
        for sc in self._active_shortcuts:
            if not editing:
                sc.setEnabled(True)
                continue
            seq_str = sc.key().toString(QKeySequence.SequenceFormat.PortableText)
            is_safe = (
                "Ctrl+" in seq_str or "Alt+" in seq_str or "Meta+" in seq_str
            )
            sc.setEnabled(is_safe)

    def _skip_if_text_editing(self) -> bool:
        mw = self._mw
        return (
            mw._tools.active_type == ToolType.TEXT
            and mw._canvas._text_editing
        )

    def _on_tool(self, tool_type: ToolType) -> None:
        if self._skip_if_text_editing():
            return
        mw = self._mw
        current = mw._tools.active_type
        for group in TOOL_CYCLE_GROUPS:
            if tool_type in group and current in group:
                idx = group.index(current)
                tool_type = group[(idx + 1) % len(group)]
                break
        mw._toolbar.select_tool(tool_type)

    def _on_swap_colors(self) -> None:
        if self._skip_if_text_editing():
            return
        ColorManager.instance().swap()

    def _on_reset_colors(self) -> None:
        if self._skip_if_text_editing():
            return
        ColorManager.instance().reset()

    def _on_brush_size(self, delta: int) -> None:
        mw = self._mw
        tool = mw._tools.active_tool
        if tool and hasattr(tool, "size"):
            new_size = max(1, tool.size + delta)
            tool.size = new_size
            mw._tool_ctrl.update_properties_panel()
            mw._tool_ctrl.update_brush_cursor()

    def _on_toggle_fullscreen(self) -> None:
        if self._skip_if_text_editing():
            return
        mw = self._mw
        if mw.isFullScreen():
            mw.showNormal()
        else:
            mw.showFullScreen()

    def _on_keyboard_shortcuts(self) -> None:
        """Open the keyboard shortcuts editor dialog."""
        from ..dialogs.shortcuts_dialog import KeyboardShortcutsDialog
        dlg = KeyboardShortcutsDialog(self._mw)
        dlg.exec()
