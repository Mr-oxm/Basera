import numpy as np

from photo_editor.adjustments.adjustment_base import Adjustment
from photo_editor.filters.filter_base import Filter
from photo_editor.processors import ImageProcessor


class DummyAdjustment(Adjustment):
    def __init__(self) -> None:
        super().__init__("Dummy Adjustment", {"value": 1})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        return image.copy()


class DummyFilter(Filter):
    def __init__(self) -> None:
        super().__init__("Dummy Filter", {"radius": 3})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        return image.copy()


def test_adjustment_and_filter_share_processor_contract() -> None:
    adjustment = DummyAdjustment()
    image_filter = DummyFilter()

    assert isinstance(adjustment, ImageProcessor)
    assert isinstance(image_filter, ImageProcessor)


def test_processor_defaults_are_copied() -> None:
    adjustment = DummyAdjustment()

    defaults = adjustment.get_defaults()
    defaults["value"] = 99

    assert adjustment.default_params["value"] == 1