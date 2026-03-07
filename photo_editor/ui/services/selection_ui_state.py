"""Shared helpers for selection overlay state on the canvas."""

from __future__ import annotations


def apply_selection_overlay(canvas, mask) -> None:
    """Show the selection mask only when it contains visible pixels."""
    if mask is not None and mask.max() > 0:
        canvas.set_selection_mask(mask)
        return
    canvas.set_selection_mask(None)