"""Image load / save helpers — supports PNG, JPG, WEBP, TIFF."""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

_SUPPORTED_READ = {".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif", ".bmp"}
_SUPPORTED_WRITE = {".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif"}


def load_image(path: str | Path) -> np.ndarray:
    """Load an image file and return RGBA float32 in [0, 1]."""
    path = Path(path)
    if path.suffix.lower() not in _SUPPORTED_READ:
        raise ValueError(f"Unsupported format: {path.suffix}")

    img = Image.open(path).convert("RGBA")
    arr = np.array(img, dtype=np.float32) / 255.0
    return arr


def save_image(
    image: np.ndarray, path: str | Path, quality: int = 95,
) -> None:
    """Save an RGBA float32 image to disk."""
    path = Path(path)
    if path.suffix.lower() not in _SUPPORTED_WRITE:
        raise ValueError(f"Unsupported format: {path.suffix}")

    data = np.clip(image, 0, 1)
    data = (data * 255).astype(np.uint8)

    pil = Image.fromarray(data, "RGBA")
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        pil = pil.convert("RGB")
        pil.save(path, quality=quality)
    elif path.suffix.lower() == ".webp":
        pil.save(path, quality=quality)
    else:
        pil.save(path)


def load_image_cv(path: str | Path) -> np.ndarray:
    """Load via OpenCV, return RGBA float32."""
    raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if raw is None:
        raise FileNotFoundError(f"Cannot read: {path}")
    if raw.ndim == 2:
        raw = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGRA)
    elif raw.shape[2] == 3:
        raw = cv2.cvtColor(raw, cv2.COLOR_BGR2BGRA)
    else:
        raw = cv2.cvtColor(raw, cv2.COLOR_BGRA2RGBA)
        return raw.astype(np.float32) / 255.0
    rgba = cv2.cvtColor(raw, cv2.COLOR_BGRA2RGBA)
    return rgba.astype(np.float32) / 255.0
