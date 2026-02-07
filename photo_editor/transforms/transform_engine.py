"""Geometric transform engine using OpenCV affine/perspective warps."""

import cv2
import numpy as np


class TransformEngine:
    """Applies geometric transforms to RGBA float32 images."""

    @staticmethod
    def scale(image: np.ndarray, sx: float, sy: float) -> np.ndarray:
        h, w = image.shape[:2]
        nw, nh = max(1, int(w * sx)), max(1, int(h * sy))
        return cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR)

    @staticmethod
    def rotate(image: np.ndarray, angle: float, expand: bool = True) -> np.ndarray:
        h, w = image.shape[:2]
        cx, cy = w / 2, h / 2
        M = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
        if expand:
            cos, sin = abs(M[0, 0]), abs(M[0, 1])
            nw = int(h * sin + w * cos)
            nh = int(h * cos + w * sin)
            M[0, 2] += (nw - w) / 2
            M[1, 2] += (nh - h) / 2
        else:
            nw, nh = w, h
        return cv2.warpAffine(image, M, (nw, nh), borderMode=cv2.BORDER_TRANSPARENT)

    @staticmethod
    def skew(image: np.ndarray, sx: float = 0.0, sy: float = 0.0) -> np.ndarray:
        h, w = image.shape[:2]
        M = np.float32([[1, sx, 0], [sy, 1, 0]])
        nw = int(w + abs(sx) * h)
        nh = int(h + abs(sy) * w)
        if sx < 0:
            M[0, 2] = -sx * h
        if sy < 0:
            M[1, 2] = -sy * w
        return cv2.warpAffine(image, M, (nw, nh), borderMode=cv2.BORDER_TRANSPARENT)

    @staticmethod
    def flip_h(image: np.ndarray) -> np.ndarray:
        return np.ascontiguousarray(image[:, ::-1])

    @staticmethod
    def flip_v(image: np.ndarray) -> np.ndarray:
        return np.ascontiguousarray(image[::-1, :])

    @staticmethod
    def perspective(image: np.ndarray, src_pts: np.ndarray, dst_pts: np.ndarray) -> np.ndarray:
        """Apply a perspective warp.  src_pts / dst_pts: (4, 2) float32."""
        h, w = image.shape[:2]
        M = cv2.getPerspectiveTransform(src_pts.astype(np.float32), dst_pts.astype(np.float32))
        return cv2.warpPerspective(image, M, (w, h), borderMode=cv2.BORDER_TRANSPARENT)

    @staticmethod
    def free_transform(
        image: np.ndarray,
        angle: float = 0, sx: float = 1, sy: float = 1,
        tx: float = 0, ty: float = 0,
    ) -> np.ndarray:
        h, w = image.shape[:2]
        cx, cy = w / 2, h / 2
        M = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
        M[0, 0] *= sx
        M[0, 1] *= sx
        M[1, 0] *= sy
        M[1, 1] *= sy
        M[0, 2] += tx
        M[1, 2] += ty
        return cv2.warpAffine(image, M, (w, h), borderMode=cv2.BORDER_TRANSPARENT)

    @staticmethod
    def warp_grid(image: np.ndarray, grid_points: np.ndarray, grid_size: int = 3) -> np.ndarray:
        """Basic grid warp using piecewise affine (simplified)."""
        h, w = image.shape[:2]
        map_x = np.tile(np.arange(w, dtype=np.float32), (h, 1))
        map_y = np.tile(np.arange(h, dtype=np.float32)[:, np.newaxis], (1, w))
        # Simple displacement from grid
        for pt in grid_points:
            ox, oy, dx, dy = pt
            dist = np.sqrt((map_x - ox) ** 2 + (map_y - oy) ** 2)
            weight = np.exp(-dist / max(w, h) * grid_size)
            map_x += dx * weight
            map_y += dy * weight
        return cv2.remap(image, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_TRANSPARENT)
