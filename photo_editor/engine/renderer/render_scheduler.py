"""Render scheduler — debounces requests, cancels stale jobs, limits FPS.

Prevents 500 renders/sec when dragging sliders. Keeps only the latest
request, limits to ~30 FPS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal

from .render_worker import RenderCommand, RenderWorker

if TYPE_CHECKING:
    from ..render_pipeline import RenderPipeline
    from ...core.document import Document


@dataclass
class _PendingJob:
    """A render job waiting to be executed."""

    document: Document
    command: RenderCommand
    generation_id: int
    full_refresh: bool = False  # True = refresh panels too


class RenderScheduler(QObject):
    """Debounces render requests and runs them via RenderWorker.

    - Cancels old pending jobs when a new request arrives
    - Limits FPS to ~30 (33ms interval)
    - Discards stale results (generation_id check)
    - UI never blocks
    """

    render_ready = Signal(object, int, bool, bool)  # (uint8_rgba, generation_id, full_refresh, full_resolution)
    render_error = Signal(str)

    def __init__(
        self,
        pipeline: RenderPipeline,
        final_pipeline: RenderPipeline | None = None,
        interval_ms: int = 33,  # ~30 FPS
        preview_max_size: int = 2048,
    ) -> None:
        super().__init__()
        self._pipeline = pipeline
        self._final_pipeline = final_pipeline or pipeline
        self._interval_ms = interval_ms
        self._preview_max_size = preview_max_size
        self._generation = 0
        self._last_shown_generation = 0  # Only show results newer than this
        self._pending: _PendingJob | None = None
        self._in_flight = False
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._execute_pending)

    def enqueue_render(
        self,
        document: Document,
        full_resolution: bool = False,
        full_refresh: bool = False,
    ) -> None:
        """Request a render. Cancels any pending request; runs at most every interval_ms."""
        if document is None:
            return
        self._generation += 1
        cmd = RenderCommand(
            document_width=document.width,
            document_height=document.height,
            preview_max_size=0 if full_resolution else self._preview_max_size,
            full_resolution=full_resolution,
        )
        self._pending = _PendingJob(
            document=document,
            command=cmd,
            generation_id=self._generation,
            full_refresh=full_refresh,
        )
        if self._in_flight:
            return
        if not self._timer.isActive():
            self._timer.start()

    def set_preview_max_size(self, preview_max_size: int) -> None:
        self._preview_max_size = max(0, int(preview_max_size))

    def enqueue_immediate(
        self,
        document: Document,
        full_resolution: bool = False,
        full_refresh: bool = False,
    ) -> None:
        """Request a render and execute immediately (no debounce)."""
        if document is None:
            return
        self._generation += 1
        cmd = RenderCommand(
            document_width=document.width,
            document_height=document.height,
            preview_max_size=0 if full_resolution else self._preview_max_size,
            full_resolution=full_resolution,
        )
        job = _PendingJob(
            document=document,
            command=cmd,
            generation_id=self._generation,
            full_refresh=full_refresh,
        )
        self._pending = None
        self._timer.stop()
        if self._in_flight:
            self._pending = job
            return
        self._run_worker(job)

    def _execute_pending(self) -> None:
        """Timer fired — run the latest pending job."""
        if self._in_flight:
            return
        job = self._pending
        self._pending = None
        if job is not None:
            self._run_worker(job)

    def _run_worker(self, job: _PendingJob) -> None:
        """Start a RenderWorker for the given job."""
        self._in_flight = True
        pipeline = self._final_pipeline if job.command.full_resolution else self._pipeline
        worker = RenderWorker(
            pipeline=pipeline,
            document=job.document,
            command=job.command,
            generation_id=job.generation_id,
            full_refresh=job.full_refresh,
        )
        worker.signals.finished.connect(self._on_finished)
        worker.signals.error.connect(self._on_error)
        QThreadPool.globalInstance().start(worker)

    def _on_finished(self, rgba: object, generation_id: int, full_refresh: bool, full_resolution: bool) -> None:
        """Worker completed — emit if this is the newest result we've seen.

        During rapid interaction (brush, move, resize), many requests are
        enqueued and _generation advances quickly. We must show the latest
        completed frame rather than discarding everything, or the canvas
        would never update. We only skip results older than what we've
        already shown.
        """
        if generation_id >= self._last_shown_generation:
            self._last_shown_generation = generation_id
            self.render_ready.emit(rgba, generation_id, full_refresh, full_resolution)
        self._in_flight = False
        if self._pending is not None:
            QTimer.singleShot(0, self._execute_pending)

    def _on_error(self, message: str) -> None:
        self._in_flight = False
        if self._pending is not None:
            QTimer.singleShot(0, self._execute_pending)
        self.render_error.emit(message)
