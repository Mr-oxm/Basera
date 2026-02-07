"""Off-main-thread worker for heavy image operations."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class _WorkerSignals(QObject):
    finished = Signal()
    error = Signal(str)
    result = Signal(object)
    progress = Signal(int)


class Worker(QRunnable):
    """Generic worker that runs a callable in the Qt thread pool."""

    def __init__(self, fn: Callable, *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = _WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()

    @staticmethod
    def pool() -> QThreadPool:
        return QThreadPool.globalInstance()

    @classmethod
    def run_async(
        cls,
        fn: Callable,
        *args: Any,
        on_result: Callable | None = None,
        on_error: Callable | None = None,
        on_done: Callable | None = None,
        **kwargs: Any,
    ) -> Worker:
        """Convenience: create, connect signals, and start a worker."""
        worker = cls(fn, *args, **kwargs)
        if on_result:
            worker.signals.result.connect(on_result)
        if on_error:
            worker.signals.error.connect(on_error)
        if on_done:
            worker.signals.finished.connect(on_done)
        cls.pool().start(worker)
        return worker
