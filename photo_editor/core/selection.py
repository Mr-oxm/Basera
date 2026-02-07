"""Selection management with marching-ants support."""

import numpy as np


class Selection:
    """Pixel-level selection mask in [0, 1] float space."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._mask: np.ndarray | None = None

    @property
    def active(self) -> bool:
        return self._mask is not None

    @property
    def mask(self) -> np.ndarray | None:
        return self._mask

    # ---- Whole-image ops ----------------------------------------------------

    def select_all(self) -> None:
        self._mask = np.ones((self.height, self.width), dtype=np.float32)

    def deselect(self) -> None:
        self._mask = None

    def invert(self) -> None:
        if self._mask is not None:
            self._mask = 1.0 - self._mask

    # ---- Shape selections ---------------------------------------------------

    def select_rect(self, x: int, y: int, w: int, h: int) -> None:
        self._mask = np.zeros((self.height, self.width), dtype=np.float32)
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(self.width, x + w), min(self.height, y + h)
        self._mask[y1:y2, x1:x2] = 1.0

    def select_ellipse(self, cx: int, cy: int, rx: int, ry: int) -> None:
        self._mask = np.zeros((self.height, self.width), dtype=np.float32)
        yy, xx = np.ogrid[: self.height, : self.width]
        ellipse = ((xx - cx) / max(rx, 1)) ** 2 + ((yy - cy) / max(ry, 1)) ** 2
        self._mask[ellipse <= 1.0] = 1.0

    # ---- Refinement ---------------------------------------------------------

    def feather(self, radius: int) -> None:
        if self._mask is not None and radius > 0:
            import cv2
            ksize = radius * 2 + 1
            self._mask = cv2.GaussianBlur(self._mask, (ksize, ksize), radius / 3.0)

    def grow(self, pixels: int) -> None:
        if self._mask is not None and pixels > 0:
            import cv2
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (pixels * 2 + 1,) * 2)
            self._mask = cv2.dilate(self._mask, k)

    def shrink(self, pixels: int) -> None:
        if self._mask is not None and pixels > 0:
            import cv2
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (pixels * 2 + 1,) * 2)
            self._mask = cv2.erode(self._mask, k)

    # ---- Application --------------------------------------------------------

    def apply_to(self, image: np.ndarray) -> np.ndarray:
        if self._mask is None:
            return image
        if image.ndim == 3:
            return image * self._mask[..., np.newaxis]
        return image * self._mask

    def resize(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        if self._mask is not None:
            import cv2
            self._mask = cv2.resize(self._mask, (width, height))
