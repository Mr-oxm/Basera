from photo_editor.ui.controllers.base import ControllerBase
from photo_editor.ui.controllers.crop_ctrl import CropController
from photo_editor.ui.controllers.gradient_ctrl import GradientController
from photo_editor.ui.controllers.text_ctrl import TextController
from photo_editor.ui.controllers.transform_ctrl import TransformController
from photo_editor.ui.controllers.vector_ctrl import VectorController


class FakePipeline:
    def __init__(self) -> None:
        self.invalidated = []

    def invalidate(self, layer_id=None) -> None:
        self.invalidated.append(layer_id)


class FakeWindow:
    def __init__(self) -> None:
        self._doc = object()
        self._pipeline = FakePipeline()
        self._interactive_pipeline = FakePipeline()
        self._final_pipeline = FakePipeline()
        self._canvas = type("Canvas", (), {"zoom_to_fit": self._zoom_to_fit})()
        self._status = type(
            "Status",
            (),
            {
                "showMessage": self._show_message,
                "set_document_info": self._set_document_info,
            },
        )()
        self._layers_panel = type(
            "LayersPanel",
            (),
            {
                "refresh": self._layers_refresh,
                "refresh_controls_only": self._layers_refresh_controls,
                "toggle_visibility_for_selected": self._toggle_visibility,
                "selected_layer_ids": self._selected_layer_ids,
                "row_layer_ids": self._row_layer_ids,
            },
        )()
        self.refresh_calls = []
        self.canvas_only_calls = 0
        self.render_calls = 0
        self.panel_calls = 0
        self.command_calls = []
        self.async_calls = []
        self.zoom_to_fit_calls = 0
        self.status_messages = []
        self.window_titles = []
        self.layers_refresh_calls = []
        self.layers_control_calls = 0
        self.layers_toggle_calls = 0
        self.document_info_calls = []
        self.selected_layer_ids_calls = 0
        self.row_layer_ids_calls = 0

    def _zoom_to_fit(self) -> None:
        self.zoom_to_fit_calls += 1

    def _show_message(self, message: str, timeout: int = 0) -> None:
        self.status_messages.append((message, timeout))

    def _set_document_info(self, name: str, width: int, height: int) -> None:
        self.document_info_calls.append((name, width, height))

    def _layers_refresh(self, document, thumbnails=True) -> None:
        self.layers_refresh_calls.append((document, thumbnails))

    def _layers_refresh_controls(self, document) -> None:
        self.layers_control_calls += 1

    def _toggle_visibility(self) -> None:
        self.layers_toggle_calls += 1

    def _selected_layer_ids(self) -> list[str]:
        self.selected_layer_ids_calls += 1
        return ["layer-a", "layer-b"]

    def _row_layer_ids(self) -> list[str]:
        self.row_layer_ids_calls += 1
        return ["row-a", "row-b"]

    def _refresh(self, invalidate=True, layer_id=None) -> None:
        self.refresh_calls.append((invalidate, layer_id))

    def _refresh_canvas_only(self) -> None:
        self.canvas_only_calls += 1

    def _schedule_render(self) -> None:
        self.render_calls += 1

    def _schedule_panel_refresh(self) -> None:
        self.panel_calls += 1

    def execute_command(self, command):
        self.command_calls.append(command)
        return "ok"

    def execute_command_async(self, command, on_success=None, on_error=None) -> None:
        self.async_calls.append((command, on_success, on_error))

    def setWindowTitle(self, title: str) -> None:
        self.window_titles.append(title)


class DummyController(ControllerBase):
    pass


def test_controller_context_proxies_main_window_operations() -> None:
    window = FakeWindow()
    controller = DummyController()
    controller.wire(window)

    assert controller.doc is window._doc

    controller.ctx.invalidate("layer-1")
    controller.ctx.refresh(invalidate=False, layer_id="layer-2")
    controller.ctx.refresh_canvas_only()
    controller.ctx.schedule_render()
    controller.ctx.schedule_panel_refresh()
    controller.ctx.zoom_to_fit()
    controller.ctx.show_status_message("saved", 500)
    controller.ctx.set_window_title("Basera")
    controller.ctx.set_document("new-doc")
    controller.ctx.set_document_info("Doc", 10, 20)
    controller.ctx.refresh_layers_panel(thumbnails=False)
    controller.ctx.refresh_layer_controls()
    controller.ctx.toggle_selected_layer_visibility()
    selected_ids = controller.ctx.selected_layer_ids()
    row_ids = controller.ctx.layer_row_ids()
    result = controller.ctx.execute_command("cmd")
    controller.ctx.execute_command_async("async-cmd")

    assert window._interactive_pipeline.invalidated == ["layer-1"]
    assert window._final_pipeline.invalidated == ["layer-1"]
    assert window.refresh_calls == [(False, "layer-2")]
    assert window.canvas_only_calls == 1
    assert window.render_calls == 1
    assert window.panel_calls == 1
    assert window.zoom_to_fit_calls == 1
    assert window._doc == "new-doc"
    assert window.document_info_calls == [("Doc", 10, 20)]
    assert window.status_messages == [("saved", 500)]
    assert window.window_titles == ["Basera"]
    assert window.layers_refresh_calls == [("new-doc", False)]
    assert window.layers_control_calls == 1
    assert window.layers_toggle_calls == 1
    assert selected_ids == ["layer-a", "layer-b"]
    assert row_ids == ["row-a", "row-b"]
    assert window.selected_layer_ids_calls == 1
    assert window.row_layer_ids_calls == 1
    assert window.command_calls == ["cmd"]
    assert len(window.async_calls) == 1
    assert result == "ok"


def test_remaining_feature_controllers_share_controller_base() -> None:
    assert issubclass(CropController, ControllerBase)
    assert issubclass(GradientController, ControllerBase)
    assert issubclass(TextController, ControllerBase)
    assert issubclass(TransformController, ControllerBase)
    assert issubclass(VectorController, ControllerBase)