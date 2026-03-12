"""Layer auto-selection helpers.

These functions are *tool-agnostic* and are shared between the Move tool
and the Node tool (and any other tool that needs to pick the topmost
visible layer under the cursor).

Exported symbols
----------------
point_on_layer(layer, x, y, alpha_threshold)
    Return ``True`` when the document-coord point *(x, y)* lands on a
    non-transparent pixel of *layer*.  Text layers use a bounding-box
    test (optionally accounting for rotation) so that clicking anywhere
    inside the text area counts as a hit.

find_layer_at(doc, x, y, exclude_id, alpha_threshold)
    Walk the layer stack from top to bottom and return the *stack index*
    of the first visible, non-locked, non-group, non-adjustment layer
    whose opaque area covers the point.  Returns ``None`` on a miss.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ...core.enums import LayerType

if TYPE_CHECKING:
    from ...core.document import Document


def point_on_layer(
    layer,
    x: int,
    y: int,
    alpha_threshold: float = 0.01,
) -> bool:
    """Return ``True`` if document-coord *(x, y)* hits *layer*.

    Text layers are tested against the text bounding box (supporting
    rotation) so clicking anywhere inside the text area is a hit.
    All other layer types use a pixel-level alpha test.
    """
    lx, ly = layer.position

    # --- Text layers: bounding-box hit-test (supports rotation) -------
    if layer.layer_type == LayerType.TEXT:
        td = getattr(layer, "_text_data", None)
        if td is not None:
            angle = layer.transform_angle
            bw, bh = td.box_width, td.box_height
            if angle != 0.0:
                cx = lx + bw / 2
                cy = ly + bh / 2
                rad = math.radians(angle)
                dx, dy = x - cx, y - cy
                rx = dx * math.cos(rad) + dy * math.sin(rad)
                ry = -dx * math.sin(rad) + dy * math.cos(rad)
                return abs(rx) <= bw / 2 and abs(ry) <= bh / 2
            return lx <= x <= lx + bw and ly <= y <= ly + bh

    # --- Raster / shape layers: pixel alpha test ----------------------
    px, py = x - lx, y - ly
    h, w = int(layer.height), int(layer.width)
    if px < 0 or px >= w or py < 0 or py >= h:
        return False
    pixel = layer.read_display_pixel_float(px, py)
    if pixel is None:
        return False
    return float(pixel[3]) >= alpha_threshold


def find_layer_at(
    doc: "Document",
    x: int,
    y: int,
    exclude_id: str | None = None,
    alpha_threshold: float = 0.01,
) -> int | None:
    """Return the *stack index* of the topmost visible layer at *(x, y)*.

    Iterates from the top of the stack downward.  Group, adjustment,
    filter, and mask layers are skipped.  Hidden layers are always
    skipped — they can only be selected via the layers panel.
    Returns ``None`` when no layer is found.

    Parameters
    ----------
    doc:
        The active document.
    x, y:
        Position in document (pixel) coordinates.
    exclude_id:
        If supplied, the layer with this ``id`` is skipped (useful for
        excluding the current active layer during auto-select).
    alpha_threshold:
        Minimum alpha value (0–1) for a pixel to be considered opaque.
    """
    skip_types = (
        LayerType.GROUP,
        LayerType.ADJUSTMENT,
        LayerType.FILTER,
        LayerType.MASK,
    )
    for i in range(len(doc.layers) - 1, -1, -1):
        layer = doc.layers.layers[i]
        if not layer.visible or layer.locked:
            continue
        if layer.layer_type in skip_types:
            continue
        if exclude_id is not None and layer.id == exclude_id:
            continue
        if point_on_layer(layer, x, y, alpha_threshold):
            return i
    return None
