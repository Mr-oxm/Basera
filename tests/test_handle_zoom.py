"""Tests for transform bounding-box and handle hit-testing across zoom levels and resolutions."""

import pytest
import numpy as np

from photo_editor.core.document import Document
from photo_editor.core.layer import Layer
from photo_editor.tools.move.hit_test import (
    HANDLE_MARGIN,
    ROTATE_HANDLE_OFFSET,
    ROTATE_PROXIMITY,
    hit_test,
    hit_test_rect,
)
from photo_editor.tools.move._enums import _Handle, _Mode
from photo_editor.tools.move.move_tool import MoveTool
from photo_editor.tools.crop_tool import CropTool


def _create_high_res_doc(w: int = 6000, h: int = 4000) -> tuple[Document, Layer]:
    """Create a high-resolution document with a layer."""
    doc = Document(w, h)
    layer = Layer(name="Layer 1", width=2000, height=2000)
    layer.pixels[:] = np.array([1.0, 0.0, 0.0, 1.0], dtype=np.float32)
    layer.position = (1000, 1000)
    doc.layers.add(layer)
    doc.layers.active_index = doc.layers.layers.index(layer)
    return doc, layer


class TestHandleZoomHitTesting:
    """Test that handles can be comfortably clicked regardless of zoom level or resolution."""

    def test_high_res_corner_handle_click(self):
        """At 10% zoom (e.g. 6000x4000 image), clicking within 10 screen pixels of a corner hits the handle."""
        zoom = 0.1  # 1 screen px = 10 doc px
        bx, by, bw, bh = 1000, 1000, 2000, 2000
        corner_x, corner_y = bx + bw, by + bh  # (3000, 3000)

        # User clicks 10 screen pixels away (100 document pixels)
        click_x = corner_x + int(10 / zoom)  # 3100
        click_y = corner_y + int(10 / zoom)  # 3100

        mode, handle = hit_test_rect(bx, by, bw, bh, click_x, click_y, zoom=zoom)
        assert mode == _Mode.RESIZE
        assert handle == _Handle.BR

    def test_high_res_rotation_handle_click(self):
        """At 10% zoom, clicking on the rotation handle drawn 25 screen pixels above top-center hits ROTATE."""
        zoom = 0.1  # 1 screen px = 10 doc px
        bx, by, bw, bh = 1000, 1000, 2000, 2000
        mid_x = bx + bw / 2.0

        # Rotation handle drawn at ROTATE_HANDLE_OFFSET (25 screen px) above top
        click_x = mid_x
        click_y = by - int(ROTATE_HANDLE_OFFSET / zoom)  # 1000 - 250 = 750

        mode, handle = hit_test_rect(bx, by, bw, bh, click_x, click_y, zoom=zoom)
        assert mode == _Mode.ROTATE

    def test_zoomed_in_handle_does_not_balloon(self):
        """At 400% zoom, handle hit target remains ~14 screen pixels (3.5 doc px), not huge."""
        zoom = 4.0  # 1 screen px = 0.25 doc px
        bx, by, bw, bh = 100, 100, 200, 200
        corner_x, corner_y = bx + bw, by + bh  # (300, 300)

        # Click 5 document pixels away = 20 screen pixels away -> should miss handle (outside 14 screen px)
        click_x = corner_x + 5
        click_y = corner_y + 5

        mode, handle = hit_test_rect(bx, by, bw, bh, click_x, click_y, zoom=zoom)
        assert handle != _Handle.BR

    def test_move_tool_hit_test_with_view_zoom(self):
        """MoveTool._hit_test uses view_zoom to correctly detect handle clicks on high-res layers."""
        doc, layer = _create_high_res_doc(6000, 4000)
        tool = MoveTool()
        tool.view_zoom = 0.1

        # Press on BR handle (within 8 screen pixels = 80 doc pixels)
        tool.on_press(doc, 3080, 3080)
        assert tool._mode == _Mode.RESIZE
        assert tool._handle == _Handle.BR

    def test_closest_handle_selected_on_overlap(self):
        """When multiple handles are within tolerance (e.g. small box or low zoom), closest is chosen."""
        zoom = 0.1
        bx, by, bw, bh = 1000, 1000, 200, 200  # only 20x20 screen pixels!
        # Click very close to TR corner
        click_x = bx + bw - 2  # 1198
        click_y = by + 2       # 1002

        mode, handle = hit_test_rect(bx, by, bw, bh, click_x, click_y, zoom=zoom)
        assert mode == _Mode.RESIZE
        assert handle == _Handle.TR

    def test_crop_tool_zoom_hit_test(self):
        """CropTool handles can be clicked when zoomed out on high-res image."""
        crop = CropTool()
        crop.view_zoom = 0.1
        crop._box = (1000, 1000, 2000, 2000)

        # Click within 8 screen pixels (80 doc px) of BR handle (3000, 3000)
        hit = crop.hit_test(3080, 3080)
        assert hit == "BR"
