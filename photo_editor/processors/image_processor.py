"""Shared base contract for image-processing primitives."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class ImageProcessor(ABC):
    """Common contract for adjustment-like and filter-like processors."""

    def __init__(self, name: str, default_params: dict | None = None) -> None:
        self.name = name
        self.default_params: dict = default_params or {}

    @abstractmethod
    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        """Process an RGBA float32 image and return a new RGBA float32 image."""

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