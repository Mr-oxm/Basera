"""Drag & drop state management and helpers for the layers panel."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF

from .base import INDENT_WIDTH, MAX_INDENT_DEPTH, ROW_HEIGHT, THUMB_SIZE

if TYPE_CHECKING:
    pass


class DropMode(Enum):
    """Three mutually-exclusive drop operations."""
    REORDER = auto()
    NEST = auto()
    CLIP = auto()


@dataclass
class DragState:
    """Mutable drag state kept in a ref-like object to avoid re-renders.

    Only ``committed`` is written to widget state on pointerup.
    """
    dragging: bool = False
    drag_started: bool = False       # True after pointer moves past threshold
    dragged_ids: list[str] = field(default_factory=list)
    dragged_locked: bool = False     # True if any dragged layer is locked
    source_parent_id: str | None = None
    source_indices: list[int] = field(default_factory=list)  # display-order rows

    # Live tracking (updated every pointermove, no re-render)
    pointer_x: float = 0.0
    pointer_y: float = 0.0
    start_x: float = 0.0
    start_y: float = 0.0

    # Computed drop target
    drop_target_id: str | None = None
    drop_target_row: int = -1
    drop_mode: DropMode | None = None
    insert_index: int = -1

    # Unparent / eject state
    target_depth: int = 0
    eject_timer_active: bool = False
    eject_shown: bool = False

    # Gap animation
    gap_index: int = -1           # display row where gap is shown

    # Committed flag
    committed: bool = False

    def reset(self) -> None:
        self.dragging = False
        self.drag_started = False
        self.dragged_ids.clear()
        self.dragged_locked = False
        self.source_parent_id = None
        self.source_indices.clear()
        self.pointer_x = 0.0
        self.pointer_y = 0.0
        self.start_x = 0.0
        self.start_y = 0.0
        self.drop_target_id = None
        self.drop_target_row = -1
        self.drop_mode = None
        self.insert_index = -1
        self.target_depth = 0
        self.eject_timer_active = False
        self.eject_shown = False
        self.gap_index = -1
        self.committed = False


# ---------------------------------------------------------------------------
# Helper: detect circular reparent (drag group onto its own descendant)
# ---------------------------------------------------------------------------

def is_descendant_of(
    layer_id: str,
    potential_ancestor_ids: set[str],
    children_map: dict[str, list[str]],
) -> bool:
    """Return True if *layer_id* is a descendant of any id in *potential_ancestor_ids*."""
    visited: set[str] = set()
    stack = list(potential_ancestor_ids)
    while stack:
        nid = stack.pop()
        if nid in visited:
            continue
        visited.add(nid)
        for child_id in children_map.get(nid, []):
            if child_id == layer_id:
                return True
            stack.append(child_id)
    return False


# ---------------------------------------------------------------------------
# Helper: determine drop mode from pointer position
# ---------------------------------------------------------------------------

def get_drop_mode(
    pointer_x: float,
    pointer_y: float,
    target_row_rect: QRectF,
    thumbnail_rect: QRectF | None,
    target_indent: int,
) -> DropMode:
    """Return 'reorder', 'nest', or 'clip' based on pointer position.

    Parameters
    ----------
    pointer_x, pointer_y : cursor position in list-widget coordinates.
    target_row_rect : bounding rect of the target row.
    thumbnail_rect : bounding rect of the layer thumbnail (in list-widget coords).
    target_indent : indentation level of the target row.
    """
    # Mode C — CLIP: pointer over the thumbnail preview
    if thumbnail_rect is not None and thumbnail_rect.contains(QPointF(pointer_x, pointer_y)):
        return DropMode.CLIP

    rel_y = pointer_y - target_row_rect.top()
    row_h = target_row_rect.height()

    # Mode A — REORDER: top 25% or bottom 25%
    if rel_y < row_h * 0.25 or rel_y > row_h * 0.75:
        return DropMode.REORDER

    # Middle 50%: check X position for nest vs reorder
    indent_x = target_indent * INDENT_WIDTH
    if pointer_x > indent_x + INDENT_WIDTH:
        return DropMode.NEST

    return DropMode.REORDER


# ---------------------------------------------------------------------------
# Helper: compute insertion index from pointer Y
# ---------------------------------------------------------------------------

def get_drop_index(
    pointer_y: float,
    row_tops: list[float],
    row_count: int,
    row_heights: list[float] | None = None,
) -> int:
    """Map cursor Y to the correct insertion index by comparing against each row's midpoint.

    Parameters
    ----------
    pointer_y : cursor Y in scroll-content coordinates.
    row_tops : list of Y-top for each row in display order.
    row_count : total number of rows.
    row_heights : optional per-row heights.  When provided, midpoints are
        computed from actual heights rather than the constant ROW_HEIGHT.

    Returns
    -------
    int : insertion index (0 = before first, row_count = after last).
    """
    for i, top in enumerate(row_tops):
        h = row_heights[i] if row_heights and i < len(row_heights) else ROW_HEIGHT
        mid = top + h / 2.0
        if pointer_y < mid:
            return i
    return row_count


# ---------------------------------------------------------------------------
# Helper: compute target depth from cursor X (for unparent gesture)
# ---------------------------------------------------------------------------

def infer_target_depth(pointer_x: float) -> int:
    """Infer the desired nesting depth from the cursor's X position."""
    depth = int(pointer_x / INDENT_WIDTH)
    return max(0, min(depth, MAX_INDENT_DEPTH))
