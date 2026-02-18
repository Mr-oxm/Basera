"""Drag and drop — place image from file manager."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from ...commands import PlaceImageCommand
from ...core.document import Document
from ...utils.image_io import load_image


class DropController:
    """Handles drag-enter and drop events for placing images."""

    def __init__(self) -> None:
        self._mw = None

    def wire(self, main_window) -> None:
        self._mw = main_window

    def on_drag_enter(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def on_drop(self, event) -> None:
        mw = self._mw
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if not path:
                continue
            try:
                img = load_image(path)
                if mw._doc:
                    mw.execute_command(PlaceImageCommand(img, name=Path(path).stem))
                else:
                    h, w = img.shape[:2]
                    mw._doc = Document(w, h, name=Path(path).stem)
                    mw._doc.layers[0].pixels = img
                    mw._doc.save_snapshot("Open Image")
                    mw._open_docs.append((mw._doc, path))
                    mw._file_tabs.add_tab(Path(path).name, tooltip=path)
                    mw._refresh()
                mw._canvas.zoom_to_fit()
            except Exception as exc:
                QMessageBox.warning(mw, "Error", str(exc))
            break
