"""Abstract base for all non-destructive adjustments."""

from abc import ABC, abstractmethod

import numpy as np


class Adjustment(ABC):
    """Non-destructive image adjustment.

    Each subclass implements ``apply`` which receives an RGBA float32
    image and a params dict, returning the adjusted image.
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
