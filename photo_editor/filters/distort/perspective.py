"""Perspective distortion filter."""

import cv2
import numpy as np

from ..filter_base import Filter


class PerspectiveFilter(Filter):
    """Apply a perspective (vanishing-point) distortion.

    Parameters
    ----------
    amount : int
        Distortion amount, range [-100, 100].
        Positive values converge the top/left; negative the bottom/right.
    direction : str
        ``"horizontal"`` or ``"vertical"``.
    """

    def __init__(self) -> None:
        super().__init__(
            "Perspective",
            {"amount": 25, "direction": "vertical"},
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image).astype(np.float32)
        alpha = self._alpha(image)

        amount = int(params.get("amount", self.default_params["amount"]))
        direction = str(params.get("direction", self.default_params["direction"])).lower()
        amount = max(-100, min(amount, 100))
        if direction not in ("horizontal", "vertical"):
            direction = "vertical"

        h, w = rgb.shape[:2]
        strength = amount / 100.0

        # Source corners: TL, TR, BR, BL.
        src = np.array(
            [[0, 0], [w, 0], [w, h], [0, h]],
            dtype=np.float32,
        )

        offset = abs(strength) * min(w, h) * 0.25

        if direction == "vertical":
            if strength >= 0:
                # Converge top edge.
                dst = np.array(
                    [[offset, 0], [w - offset, 0], [w, h], [0, h]],
                    dtype=np.float32,
                )
            else:
                # Converge bottom edge.
                dst = np.array(
                    [[0, 0], [w, 0], [w - offset, h], [offset, h]],
                    dtype=np.float32,
                )
        else:  # horizontal
            if strength >= 0:
                # Converge left edge.
                dst = np.array(
                    [[0, offset], [w, 0], [w, h], [0, h - offset]],
                    dtype=np.float32,
                )
            else:
                # Converge right edge.
                dst = np.array(
                    [[0, 0], [w, offset], [w, h - offset], [0, h]],
                    dtype=np.float32,
                )

        matrix = cv2.getPerspectiveTransform(src, dst)

        warped = cv2.warpPerspective(
            rgb, matrix, (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        )

        alpha_f = alpha.astype(np.float32)
        alpha_out = cv2.warpPerspective(
            alpha_f, matrix, (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        )
        if alpha_out.ndim == 2:
            alpha_out = alpha_out[..., np.newaxis]

        return self._merge(warped, alpha_out)
