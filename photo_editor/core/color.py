"""Color representation and conversion utilities."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Color:
    """Immutable RGBA color in [0, 1] float space."""

    r: float = 0.0
    g: float = 0.0
    b: float = 0.0
    a: float = 1.0

    # ---- Constructors -------------------------------------------------------

    @classmethod
    def from_rgb8(cls, r: int, g: int, b: int, a: int = 255) -> "Color":
        return cls(r / 255.0, g / 255.0, b / 255.0, a / 255.0)

    @classmethod
    def from_hex(cls, hex_str: str) -> "Color":
        h = hex_str.lstrip("#")
        if len(h) == 6:
            return cls.from_rgb8(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        if len(h) == 8:
            return cls.from_rgb8(
                int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16),
            )
        raise ValueError(f"Invalid hex color: {hex_str}")

    # ---- Conversions --------------------------------------------------------

    def to_rgb8(self) -> tuple[int, int, int, int]:
        return (
            int(self.r * 255), int(self.g * 255),
            int(self.b * 255), int(self.a * 255),
        )

    def to_hex(self) -> str:
        r, g, b, a = self.to_rgb8()
        return f"#{r:02x}{g:02x}{b:02x}" if a == 255 else f"#{r:02x}{g:02x}{b:02x}{a:02x}"

    def to_array(self) -> np.ndarray:
        return np.array([self.r, self.g, self.b, self.a], dtype=np.float32)

    # ---- Presets ------------------------------------------------------------

    @classmethod
    def black(cls) -> "Color":
        return cls(0.0, 0.0, 0.0, 1.0)

    @classmethod
    def white(cls) -> "Color":
        return cls(1.0, 1.0, 1.0, 1.0)

    @classmethod
    def transparent(cls) -> "Color":
        return cls(0.0, 0.0, 0.0, 0.0)
