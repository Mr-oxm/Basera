import numpy as np

from photo_editor.effects import Effect, EffectsPipeline


class AddValueEffect(Effect):
    def __init__(self, name: str, delta: float, *, enabled: bool = True) -> None:
        super().__init__(name, {"delta": delta}, enabled=enabled)

    def apply(self, image: np.ndarray, params: dict | None = None) -> np.ndarray:
        delta = (params or self.default_params)["delta"]
        result = image.copy()
        result[..., :3] += delta
        return result


def test_effects_pipeline_applies_enabled_effects_in_order() -> None:
    pipeline = EffectsPipeline()
    pipeline.add(AddValueEffect("first", 0.1))
    pipeline.add(AddValueEffect("second", 0.2))

    image = np.zeros((1, 1, 4), dtype=np.float32)
    result = pipeline.process(image)

    assert np.allclose(result[..., :3], 0.3)


def test_effects_pipeline_skips_disabled_effects() -> None:
    pipeline = EffectsPipeline()
    pipeline.add(AddValueEffect("first", 0.1, enabled=False))
    pipeline.add(AddValueEffect("second", 0.2, enabled=True))

    image = np.zeros((1, 1, 4), dtype=np.float32)
    result = pipeline.process(image)

    assert np.allclose(result[..., :3], 0.2)