"""Shared UI policy for rasterizing text layers before paint operations."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QMessageBox

from ...core.enums import LayerType, ToolType


PAINTING_TOOLS = {
    ToolType.BRUSH,
    ToolType.ERASER,
    ToolType.CLONE_STAMP,
    ToolType.HEALING_BRUSH,
    ToolType.GRADIENT,
    ToolType.PAINT_BUCKET,
}


def needs_text_layer_rasterization(document, tool_type: ToolType) -> bool:
    """Return True when a painting tool targets a text layer."""
    if document is None or tool_type not in PAINTING_TOOLS:
        return False
    layer = document.layers.active_layer
    return layer is not None and layer.layer_type == LayerType.TEXT


def rasterize_active_text_layer(document, refresh: Callable[[], None]) -> bool:
    """Convert the active text layer into a raster layer and refresh the UI."""
    if document is None:
        return False
    layer = document.layers.active_layer
    if layer is None or layer.layer_type != LayerType.TEXT:
        return False

    document.save_snapshot("Rasterize Text")
    layer.layer_type = LayerType.RASTER
    if hasattr(layer, "_text_data"):
        try:
            del layer._text_data
        except AttributeError:
            layer._text_data = None
    layer.rasterize_transform()
    refresh()
    return True


def ensure_active_layer_rasterized_for_tool(
    parent,
    document,
    tool_type: ToolType,
    refresh: Callable[[], None],
    warning_fn: Callable[..., QMessageBox.StandardButton] | None = None,
) -> bool:
    """Prompt and rasterize when a paint operation targets a text layer."""
    if not needs_text_layer_rasterization(document, tool_type):
        return True

    warning = warning_fn or QMessageBox.warning
    reply = warning(
        parent,
        "Rasterize Text Layer",
        "This type layer must be rasterized before it can be modified "
        "with this tool.  Once rasterized, the text will no longer be "
        "editable.\n\nRasterize the layer?",
        QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel,
    )
    if reply != QMessageBox.StandardButton.Ok:
        return False
    return rasterize_active_text_layer(document, refresh)