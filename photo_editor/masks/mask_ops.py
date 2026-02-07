"""Low-level mask operations (blur, feather, refine)."""

import cv2
import numpy as np


class MaskOps:
    """Stateless mask manipulation utilities."""

    @staticmethod
    def feather(mask: np.ndarray, radius: int) -> np.ndarray:
        if radius <= 0:
            return mask
        k = radius * 2 + 1
        return cv2.GaussianBlur(mask, (k, k), radius / 3.0)

    @staticmethod
    def grow(mask: np.ndarray, pixels: int) -> np.ndarray:
        if pixels <= 0:
            return mask
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (pixels * 2 + 1,) * 2)
        return cv2.dilate(mask, k)

    @staticmethod
    def shrink(mask: np.ndarray, pixels: int) -> np.ndarray:
        if pixels <= 0:
            return mask
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (pixels * 2 + 1,) * 2)
        return cv2.erode(mask, k)

    @staticmethod
    def refine_edge(mask: np.ndarray, radius: int = 3, contrast: float = 1.5) -> np.ndarray:
        """Simple edge refinement via blur + contrast boost."""
        refined = MaskOps.feather(mask, radius)
        mid = 0.5
        refined = (refined - mid) * contrast + mid
        return np.clip(refined, 0, 1).astype(np.float32)

    @staticmethod
    def from_alpha(image: np.ndarray) -> np.ndarray:
        """Extract mask from the alpha channel of an RGBA image."""
        return image[..., 3].copy()

    @staticmethod
    def threshold(mask: np.ndarray, level: float = 0.5) -> np.ndarray:
        return np.where(mask >= level, 1.0, 0.0).astype(np.float32)

    @staticmethod
    def combine_intersect(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return np.minimum(a, b)

    @staticmethod
    def combine_union(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return np.maximum(a, b)

    @staticmethod
    def combine_subtract(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return np.clip(a - b, 0, 1).astype(np.float32)
