from types import SimpleNamespace

from photo_editor.ui.services.layer_panel_state import (
    reordered_stack_order,
    selected_indices_from_layer_ids,
    sync_panel_selection,
)


class FakeItem:
    def __init__(self) -> None:
        self.selected = False

    def setSelected(self, value: bool) -> None:
        self.selected = value


class FakeListWidget:
    def __init__(self, count: int) -> None:
        self._items = [FakeItem() for _ in range(count)]
        self.blocked = []
        self.cleared = 0
        self.current_row = None

    def blockSignals(self, value: bool) -> None:
        self.blocked.append(value)

    def clearSelection(self) -> None:
        self.cleared += 1

    def setCurrentRow(self, row: int) -> None:
        self.current_row = row

    def item(self, row: int):
        return self._items[row]


class FakePanel:
    def __init__(self, row_ids: list[str]) -> None:
        self._row_ids = row_ids
        self._list = FakeListWidget(len(row_ids))
        self.refresh_calls = []

    def refresh(self, document, thumbnails=True) -> None:
        self.refresh_calls.append((document, thumbnails))

    def row_layer_ids(self) -> list[str]:
        return list(self._row_ids)


def test_sync_panel_selection_refreshes_and_selects_rows() -> None:
    layers = [SimpleNamespace(id="a"), SimpleNamespace(id="b"), SimpleNamespace(id="c")]
    document = SimpleNamespace(
        layers=SimpleNamespace(
            selected_indices={0, 2},
            active_layer=layers[2],
            layers=layers,
        )
    )
    panel = FakePanel(["c", "b", "a"])

    sync_panel_selection(document, panel)

    assert panel.refresh_calls == [(document, True)]
    assert panel._list.current_row == 0
    assert panel._list._items[0].selected is True
    assert panel._list._items[2].selected is True
    assert panel._list.blocked == [True, False]


def test_selected_indices_from_layer_ids_maps_ids_to_indices() -> None:
    layers = [SimpleNamespace(id="a"), SimpleNamespace(id="b"), SimpleNamespace(id="c")]

    result = selected_indices_from_layer_ids(["c", "a"], layers)

    assert result == {0, 2}


def test_reordered_stack_order_moves_dragged_ids_to_target_row() -> None:
    display_ids = ["top", "mid1", "mid2", "bottom"]

    result = reordered_stack_order(display_ids, ["mid1", "mid2"], 1)

    assert result == ["bottom", "mid2", "mid1", "top"]