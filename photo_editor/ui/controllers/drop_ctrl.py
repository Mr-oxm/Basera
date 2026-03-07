"""Drag and drop — place image from file manager."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from ...commands import PlaceImageCommand
from ...core.document import Document
from ...utils.image_io import load_image
from .base import ControllerBase


class DropController(ControllerBase):
    """Handles drag-enter and drop events for placing images."""

    def __init__(self) -> None:
        super().__init__()

    def wire(self, main_window) -> None:
        super().wire(main_window)

    def on_drag_enter(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def on_drop(self, event) -> None:
        mw = self.mw
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if not path:
                continue
            try:
                img = load_image(path)
                if self.doc:
                    self.ctx.execute_command(PlaceImageCommand(img, name=Path(path).stem))
                else:
                    h, w = img.shape[:2]
                    document = Document(w, h, name=Path(path).stem)
                    document.layers[0].pixels = img
                    document.save_snapshot("Open Image")
                    mw._document_session.add(document, path, title=Path(path).name)
                    self.ctx.set_document(document)
                    self.ctx.set_document_info(document.name, document.width, document.height)
                    self.ctx.set_window_title(f"Basera — {Path(path).name}")
                    self.ctx.refresh()
                self.ctx.zoom_to_fit()
            except Exception as exc:
                QMessageBox.warning(mw, "Error", str(exc))
            break
