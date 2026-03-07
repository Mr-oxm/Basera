from types import SimpleNamespace

from PySide6.QtWidgets import QMessageBox

from photo_editor.core.enums import LayerType, ToolType
from photo_editor.ui.services.rasterize_guard import (
    ensure_active_layer_rasterized_for_tool,
    needs_text_layer_rasterization,
)


class MockLayer:
    def __init__(self, layer_type: LayerType) -> None:
        self.layer_type = layer_type
        self._text_data = object()
        self.rasterized = False

    def rasterize_transform(self) -> None:
        self.rasterized = True


class MockDocument:
    def __init__(self, layer: MockLayer | None) -> None:
        self.layers = SimpleNamespace(active_layer=layer)
        self.snapshots: list[str] = []

    def save_snapshot(self, name: str) -> None:
        self.snapshots.append(name)


def test_needs_text_layer_rasterization_checks_tool_and_layer_type() -> None:
    text_doc = MockDocument(MockLayer(LayerType.TEXT))
    raster_doc = MockDocument(MockLayer(LayerType.RASTER))

    assert needs_text_layer_rasterization(text_doc, ToolType.BRUSH) is True
    assert needs_text_layer_rasterization(text_doc, ToolType.MOVE) is False
    assert needs_text_layer_rasterization(raster_doc, ToolType.BRUSH) is False
    assert needs_text_layer_rasterization(None, ToolType.BRUSH) is False


def test_ensure_active_layer_rasterized_for_tool_aborts_when_cancelled() -> None:
    document = MockDocument(MockLayer(LayerType.TEXT))
    refresh_calls: list[str] = []

    allowed = ensure_active_layer_rasterized_for_tool(
        None,
        document,
        ToolType.BRUSH,
        lambda: refresh_calls.append("refresh"),
        warning_fn=lambda *args: QMessageBox.StandardButton.Cancel,
    )

    assert allowed is False
    assert document.snapshots == []
    assert refresh_calls == []
    assert document.layers.active_layer.layer_type == LayerType.TEXT


def test_ensure_active_layer_rasterized_for_tool_rasterizes_after_confirmation() -> None:
    document = MockDocument(MockLayer(LayerType.TEXT))
    refresh_calls: list[str] = []

    allowed = ensure_active_layer_rasterized_for_tool(
        None,
        document,
        ToolType.BRUSH,
        lambda: refresh_calls.append("refresh"),
        warning_fn=lambda *args: QMessageBox.StandardButton.Ok,
    )

    layer = document.layers.active_layer
    assert allowed is True
    assert document.snapshots == ["Rasterize Text"]
    assert refresh_calls == ["refresh"]
    assert layer.layer_type == LayerType.RASTER
    assert layer.rasterized is True