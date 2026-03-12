"""Background render worker — runs compositing off the UI thread.

UI sends RenderCommand via enqueue_render(); the worker produces a preview
bitmap and emits it. UI never blocks on render.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

if TYPE_CHECKING:
    from ..render_pipeline import RenderPipeline
    from ...core.document import Document


@dataclass
class RenderCommand:
    """Immutable render request — document state + target size."""

    document_width: int
    document_height: int
    preview_max_size: int  # max dimension for preview (e.g. 2048)
    full_resolution: bool  # True = export, False = preview


class _RenderWorkerSignals(QObject):
    """Signals emitted when render completes (thread-safe)."""

    finished = Signal(object, int, bool, bool)  # (uint8_rgba, generation_id, full_refresh, full_resolution)
    error = Signal(str)


class RenderWorker(QRunnable):
    """Runs a single render job in the thread pool."""

    def __init__(
        self,
        pipeline: RenderPipeline,
        document: Document,
        command: RenderCommand,
        generation_id: int,
        full_refresh: bool = False,
    ) -> None:
        super().__init__()
        self._pipeline = pipeline
        self._document = document
        self._command = command
        self._generation_id = generation_id
        self._full_refresh = full_refresh
        self.signals = _RenderWorkerSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = self._do_render()
            self.signals.finished.emit(
                result,
                self._generation_id,
                self._full_refresh,
                self._command.full_resolution,
            )
        except Exception as exc:
            self.signals.error.emit(str(exc))

    def _do_render(self) -> np.ndarray:
        """Execute render and return uint8 RGBA."""
        rgba_u8 = self._pipeline.execute_to_uint8(self._document)

        if not self._command.full_resolution and self._command.preview_max_size > 0:
            rgba_u8 = self._downsample_to_preview(rgba_u8)

        return rgba_u8

    def _downsample_to_preview(self, rgba: np.ndarray) -> np.ndarray:
        """Downsample to max preview size (e.g. 2K) for display."""
        h, w = rgba.shape[:2]
        max_dim = self._command.preview_max_size
        if w <= max_dim and h <= max_dim:
            return rgba

        scale = min(max_dim / w, max_dim / h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))

        try:
            import cv2
            return cv2.resize(
                rgba, (new_w, new_h),
                interpolation=cv2.INTER_AREA,
            )
        except ImportError:
            # Fallback: Pillow
            from PIL import Image
            img = Image.fromarray(rgba)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            return np.array(img)
