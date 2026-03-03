"""Place image command."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ..base import Command

if TYPE_CHECKING:
    from ...core.document import Document


class PlaceImageCommand(Command):
    """Place an RGBA image as a new layer."""

    def __init__(self, pixels: np.ndarray, name: str = "Placed Image") -> None:
        self.pixels = pixels
        self.name = name

    def execute(self, document: Document) -> None:
        document.place_image(self.pixels, name=self.name)
