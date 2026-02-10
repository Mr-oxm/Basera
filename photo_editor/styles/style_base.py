"""Abstract base for layer styles."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np

from ..core.enums import BlendMode


@dataclass
class StyleParams:
    """Common parameters shared by all styles."""

    enabled: bool = True
    opacity: float = 1.0
    blend_mode: BlendMode = BlendMode.NORMAL
    extra: dict = field(default_factory=dict)


class LayerStyle(ABC):
    """Base class for every layer style effect."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.params = StyleParams()

    @abstractmethod
    def apply(self, layer_image: np.ndarray) -> np.ndarray:
        ...

    @staticmethod
    def _f32(img: np.ndarray) -> np.ndarray:
        return img.astype(np.float32) if img.dtype != np.float32 else img
