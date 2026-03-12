"""Alignment, flip, and 90°-rotate helpers for the Move tool.

All functions are standalone (no ``self``) so they can be called
directly on a ``Document`` from menu actions, keyboard shortcuts, or
any other tool that wants the same behaviour.

Exported symbols
----------------
align_left(doc)         Align active layer's left edge to canvas left.
align_center_h(doc)     Horizontally centre the active layer on canvas.
align_right(doc)        Align right edge to canvas right.
align_top(doc)          Align top edge to canvas top.
align_middle_v(doc)     Vertically centre the active layer on canvas.
align_bottom(doc)       Align bottom edge to canvas bottom.

flip_horizontal(doc)    Flip the active layer along the Y axis.
flip_vertical(doc)      Flip the active layer along the X axis.
rotate_90_cw(doc)       Rotate 90° clockwise, keeping the centre fixed.
rotate_90_ccw(doc)      Rotate 90° counter-clockwise, keeping centre.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ...transforms.transform_engine import TransformEngine

if TYPE_CHECKING:
    from ...core.document import Document


# ---------------------------------------------------------------------------
# Alignment helpers
# ---------------------------------------------------------------------------


def align_left(doc: "Document") -> None:
    """Align the active layer's left edge to the canvas left edge."""
    layer = doc.layers.active_layer
    if layer is None or layer.locked:
        return
    _, ly = layer.position
    new_pos = (0, ly)
    if new_pos != layer.position:
        doc.save_metadata_snapshot("Align Left")
        layer.position = new_pos


def align_center_h(doc: "Document") -> None:
    """Horizontally centre the active layer on the canvas."""
    layer = doc.layers.active_layer
    if layer is None or layer.locked:
        return
    _, ly = layer.position
    new_pos = ((doc.width - layer.width) // 2, ly)
    if new_pos != layer.position:
        doc.save_metadata_snapshot("Align Center H")
        layer.position = new_pos


def align_right(doc: "Document") -> None:
    """Align the active layer's right edge to the canvas right edge."""
    layer = doc.layers.active_layer
    if layer is None or layer.locked:
        return
    _, ly = layer.position
    new_pos = (doc.width - layer.width, ly)
    if new_pos != layer.position:
        doc.save_metadata_snapshot("Align Right")
        layer.position = new_pos


def align_top(doc: "Document") -> None:
    """Align the active layer's top edge to the canvas top edge."""
    layer = doc.layers.active_layer
    if layer is None or layer.locked:
        return
    lx, _ = layer.position
    new_pos = (lx, 0)
    if new_pos != layer.position:
        doc.save_metadata_snapshot("Align Top")
        layer.position = new_pos


def align_middle_v(doc: "Document") -> None:
    """Vertically centre the active layer on the canvas."""
    layer = doc.layers.active_layer
    if layer is None or layer.locked:
        return
    lx, _ = layer.position
    new_pos = (lx, (doc.height - layer.height) // 2)
    if new_pos != layer.position:
        doc.save_metadata_snapshot("Align Middle V")
        layer.position = new_pos


def align_bottom(doc: "Document") -> None:
    """Align the active layer's bottom edge to the canvas bottom edge."""
    layer = doc.layers.active_layer
    if layer is None or layer.locked:
        return
    lx, _ = layer.position
    new_pos = (lx, doc.height - layer.height)
    if new_pos != layer.position:
        doc.save_metadata_snapshot("Align Bottom")
        layer.position = new_pos


# ---------------------------------------------------------------------------
# Flip helpers
# ---------------------------------------------------------------------------


def flip_horizontal(doc: "Document") -> None:
    """Flip the active layer horizontally (mirror along the Y axis).

    Always operates through the non-destructive source so the rotated
    bounding-box is preserved regardless of whether the layer has been
    previously interacted with.

    Math: flip_H(rotate(src, A)) ≡ rotate(flip_H(src), −A)
    """
    layer = doc.layers.active_layer
    if layer is None or layer.locked:
        return
    doc.save_snapshot("Flip Horizontal")
    # init_non_destructive is idempotent — snapshots pixels as source on
    # first call and does nothing on subsequent calls.  Calling it here
    # ensures the ND path is always taken even on a freshly placed layer.
    layer.init_non_destructive()
    layer._source_pixels = TransformEngine.flip_h(layer._source_pixels)
    if layer._source_mask is not None:
        layer._source_mask = np.flip(layer._source_mask, axis=1).copy()
    layer.transform_angle = -layer.transform_angle
    layer.compute_display()


def flip_vertical(doc: "Document") -> None:
    """Flip the active layer vertically (mirror along the X axis).

    Always operates through the non-destructive source so the rotated
    bounding-box is preserved regardless of prior interaction.

    Math: flip_V(rotate(src, A)) ≡ rotate(flip_V(src), −A)
    """
    layer = doc.layers.active_layer
    if layer is None or layer.locked:
        return
    doc.save_snapshot("Flip Vertical")
    layer.init_non_destructive()
    layer._source_pixels = TransformEngine.flip_v(layer._source_pixels)
    if layer._source_mask is not None:
        layer._source_mask = np.flip(layer._source_mask, axis=0).copy()
    layer.transform_angle = -layer.transform_angle
    layer.compute_display()


# ---------------------------------------------------------------------------
# 90° rotation helpers
# ---------------------------------------------------------------------------


def rotate_90_cw(doc: "Document") -> None:
    """Rotate the active layer 90° clockwise, keeping the centre in place.

    Always operates through the non-destructive source so no pixel quality
    is lost and the rotated bounding-box is correct on the very first call,
    even on a freshly placed layer.

    Math: rotate_90_cw(rotate(src, A)) ≡ rotate(src, A − 90°)
    """
    layer = doc.layers.active_layer
    if layer is None or layer.locked:
        return
    doc.save_snapshot("Rotate 90° CW")
    # Capture visual centre before dims change.
    lx, ly = layer.position
    cx = lx + layer.width / 2.0
    cy = ly + layer.height / 2.0
    # Ensure ND source exists (idempotent on subsequent calls).
    layer.init_non_destructive()
    layer.transform_angle -= 90.0
    layer.compute_display()
    layer.position = (int(cx - layer.width / 2), int(cy - layer.height / 2))


def rotate_90_ccw(doc: "Document") -> None:
    """Rotate the active layer 90° counter-clockwise, keeping the centre in place.

    Always operates through the non-destructive source so no pixel quality
    is lost and the rotated bounding-box is correct on the very first call.

    Math: rotate_90_ccw(rotate(src, A)) ≡ rotate(src, A + 90°)
    """
    layer = doc.layers.active_layer
    if layer is None or layer.locked:
        return
    doc.save_snapshot("Rotate 90° CCW")
    lx, ly = layer.position
    cx = lx + layer.width / 2.0
    cy = ly + layer.height / 2.0
    layer.init_non_destructive()
    layer.transform_angle += 90.0
    layer.compute_display()
    layer.position = (int(cx - layer.width / 2), int(cy - layer.height / 2))
