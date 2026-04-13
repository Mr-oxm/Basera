"""Image load / save helpers with capability-aware export support."""

from pathlib import Path
import base64
import io

import cv2
import numpy as np
from PIL import Image

_SUPPORTED_READ = {".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif", ".bmp"}

_EXT_TO_PIL_FORMAT = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
    ".avif": "AVIF",
    ".tiff": "TIFF",
    ".tif": "TIFF",
    ".bmp": "BMP",
    ".pdf": "PDF",
    ".psd": "PSD",
    ".heic": "HEIF",
}


def _pil_save_formats() -> set[str]:
    Image.init()
    return {fmt.upper() for fmt in Image.SAVE.keys()}


def can_save_extension(ext: str) -> bool:
    """Return True when the extension is writable in this runtime."""
    ext = ext.lower()
    if ext == ".basera":
        return True
    if ext == ".svg":
        return True
    fmt = _EXT_TO_PIL_FORMAT.get(ext)
    if fmt is None:
        return False
    return fmt in _pil_save_formats()


def supported_write_extensions() -> set[str]:
    """Return all writable extensions for this runtime."""
    exts = {".svg", ".basera"}
    for ext in _EXT_TO_PIL_FORMAT:
        if can_save_extension(ext):
            exts.add(ext)
    return exts


def load_image(path: str | Path) -> np.ndarray:
    """Load an image file and return RGBA float32 in [0, 1]."""
    path = Path(path)
    if path.suffix.lower() not in _SUPPORTED_READ:
        raise ValueError(f"Unsupported format: {path.suffix}")

    img = Image.open(path).convert("RGBA")
    arr = np.array(img, dtype=np.float32) / 255.0
    return arr


def save_image(
    image: np.ndarray,
    path: str | Path,
    quality: int = 95,
    *,
    target_size: tuple[int, int] | None = None,
    jpeg_bg: tuple[int, int, int] = (255, 255, 255),
    subsampling: int = 0,
) -> None:
    """Save an RGBA float32 image to disk.

    Parameters
    ----------
    image:
        RGBA float32 array in [0, 1].
    path:
        Destination file path.
    quality:
        Lossy quality (1-100) for JPEG / WEBP / AVIF / HEIC.
    target_size:
        ``(width, height)`` to resize the image before saving.  When
        ``None`` the original dimensions are kept.
    jpeg_bg:
        RGB background colour used when flattening transparent pixels for
        formats that have no alpha channel (JPEG, BMP, PDF).
    subsampling:
        JPEG chroma sub-sampling: 0=4:4:4, 1=4:2:2, 2=4:2:0.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if not can_save_extension(suffix):
        raise ValueError(
            f"Unsupported or unavailable export format for this runtime: {path.suffix}"
        )

    data = np.clip(image, 0, 1)
    data = (data * 255).astype(np.uint8)

    pil = Image.fromarray(data, "RGBA")

    if target_size is not None:
        tw, th = int(target_size[0]), int(target_size[1])
        if tw > 0 and th > 0 and (tw, th) != (pil.width, pil.height):
            pil = pil.resize((tw, th), Image.Resampling.LANCZOS)

    if suffix in {".jpg", ".jpeg"}:
        bg = Image.new("RGBA", pil.size, (*jpeg_bg, 255))
        composite = Image.alpha_composite(bg, pil)
        composite.convert("RGB").save(path, quality=quality, subsampling=subsampling)
    elif suffix == ".webp":
        pil.save(path, quality=quality)
    elif suffix == ".pdf":
        bg = Image.new("RGBA", pil.size, (*jpeg_bg, 255))
        composite = Image.alpha_composite(bg, pil)
        composite.convert("RGB").save(path, format="PDF", resolution=300)
    elif suffix == ".svg":
        # Export a self-contained raster-backed SVG for broad compatibility.
        buff = io.BytesIO()
        pil.save(buff, format="PNG")
        encoded = base64.b64encode(buff.getvalue()).decode("ascii")
        h, w = pil.height, pil.width
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">\n'
            f'  <image href="data:image/png;base64,{encoded}" width="{w}" height="{h}"/>\n'
            "</svg>\n"
        )
        path.write_text(svg, encoding="utf-8")
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
