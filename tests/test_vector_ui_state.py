from types import SimpleNamespace

from photo_editor.ui.services.vector_ui_state import (
    clear_boolean_preview,
    enter_pick_segments_mode,
    exit_pick_segments_mode,
    show_boolean_preview,
    update_boolean_toolbar,
)


class FakeVectorBar:
    def __init__(self) -> None:
        self.enter_calls = 0
        self.exit_calls = 0
        self.boolean_state = None

    def enter_pick_segments(self) -> None:
        self.enter_calls += 1

    def exit_pick_segments(self) -> None:
        self.exit_calls += 1

    def update_boolean_state(self, count: int, first: str, second: str) -> None:
        self.boolean_state = (count, first, second)


class FakeCanvas:
    def __init__(self) -> None:
        self._pick_segments_state = None
        self._bool_preview_path = None
        self._bool_source_ids = set()
        self.update_calls = 0

    def update(self) -> None:
        self.update_calls += 1


def test_pick_segments_helpers_update_panel_and_canvas() -> None:
    props_panel = SimpleNamespace(vector_bar=FakeVectorBar())
    canvas = FakeCanvas()

    enter_pick_segments_mode(props_panel, canvas, "state")
    exit_pick_segments_mode(props_panel, canvas)

    assert props_panel.vector_bar.enter_calls == 1
    assert props_panel.vector_bar.exit_calls == 1
    assert canvas._pick_segments_state is None
    assert canvas.update_calls == 2


def test_boolean_preview_helpers_update_canvas_state() -> None:
    canvas = FakeCanvas()

    show_boolean_preview(canvas, "preview", ["a", "b"])
    clear_boolean_preview(canvas)

    assert canvas._bool_preview_path is None
    assert canvas._bool_source_ids == set()
    assert canvas.update_calls == 2


def test_update_boolean_toolbar_forwards_state() -> None:
    props_panel = SimpleNamespace(vector_bar=FakeVectorBar())

    update_boolean_toolbar(props_panel, 2, "Layer A", "Layer B")

    assert props_panel.vector_bar.boolean_state == (2, "Layer A", "Layer B")