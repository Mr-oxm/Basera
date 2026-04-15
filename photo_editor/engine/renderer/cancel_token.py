"""Cooperative cancellation token for render jobs.

When a newer render generation supersedes an older one, the old token is
cancelled.  The compositor (or future tile loop) checks the token at each
natural boundary (per layer, per tile) and returns early if cancelled.
This prevents obsolete renders from burning CPU.
"""

from __future__ import annotations

import threading


class CancelToken:
    """Thread-safe cooperative cancellation primitive."""

    __slots__ = ('_cancelled', '_lock')

    def __init__(self) -> None:
        self._cancelled = False
        self._lock = threading.Lock()

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def raise_if_cancelled(self) -> None:
        """Raise ``RenderCancelled`` if the token has been cancelled."""
        if self._cancelled:
            raise RenderCancelled()


class RenderCancelled(Exception):
    """Raised when a render job is cancelled via its CancelToken."""
