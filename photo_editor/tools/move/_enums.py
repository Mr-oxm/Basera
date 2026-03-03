"""Internal enumerations and constants for the Move tool.

Exported symbols
----------------
_Mode       Drag interaction mode (NONE, MOVE, RESIZE, ROTATE).
_Handle     Which of the 8 bounding-box handles (or NONE) is active.
_ANCHOR_SIGN
            Maps each resize handle to the *(±1, ±1)* sign of the
            opposite (anchor) corner in the box-local frame.  Used to
            keep the anchor fixed while the dragged side moves.
"""

from __future__ import annotations

from enum import Enum, auto


class _Mode(Enum):
    NONE = auto()
    MOVE = auto()
    RESIZE = auto()
    ROTATE = auto()


class _Handle(Enum):
    NONE = auto()
    TL = auto()
    T = auto()
    TR = auto()
    L = auto()
    R = auto()
    BL = auto()
    B = auto()
    BR = auto()


# For each resize handle the *anchor* is the opposite corner/edge.
# The sign pair maps to ``(±half_w, ±half_h)`` in the box-local frame.
_ANCHOR_SIGN: dict[_Handle, tuple[int, int]] = {
    _Handle.TL: (1, 1),
    _Handle.T:  (0, 1),
    _Handle.TR: (-1, 1),
    _Handle.L:  (1, 0),
    _Handle.R:  (-1, 0),
    _Handle.BL: (1, -1),
    _Handle.B:  (0, -1),
    _Handle.BR: (-1, -1),
}
