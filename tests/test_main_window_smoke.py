"""Smoke tests for MainWindow and controllers."""

import pytest
from PySide6.QtWidgets import QApplication

from photo_editor.ui.controllers import (
    CanvasController,
    ColorController,
    DropController,
    CropController,
    DocumentController,
    FilterController,
    GradientController,
    LayerController,
    SelectionController,
    ShortcutController,
    TextController,
    ToolController,
    TransformController,
    VectorController,
    ViewController,
)
from photo_editor.ui.main_window import MainWindow


def test_controller_imports():
    """All controllers can be imported."""
    assert CanvasController is not None
    assert ColorController is not None
    assert DropController is not None
    assert CropController is not None
    assert DocumentController is not None
    assert FilterController is not None
    assert GradientController is not None
    assert LayerController is not None
    assert SelectionController is not None
    assert ShortcutController is not None
    assert TextController is not None
    assert ToolController is not None
    assert TransformController is not None
    assert VectorController is not None
    assert ViewController is not None


def test_main_window_launch(qtbot):
    """MainWindow can be created and closed."""
    app = QApplication.instance()
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    w.close()
    assert w.isHidden() or not w.isVisible()


def test_main_window_preview_budget_tracks_viewport(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w._canvas.resize(400, 300)

    size = w._effective_preview_max_size()

    assert 512 <= size <= 2048
    assert size == 750
