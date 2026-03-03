"""``photo_editor.tools.move`` — Move tool sub-package.

This package breaks the original monolithic ``move_tool.py`` (1 200 +
lines) into focused, reusable modules.

Sub-module overview
-------------------
``_enums``
    Internal enumerations: ``_Mode`` (NONE/MOVE/RESIZE/ROTATE),
    ``_Handle`` (TL/T/TR/L/R/BL/B/BR/NONE), and the ``_ANCHOR_SIGN``
    mapping used to keep the opposite corner fixed during a resize.

``hit_test``
    Pure functions for bounding-box and handle hit-testing in document
    coordinates.  Exports ``HANDLE_MARGIN``, ``ROTATE_HANDLE_OFFSET``,
    ``bbox``, ``group_bbox``, ``hit_test``, and ``hit_test_rect``.
    These helpers have no side-effects and can be imported by any other
    module that needs to know what the user clicked.

``auto_select``
    Tool-agnostic layer-picking helpers: ``point_on_layer`` and
    ``find_layer_at``.  **Shared with** :mod:`photo_editor.vector.node_tool`
    so both tools honour the same alpha-threshold logic and TEXT
    bounding-box test.  Import directly::

        from photo_editor.tools.move.auto_select import find_layer_at

``float_selection``
    ``FloatSelectionMixin`` — cuts the selected pixels into a floating
    buffer on drag-start and alpha-composites them back on commit.

``resize_ops``
    ``ResizeMixin`` — non-destructive single-layer resize
    (``_apply_resize``, ``_setup_resize_anchor``) and group resize
    (``_apply_group_resize``).

``rotate_ops``
    ``RotateMixin`` — non-destructive single-layer rotate
    (``_apply_rotate``), group rotate (``_apply_group_rotate``), and
    mask-child synchronisation (``_sync_mask_transforms``).

``vector_commit``
    ``VectorCommitMixin`` — bakes the non-destructive layer transform
    back into vector objects at drag-end so the layer is left clean
    (``_commit_vector_transform``, ``_commit_group_vector_transforms``,
    ``_bake_transform_into_descendants``).

``align_ops``
    Standalone functions for aligning a layer to the canvas
    (``align_left/center_h/right/top/middle_v/bottom``) and for
    flipping / fixed-angle rotation
    (``flip_horizontal/vertical``, ``rotate_90_cw/ccw``).
    These can be called from menu actions without an active tool.

``move_tool``
    ``MoveTool`` — the final class that assembles all of the above
    mixins and is registered with the tool manager.

Public re-exports
-----------------
Only ``MoveTool`` is exported at the package level; everything else
should be imported from its own sub-module.
"""

from .move_tool import MoveTool

__all__ = ["MoveTool"]
