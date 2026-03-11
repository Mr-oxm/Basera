"""Bounding-box and handle hit-testing helpers for the Move tool.

All functions operate in *document* (pixel) coordinates.

Exported symbols
----------------
HANDLE_MARGIN           Hit-test radius (px) for resize / rotate handles.
ROTATE_HANDLE_OFFSET    Distance above the top-centre edge for the
                        rotation handle node.

bbox(doc)               Return (x, y, w, h) of the active layer, or the
                        union of all children if the layer is a group.
group_bbox(doc, group)  Return (x, y, w, h) that covers every child of
                        *group*.
hit_test(doc, x, y, current_angle)
                        Return (Mode, Handle) for a click at *(x, y)*.
                        Pass the tool's ``_current_angle`` (mid-drag
                        accumulator) so the rotated box is taken into
                        account.
hit_test_rect(bx, by, bw, bh, x, y)
                        Low-level rectangle hit-test.  Returns
                        ``(Mode, Handle)`` according to the priority:
                        rotation node → resize handles → interior →
                        outside (rotation zone).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ._enums import _Mode, _Handle
from ...core.enums import LayerType

if TYPE_CHECKING:
    from ...core.document import Document

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HANDLE_MARGIN = 14        # hit-test radius in document pixels (slightly expanded)
ROTATE_HANDLE_OFFSET = 25  # distance above top-centre for rotation handle
ROTATE_PROXIMITY = 50     # max distance from a corner/rotation node for rotate cursor

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def bbox(doc: "Document") -> tuple[int, int, int, int] | None:
    """Return ``(x, y, w, h)`` bounding box of the active layer in document coords.

    For group layers the box is the union of all child-layer bounding boxes.
    When multiple layers are selected, returns the union of all selected layers.
    Returns ``None`` when there is no active layer.
    """
    # Multi-selection: union of all selected layers
    sel = doc.layers.selected_indices
    if len(sel) > 1:
        return multi_bbox(doc)

    layer = doc.layers.active_layer
    if layer is None:
        return None
    if layer.layer_type == LayerType.GROUP:
        return group_bbox(doc, layer)
    # Non-group parent with children (pseudo-group) — BB uses the parent's
    # own bounds only.  Clipped children are masked to the parent's shape
    # so their overflow is invisible and must NOT inflate the BB.
    if layer.children:
        lx, ly = layer.position
        return (lx, ly, layer.width, layer.height)
    lx, ly = layer.position
    return (lx, ly, layer.width, layer.height)


def multi_bbox(doc: "Document") -> tuple[int, int, int, int] | None:
    """Return ``(x, y, w, h)`` covering all currently selected layers."""
    min_x, min_y = float("inf"), float("inf")
    max_x, max_y = float("-inf"), float("-inf")
    found = False
    for i in doc.layers.selected_indices:
        if 0 <= i < len(doc.layers.layers):
            layer = doc.layers.layers[i]
            if layer.layer_type == LayerType.GROUP:
                gb = group_bbox(doc, layer)
                if gb:
                    min_x = min(min_x, gb[0])
                    min_y = min(min_y, gb[1])
                    max_x = max(max_x, gb[0] + gb[2])
                    max_y = max(max_y, gb[1] + gb[3])
                    found = True
            else:
                lx, ly = layer.position
                min_x = min(min_x, lx)
                min_y = min(min_y, ly)
                max_x = max(max_x, lx + layer.width)
                max_y = max(max_y, ly + layer.height)
                found = True
    if not found:
        return None
    return (int(min_x), int(min_y), int(max_x - min_x), int(max_y - min_y))


def group_bbox(doc: "Document", group) -> tuple[int, int, int, int] | None:
    """Return ``(x, y, w, h)`` covering every direct child of *group*.

    Falls back to the group's own position/size when the group has no
    child layers.
    """
    min_x, min_y = float("inf"), float("inf")
    max_x, max_y = float("-inf"), float("-inf")
    found = False
    for child in doc.layers:
        if child.parent_id != group.id:
            continue
        cx, cy = child.position
        min_x = min(min_x, cx)
        min_y = min(min_y, cy)
        max_x = max(max_x, cx + child.width)
        max_y = max(max_y, cy + child.height)
        found = True
    if not found:
        lx, ly = group.position
        return (lx, ly, group.width, group.height)
    return (int(min_x), int(min_y), int(max_x - min_x), int(max_y - min_y))


def hit_test(
    doc: "Document",
    x: int,
    y: int,
    current_angle: float = 0.0,
) -> tuple[_Mode, _Handle]:
    """Return ``(Mode, Handle)`` for a click at *(x, y)*.

    Parameters
    ----------
    doc:
        The active document.
    x, y:
        Click position in document coordinates.
    current_angle:
        Any mid-drag rotation that has not yet been committed to
        ``layer.transform_angle`` (the tool's ``_current_angle``).
    """
    layer = doc.layers.active_layer
    if layer is None:
        return _Mode.NONE, _Handle.NONE

    # Multi-selection: always hit-test against the union multi-bbox.
    # Skip the single-layer rotation branch — the multi-bbox is axis-aligned
    # and represents the combined bounds of all selected layers.
    sel = doc.layers.selected_indices
    if len(sel) > 1:
        bb = multi_bbox(doc)
        if bb is None:
            return _Mode.NONE, _Handle.NONE
        return hit_test_rect(bb[0], bb[1], bb[2], bb[3], x, y)

    # Non-group parent with children (pseudo-group) — hit-test uses the
    # parent's own bounds.  When the parent is rotated, inverse-rotate
    # the click point into the parent's local frame (same as single layer).
    if layer.children:
        total_angle = layer.transform_angle + current_angle
        if total_angle != 0.0 and layer.transform_base_w > 0:
            lx, ly = layer.position
            cx = lx + layer.width / 2
            cy = ly + layer.height / 2
            rad = math.radians(total_angle)
            dx, dy = x - cx, y - cy
            rx = dx * math.cos(rad) - dy * math.sin(rad)
            ry = dx * math.sin(rad) + dy * math.cos(rad)
            return hit_test_rect(
                -layer.transform_base_w / 2,
                -layer.transform_base_h / 2,
                layer.transform_base_w,
                layer.transform_base_h,
                rx, ry,
            )
        bb = bbox(doc)
        if bb is None:
            return _Mode.NONE, _Handle.NONE
        return hit_test_rect(bb[0], bb[1], bb[2], bb[3], x, y)

    total_angle = layer.transform_angle + current_angle

    # When the layer has accumulated rotation, inverse-rotate the click
    # point into the box's local frame before testing.
    if total_angle != 0.0 and layer.transform_base_w > 0:
        lx, ly = layer.position
        cx = lx + layer.width / 2
        cy = ly + layer.height / 2
        rad = math.radians(total_angle)
        dx, dy = x - cx, y - cy
        # Inverse of the rotation applied by QPainter
        rx = dx * math.cos(rad) - dy * math.sin(rad)
        ry = dx * math.sin(rad) + dy * math.cos(rad)
        return hit_test_rect(
            -layer.transform_base_w / 2,
            -layer.transform_base_h / 2,
            layer.transform_base_w,
            layer.transform_base_h,
            rx, ry,
        )

    # Normal (no rotation) hit-test on current layer bounds
    bb = bbox(doc)
    if bb is None:
        return _Mode.NONE, _Handle.NONE
    bx, by, bw, bh = bb
    return hit_test_rect(bx, by, bw, bh, x, y)


def hit_test_rect(
    bx: float, by: float, bw: float, bh: float,
    x: float, y: float,
) -> tuple[_Mode, _Handle]:
    """Hit-test *(x, y)* against a rectangle and its transform handles.

    Detection priority
    ------------------
    1. Rotation handle node (circle above top-centre)
    2. Resize handles (TL, T, TR, L, R, BL, B, BR) — expanded hit area
    3. Bounding box border lines (thin margin strip)
    4. Interior  → ``(MOVE, NONE)``
    5. Near a corner within ROTATE_PROXIMITY → ``(ROTATE, NONE)``
    6. Everything else → ``(NONE, NONE)``   (no interaction)
    """
    m = HANDLE_MARGIN
    rh_offset = ROTATE_HANDLE_OFFSET
    mx, my = bx + bw / 2, by + bh / 2

    # 1. Rotation handle node above top-centre
    rh_x, rh_y = mx, by - rh_offset
    if abs(x - rh_x) <= m and abs(y - rh_y) <= m:
        return _Mode.ROTATE, _Handle.NONE

    # 2. Resize handles (expanded hit area)
    handles = [
        (_Handle.TL, bx,       by),
        (_Handle.T,  mx,       by),
        (_Handle.TR, bx + bw,  by),
        (_Handle.L,  bx,       my),
        (_Handle.R,  bx + bw,  my),
        (_Handle.BL, bx,       by + bh),
        (_Handle.B,  mx,       by + bh),
        (_Handle.BR, bx + bw,  by + bh),
    ]
    for hid, hx, hy in handles:
        if abs(x - hx) <= m and abs(y - hy) <= m:
            return _Mode.RESIZE, hid

    # 3. Bounding box border lines (thin strip around the edges)
    border = 6  # pixels either side of the border line
    inside_outer = (bx - border <= x <= bx + bw + border
                    and by - border <= y <= by + bh + border)
    inside_inner = (bx + border < x < bx + bw - border
                    and by + border < y < by + bh - border)
    if inside_outer and not inside_inner:
        return _Mode.MOVE, _Handle.NONE

    # 4. Interior
    if bx <= x <= bx + bw and by <= y <= by + bh:
        return _Mode.MOVE, _Handle.NONE

    # 5. Rotation zones — only near corners and rotation handle, within
    #    ROTATE_PROXIMITY distance from the closest corner.
    rp = ROTATE_PROXIMITY
    corners = [
        (bx,       by),        # TL
        (bx + bw,  by),        # TR
        (bx,       by + bh),   # BL
        (bx + bw,  by + bh),   # BR
        (rh_x,     rh_y),      # rotation node
    ]
    for (cx, cy) in corners:
        dist_sq = (x - cx) ** 2 + (y - cy) ** 2
        if dist_sq <= rp * rp:
            return _Mode.ROTATE, _Handle.NONE

    # 6. Everything else — no interaction
    return _Mode.NONE, _Handle.NONE
