"""Thumbnail generation for layer previews."""

from __future__ import annotations

import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

from ....core.document import Document
from .base import THUMB_SIZE


_THUMB_CHECKER: QPixmap | None = None


def thumb_checker(size: int = THUMB_SIZE) -> QPixmap:
    global _THUMB_CHECKER
    if _THUMB_CHECKER is None or _THUMB_CHECKER.width() != size:
        _THUMB_CHECKER = QPixmap(size, size)
        _THUMB_CHECKER.fill(QColor(42, 42, 42))
        tp = QPainter(_THUMB_CHECKER)
        tp.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        cs = 4
        light, dark = QColor(70, 70, 70), QColor(50, 50, 50)
        for r in range(0, size, cs):
            for c in range(0, size, cs):
                tp.fillRect(c, r, cs, cs, light if (r // cs + c // cs) % 2 == 0 else dark)
        tp.end()
    return _THUMB_CHECKER


def pixels_to_thumbnail_pixmap(px: np.ndarray, size: int = THUMB_SIZE) -> QPixmap:
    """Convert float32 RGBA pixels to a centered thumbnail QPixmap on checkerboard."""
    pm = QPixmap(thumb_checker(size))
    if px is None or px.size == 0:
        return pm
    h, w = px.shape[:2]
    if h > size * 4 or w > size * 4:
        step_h = max(1, h // (size * 2))
        step_w = max(1, w // (size * 2))
        px = px[::step_h, ::step_w]
        h, w = px.shape[:2]
    buf = np.empty((h, w, 4), dtype=np.uint8)
    np.multiply(px[:, :, 2:3], 255, out=buf[:, :, 0:1], casting='unsafe')
    np.multiply(px[:, :, 1:2], 255, out=buf[:, :, 1:2], casting='unsafe')
    np.multiply(px[:, :, 0:1], 255, out=buf[:, :, 2:3], casting='unsafe')
    np.multiply(px[:, :, 3:4], 255, out=buf[:, :, 3:4], casting='unsafe')
    np.clip(buf, 0, 255, out=buf)
    img = QImage(buf.data, w, h, w * 4, QImage.Format.Format_ARGB32)
    scaled = img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.FastTransformation)
    tp = QPainter(pm)
    ox = (size - scaled.width()) // 2
    oy = (size - scaled.height()) // 2
    tp.drawImage(ox, oy, scaled)
    tp.end()
    return pm


def make_thumbnail(layer, size: int = THUMB_SIZE) -> QPixmap:
    """Generate a small QPixmap thumbnail for *layer*."""
    pm = QPixmap(thumb_checker(size))
    try:
        px = layer.pixels
        if px is not None and px.size > 0:
            pm = pixels_to_thumbnail_pixmap(px, size)
    except Exception:
        pass
    return pm


def make_group_thumbnail(document: Document, group, size: int = THUMB_SIZE) -> QPixmap:
    """Generate a thumbnail for a group layer by compositing its children."""
    pm = QPixmap(thumb_checker(size))
    try:
        from ....engine.compositor import Compositor
        compositor = Compositor()
        px = compositor.composite_group_tight(group, document.layers)
        if px is not None and px.size > 0:
            pm = pixels_to_thumbnail_pixmap(px, size)
    except Exception:
        pass
    return pm
