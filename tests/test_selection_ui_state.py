import numpy as np

from photo_editor.ui.services.selection_ui_state import apply_selection_overlay


class FakeCanvas:
    def __init__(self) -> None:
        self.selection_masks = []

    def set_selection_mask(self, mask) -> None:
        self.selection_masks.append(mask)


def test_apply_selection_overlay_shows_non_empty_mask() -> None:
    canvas = FakeCanvas()
    mask = np.array([[0.0, 1.0]], dtype=np.float32)

    apply_selection_overlay(canvas, mask)

    assert canvas.selection_masks == [mask]


def test_apply_selection_overlay_hides_empty_or_missing_mask() -> None:
    canvas = FakeCanvas()

    apply_selection_overlay(canvas, np.zeros((1, 1), dtype=np.float32))
    apply_selection_overlay(canvas, None)

    assert canvas.selection_masks == [None, None]