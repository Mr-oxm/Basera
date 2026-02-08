"""Layer data model — the atomic unit of the compositing stack."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

import numpy as np

from .enums import BlendMode, LayerType


@dataclass
class Layer:
    """Single compositing layer with optional mask and styles."""

    name: str
    width: int
    height: int
    layer_type: LayerType = LayerType.RASTER
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    opacity: float = 1.0
    blend_mode: BlendMode = BlendMode.NORMAL
    visible: bool = True
    locked: bool = False
    position: tuple[int, int] = (0, 0)
    mask_enabled: bool = True
    clipping_mask: bool = False
    parent_id: str | None = None
    # Persistent rotation tracking — lets the bounding box stay rotated
    # across tool / layer switches.
    transform_angle: float = 0.0
    transform_base_w: int = 0
    transform_base_h: int = 0

    def __post_init__(self) -> None:
        self._pixels = np.zeros((self.height, self.width, 4), dtype=np.float32)
        self._mask: np.ndarray | None = None
        self._styles: list = []
        self._adjustment: object | None = None
        self._adjustment_params: dict = {}
        self.children: list[str] = []

    # ---- Pixel data ---------------------------------------------------------

    @property
    def pixels(self) -> np.ndarray:
        return self._pixels

    @pixels.setter
    def pixels(self, value: np.ndarray) -> None:
        self._pixels = value.astype(np.float32) if value.dtype != np.float32 else value
        self.height, self.width = value.shape[:2]

    # ---- Mask ---------------------------------------------------------------

    @property
    def mask(self) -> np.ndarray | None:
        return self._mask

    @mask.setter
    def mask(self, value: np.ndarray | None) -> None:
        self._mask = value

    def add_mask(self, fill_white: bool = True) -> None:
        val = 1.0 if fill_white else 0.0
        self._mask = np.full((self.height, self.width), val, dtype=np.float32)

    def remove_mask(self) -> None:
        self._mask = None

    # ---- Styles / Adjustments ----------------------------------------------

    @property
    def styles(self) -> list:
        return self._styles

    @property
    def adjustment(self):
        return self._adjustment

    @adjustment.setter
    def adjustment(self, value) -> None:
        self._adjustment = value

    @property
    def adjustment_params(self) -> dict:
        return self._adjustment_params

    @adjustment_params.setter
    def adjustment_params(self, value: dict) -> None:
        self._adjustment_params = value

    # ---- Utilities ----------------------------------------------------------

    def duplicate(self) -> "Layer":
        new = Layer(
            name=f"{self.name} copy",
            width=self.width,
            height=self.height,
            layer_type=self.layer_type,
            opacity=self.opacity,
            blend_mode=self.blend_mode,
            visible=self.visible,
            position=self.position,
            transform_angle=self.transform_angle,
            transform_base_w=self.transform_base_w,
            transform_base_h=self.transform_base_h,
        )
        new._pixels = self._pixels.copy()
        if self._mask is not None:
            new._mask = self._mask.copy()
        new._styles = list(self._styles)
        return new

    def fill(self, color: np.ndarray) -> None:
        self._pixels[:] = color.astype(np.float32)
