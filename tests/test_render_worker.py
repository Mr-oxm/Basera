"""Tests for render worker and scheduler."""

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication

from photo_editor.core.document import Document
from photo_editor.engine.render_pipeline import RenderPipeline
from photo_editor.engine.renderer import RenderScheduler, RenderWorker
from photo_editor.engine.renderer.render_worker import RenderCommand


@pytest.fixture
def app():
    """Ensure QCoreApplication exists for Qt signals."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


@pytest.fixture
def doc():
    """Minimal document for rendering."""
    d = Document(64, 64, "Test")
    d.layers[0].pixels[:] = np.array([0.5, 0.5, 0.5, 1.0], dtype=np.float32)
    return d


def test_render_command():
    """RenderCommand has expected fields."""
    cmd = RenderCommand(
        document_width=100,
        document_height=100,
        preview_max_size=2048,
        full_resolution=False,
    )
    assert cmd.document_width == 100
    assert cmd.document_height == 100
    assert cmd.preview_max_size == 2048
    assert cmd.full_resolution is False


def test_render_worker_produces_uint8(doc, app):
    """RenderWorker produces valid uint8 RGBA."""
    pipeline = RenderPipeline()
    cmd = RenderCommand(
        document_width=doc.width,
        document_height=doc.height,
        preview_max_size=0,
        full_resolution=True,
    )
    result_holder = []

    def on_result(rgba, _gen_id, _full_refresh):
        result_holder.append(rgba)

    worker = RenderWorker(
        pipeline=pipeline,
        document=doc,
        command=cmd,
        generation_id=1,
    )
    worker.signals.finished.connect(on_result)
    from PySide6.QtCore import QThreadPool
    QThreadPool.globalInstance().start(worker)
    # Process events until we get a result
    for _ in range(100):
        app.processEvents()
        if result_holder:
            break
        import time
        time.sleep(0.01)

    assert len(result_holder) == 1
    rgba = result_holder[0]
    assert rgba.dtype == np.uint8
    assert rgba.shape == (64, 64, 4)
    assert np.all(rgba[..., 3] == 255)


def test_render_scheduler_debounces(doc, app):
    """RenderScheduler debounces and emits at most one result per batch."""
    pipeline = RenderPipeline()
    scheduler = RenderScheduler(pipeline, interval_ms=10, preview_max_size=0)
    results = []

    def on_ready(rgba, gen_id, full_refresh):
        results.append((rgba, gen_id, full_refresh))

    scheduler.render_ready.connect(on_ready)

    # Enqueue multiple times rapidly
    for _ in range(5):
        scheduler.enqueue_render(doc, full_refresh=False)

    # Process events until we get a result (or timeout)
    for _ in range(200):
        app.processEvents()
        if results:
            break
        import time
        time.sleep(0.01)

    # Should get exactly one result (debounced)
    assert len(results) >= 1
    rgba, gen_id, full_refresh = results[0]
    assert rgba.dtype == np.uint8
    assert rgba.shape == (64, 64, 4)
    assert full_refresh is False
