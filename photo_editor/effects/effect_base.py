"""Abstract base for all image effects."""

from abc import ABC, abstractmethod

import numpy as np


class Effect(ABC):
    """Single processing step in the effects pipeline."""

    def __init__(self, name: str, enabled: bool = True) -> None:
        self.name = name
        self.enabled = enabled
        self._params: dict = {}

    @property
    def params(self) -> dict:
        return self._params

    def set_param(self, key: str, value: object) -> None:
        self._params[key] = value

    @abstractmethod
    def apply(self, image: np.ndarray, params: dict | None = None) -> np.ndarray:
        ...
