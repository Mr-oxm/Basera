import numpy as np
from PySide6.QtCore import QPointF

from photo_editor.ui.canvas_view import CanvasView
from photo_editor.ui.status_bar import EditorStatusBar


def test_canvas_zoom_anchor_keeps_doc_point_stable(qtbot):
    canvas = CanvasView()
    qtbot.addWidget(canvas)
    canvas.resize(400, 300)
    canvas.set_image(np.zeros((100, 200, 4), dtype=np.uint8), force=True)
    canvas.set_zoom(2.0)

    anchor = QPointF(300.0, 150.0)
    before = canvas._canvas_to_doc_float(anchor)

    canvas.zoom_by(1.5, anchor=anchor)
    after = canvas._canvas_to_doc_float(anchor)

    assert abs(before.x() - after.x()) < 1e-6
    assert abs(before.y() - after.y()) < 1e-6


def test_canvas_proxy_image_preserves_document_dimensions(qtbot):
    canvas = CanvasView()
    qtbot.addWidget(canvas)
    canvas.resize(400, 300)
    canvas.set_image(
        np.zeros((100, 200, 4), dtype=np.uint8),
        force=True,
        document_size=(1200, 600),
    )

    assert canvas._doc_h == 600
    assert canvas._doc_w == 1200

    doc_rect = canvas._doc_rect()
    point = canvas._doc_to_widget(doc_rect, 600.0, 300.0)
    mapped = canvas._canvas_to_doc_float(point)

    assert abs(mapped.x() - 600.0) < 1e-6
    assert abs(mapped.y() - 300.0) < 1e-6


def test_status_bar_zoom_to_mouse_property_and_signal(qtbot):
    status = EditorStatusBar()
    qtbot.addWidget(status)

    values = []
    status.zoom_to_mouse_changed.connect(values.append)

    assert status.zoom_to_mouse is True

    status.zoom_to_mouse = False

    assert status.zoom_to_mouse is False
    assert values[-1] is False