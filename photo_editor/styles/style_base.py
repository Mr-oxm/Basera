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

    def supports_region_rendering(self) -> bool:
        return False

    def region_padding(self) -> int:
        return 0

    def apply_region(
        self,
        layer_image: np.ndarray,
        offset_x: int,
        offset_y: int,
        full_width: int,
        full_height: int,
    ) -> np.ndarray:
        if offset_x == 0 and offset_y == 0 and layer_image.shape[1] == full_width and layer_image.shape[0] == full_height:
            return self.apply(layer_image)
        raise NotImplementedError(f"{self.__class__.__name__} does not support region rendering")

    @staticmethod
    def _f32(img: np.ndarray) -> np.ndarray:
        return img.astype(np.float32) if img.dtype != np.float32 else img
