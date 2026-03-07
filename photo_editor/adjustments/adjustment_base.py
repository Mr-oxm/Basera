"""Abstract base for all non-destructive adjustments."""

from ..processors import ImageProcessor


class Adjustment(ImageProcessor):
    """Non-destructive image adjustment.

    Each subclass implements ``apply`` which receives an RGBA float32
    image and a params dict, returning the adjusted image.
    """
