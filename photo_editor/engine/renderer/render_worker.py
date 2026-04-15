"""Background render worker — runs compositing off the UI thread.

UI sends RenderCommand via enqueue_render(); the worker produces a preview
bitmap and emits it. UI never blocks on render.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from .cancel_token import CancelToken, RenderCancelled

if TYPE_CHECKING:
    from ..render_pipeline import RenderPipeline
    from ...core.document import Document
    from .render_snapshot import RenderSnapshot


@dataclass
class RenderCommand:
    """Immutable render request — document state + target size."""

    document_width: int
    document_height: int
    preview_max_size: int  # max dimension for preview (e.g. 2048)
    full_resolution: bool  # True = export, False = preview


class _RenderWorkerSignals(QObject):
    """Signals emitted when render completes (thread-safe)."""

    finished = Signal(object, int, bool)  # (uint8_rgba, generation_id, full_refresh)
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
        snapshot: RenderSnapshot | None = None,
        cancel_token: CancelToken | None = None,
    ) -> None:
        super().__init__()
        self._pipeline = pipeline
        self._document = document
        self._command = command
        self._generation_id = generation_id
        self._full_refresh = full_refresh
        self._snapshot = snapshot
        self._cancel_token = cancel_token or CancelToken()
        self.signals = _RenderWorkerSignals()
        self.setAutoDelete(True)

    @property
    def cancel_token(self) -> CancelToken:
        return self._cancel_token

    def run(self) -> None:
        try:
            result = self._do_render()
            if self._cancel_token.is_cancelled:
                return
            self.signals.finished.emit(result, self._generation_id, self._full_refresh)
        except RenderCancelled:
            pass
        except Exception as exc:
            if not self._cancel_token.is_cancelled:
                self.signals.error.emit(str(exc))

    def _do_render(self) -> np.ndarray:
        """Execute render and return uint8 RGBA."""
        # Determine if we should composite at reduced resolution
        preview_scale = self._compute_preview_scale()

        if preview_scale < 1.0 and self._snapshot is not None:
            rgba_float = self._pipeline.execute_at_scale(
                self._document, preview_scale, snapshot=self._snapshot,
            )
        else:
            rgba_float = self._pipeline.execute(
                self._document, snapshot=self._snapshot,
                cancel_token=self._cancel_token,
            )

        rgba_u8 = np.clip(rgba_float * 255, 0, 255).astype(np.uint8)
        return rgba_u8

    def _compute_preview_scale(self) -> float:
        """Return the scale factor for preview compositing.

        Returns 1.0 for full-resolution renders, or a fraction (e.g.
        0.5) for interactive preview.
        """
        if self._command.full_resolution or self._command.preview_max_size <= 0:
            return 1.0
        w = self._command.document_width
        h = self._command.document_height
        max_dim = self._command.preview_max_size
        if w <= max_dim and h <= max_dim:
            return 1.0
        return min(max_dim / w, max_dim / h)
