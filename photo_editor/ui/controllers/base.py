"""Shared controller infrastructure.

Controllers still interact with MainWindow-owned widgets, but common
document/render/command operations go through ControllerContext so the
god-object coupling has a narrower surface and can be migrated further.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...commands.base import Command

if TYPE_CHECKING:
    from ...core.document import Document
    from ..app_signals import AppSignals
    from ..main_window import MainWindow


class ControllerContext:
    """Thin facade over MainWindow for controller-safe shared operations."""

    def __init__(self, main_window: MainWindow) -> None:
        self._main_window = main_window

    @property
    def window(self) -> MainWindow:
        return self._main_window

    @property
    def document(self) -> Document | None:
        return self._main_window._doc

    def has_document(self) -> bool:
        return self.document is not None

    def refresh(self, invalidate: bool = True, layer_id: str | None = None) -> None:
        self._main_window._refresh(invalidate=invalidate, layer_id=layer_id)

    def refresh_canvas_only(self) -> None:
        self._main_window._refresh_canvas_only()

    def schedule_render(self) -> None:
        self._main_window._schedule_render()

    def schedule_panel_refresh(self) -> None:
        self._main_window._schedule_panel_refresh()

    def zoom_to_fit(self) -> None:
        self._main_window._canvas.zoom_to_fit()

    def set_window_title(self, title: str) -> None:
        self._main_window.setWindowTitle(title)

    def show_status_message(self, message: str, timeout_ms: int = 0) -> None:
        self._main_window._status.showMessage(message, timeout_ms)

    def set_document(self, document) -> None:
        self._main_window._doc = document

    def set_document_info(self, name: str, width: int, height: int) -> None:
        self._main_window._status.set_document_info(name, width, height)

    def refresh_layers_panel(self, *, thumbnails: bool = True) -> None:
        if self.document is not None:
            self._main_window._layers_panel.refresh(self.document, thumbnails=thumbnails)

    def refresh_layer_controls(self) -> None:
        if self.document is not None:
            self._main_window._layers_panel.refresh_controls_only(self.document)

    def toggle_selected_layer_visibility(self) -> None:
        self._main_window._layers_panel.toggle_visibility_for_selected()

    def selected_layer_ids(self) -> list[str]:
        return self._main_window._layers_panel.selected_layer_ids()

    def layer_row_ids(self) -> list[str]:
        return self._main_window._layers_panel.row_layer_ids()

    def execute_command_async(
        self,
        command: Command,
        on_success=None,
        on_error=None,
    ) -> None:
        self._main_window.execute_command_async(
            command,
            on_success=on_success,
            on_error=on_error,
        )

    def invalidate(self, layer_id: str | None = None) -> None:
        self._main_window._pipeline.invalidate(layer_id)

    def composite_float_rgba(self):
        """Latest composited document RGBA float32 [0,1], or None if no document."""
        doc = self.document
        if doc is None:
            return None
        return self._main_window._pipeline.execute(doc)

    def execute_command(self, command: Command):
        return self._main_window.execute_command(command)

    @property
    def signals(self) -> AppSignals:
        return self._main_window._app_signals


class ControllerBase:
    """Base class for controllers that need MainWindow context."""

    def __init__(self) -> None:
        self._mw = None
        self._ctx: ControllerContext | None = None

    def wire(self, main_window) -> None:
        self._mw = main_window
        self._ctx = ControllerContext(main_window)

    @property
    def mw(self):
        return self._mw

    @property
    def ctx(self) -> ControllerContext:
        if self._ctx is None:
            raise RuntimeError("Controller is not wired")
        return self._ctx

    @property
    def doc(self):
        return self.ctx.document

    @property
    def signals(self):
        return self.ctx.signals