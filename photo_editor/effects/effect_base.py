"""Abstract base for all image effects."""

import numpy as np

from ..processors import ImageProcessor


class Effect(ImageProcessor):
    """Single processing step in the effects pipeline."""

    def __init__(
        self,
        name: str,
        default_params: dict | None = None,
        enabled: bool = True,
    ) -> None:
        super().__init__(name, default_params)
        self.enabled = enabled

    @property
    def params(self) -> dict:
        return self.default_params

    def set_param(self, key: str, value: object) -> None:
        self.default_params[key] = value

    def apply(self, image: np.ndarray, params: dict | None = None) -> np.ndarray:
        raise NotImplementedError()
