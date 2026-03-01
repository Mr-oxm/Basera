"""Backward-compatibility shim for ``photo_editor.tools.move_tool``.

The Move tool has been refactored into the :mod:`photo_editor.tools.move`
sub-package.  This module re-exports ``MoveTool`` from that package so
existing import paths continue to work without modification::

    from photo_editor.tools.move_tool import MoveTool  # still valid

For new code, prefer importing directly from the sub-package::

    from photo_editor.tools.move import MoveTool
"""

from .move import MoveTool  # noqa: F401

__all__ = ["MoveTool"]
