"""Abstract base for all image filters."""

from abc import ABC, abstractmethod

import numpy as np


class Filter(ABC):
    """Destructive image filter.

    Unlike adjustments, filters directly modify pixel data.
    Each subclass implements ``apply`` with a params dict.
    """

    def __init__(self, name: str, default_params: dict | None = None) -> None:
        self.name = name
        self.default_params: dict = default_params or {}

    @abstractmethod
    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        ...

    def get_defaults(self) -> dict:
        return dict(self.default_params)

    @staticmethod
    def _rgb(image: np.ndarray) -> np.ndarray:
        return image[..., :3]

    @staticmethod
    def _alpha(image: np.ndarray) -> np.ndarray:
        return image[..., 3:4]

    @staticmethod
    def _merge(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
        return np.concatenate([np.clip(rgb, 0, 1), alpha], axis=-1).astype(np.float32)

    # ------------------------------------------------------------------
    #  Premultiplied-alpha blur helpers
    # ------------------------------------------------------------------
    #  Dark-fringe / black-halo fix:  when transparent pixels have
    #  RGB = (0,0,0) their black leaks into neighbours during a
    #  convolution.  Working in premultiplied-alpha space avoids this
    #  because RGB is already "weighted" by alpha.

    @staticmethod
    def _premultiply(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Return (premultiplied RGBA float32, original alpha).

        The caller applies the blur to ALL four channels of the
        premultiplied image, then calls ``_unpremultiply``.
        """
        alpha = image[..., 3:4].astype(np.float32)
        rgb = image[..., :3].astype(np.float32)
        pm = np.concatenate([rgb * alpha, alpha], axis=-1)
        return pm, alpha

    @staticmethod
    def _unpremultiply(pm_blurred: np.ndarray,
                       original_alpha: np.ndarray | None = None,
                       preserve_alpha: bool = False) -> np.ndarray:
        """Convert a premultiplied-alpha blur result back to straight alpha.

        Parameters
        ----------
        pm_blurred
            The blurred buffer in premultiplied-alpha space (H, W, 4).
        original_alpha
            If *preserve_alpha* is True this is the unblurred alpha that
            will replace the blurred alpha channel.
        preserve_alpha
            When True the original (unblurred) alpha is kept.
        """
        blurred_alpha = pm_blurred[..., 3:4].copy()
        if preserve_alpha and original_alpha is not None:
            out_alpha = original_alpha
        else:
            out_alpha = blurred_alpha

        # Avoid division by zero
        safe_alpha = np.where(blurred_alpha > 1e-6, blurred_alpha, 1.0)
        rgb = pm_blurred[..., :3] / safe_alpha
        rgb = np.clip(rgb, 0.0, 1.0)
        return np.concatenate([rgb, np.clip(out_alpha, 0.0, 1.0)], axis=-1).astype(np.float32)
