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

    def __init__(
        self,
        path: str | Path,
        pipeline: RenderPipeline,
        quality: int = 95,
        *,
        target_size: tuple[int, int] | None = None,
        jpeg_bg: tuple[int, int, int] = (255, 255, 255),
        subsampling: int = 0,
    ) -> None:
        self.path = Path(path)
        self._pipeline = pipeline
        self._quality = int(quality)
        self._target_size = target_size
        self._jpeg_bg = jpeg_bg
        self._subsampling = subsampling

    def execute(self, document: Document) -> None:
        suffix = self.path.suffix.lower()
        if suffix == ".basera":
            from ...utils.project_io import save_basera_project

            save_basera_project(document, self.path)
            return

        from ...utils.image_io import save_image

        merged = self._pipeline.execute(document)
        save_image(
            merged,
            self.path,
            quality=self._quality,
            target_size=self._target_size,
            jpeg_bg=self._jpeg_bg,
            subsampling=self._subsampling,
        )
