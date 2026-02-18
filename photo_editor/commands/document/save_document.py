"""Save document command — runs composite + file write off UI thread."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..base import Command

if TYPE_CHECKING:
    from ...core.document import Document
    from ...engine.render_pipeline import RenderPipeline


class SaveDocumentCommand(Command):
    """Save the composited document to a file.

    Heavy operation: full composite + disk I/O. Intended for
    execute_command_async() to run off the UI thread.
    Caller must call document.mark_clean() and update UI after success.
    """

    def __init__(self, path: str | Path, pipeline: RenderPipeline) -> None:
        self.path = Path(path)
        self._pipeline = pipeline

    def execute(self, document: Document) -> None:
        from ...utils.image_io import save_image
        merged = self._pipeline.execute(document)
        save_image(merged, self.path)
