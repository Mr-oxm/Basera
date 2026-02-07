"""Abstract base for all image filters."""

from abc import ABC, abstractmethod

import numpy as np


class Filter(ABC):
    """Destructive image filter.

    Unlike adjustments, filters directly modify pixel data.
    Each subclass implements ``apply`` with a params dict.
    """

    def __init__(self, name: str, default_params: dict | None = None) -> None:
        self.name = name
        self.default_params: dict = default_params or {}

    @abstractmethod
    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        ...

    def get_defaults(self) -> dict:
        return dict(self.default_params)

    @staticmethod
    def _rgb(image: np.ndarray) -> np.ndarray:
        return image[..., :3]

    @staticmethod
    def _alpha(image: np.ndarray) -> np.ndarray:
        return image[..., 3:4]

    @staticmethod
    def _merge(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
        return np.concatenate([np.clip(rgb, 0, 1), alpha], axis=-1).astype(np.float32)
