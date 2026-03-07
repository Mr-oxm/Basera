import numpy as np

from photo_editor.effects.effect_base import Effect
from photo_editor.processors import ImageProcessor


class DummyEffect(Effect):
    def __init__(self) -> None:
        super().__init__("Dummy Effect", {"strength": 1.0}, enabled=True)

    def apply(self, image: np.ndarray, params: dict | None = None) -> np.ndarray:
        return image.copy()


def test_effect_shares_image_processor_contract() -> None:
    effect = DummyEffect()

    assert isinstance(effect, ImageProcessor)
    assert effect.params == {"strength": 1.0}


def test_effect_set_param_updates_processor_defaults() -> None:
    effect = DummyEffect()

    effect.set_param("strength", 2.5)

    assert effect.params["strength"] == 2.5
    assert effect.default_params["strength"] == 2.5