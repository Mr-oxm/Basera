"""Shared helpers for guide state across canvas and rulers."""

from __future__ import annotations


def apply_guides(canvas, h_ruler, v_ruler, guides) -> None:
    """Sync the current guide set to the canvas and both rulers."""
    canvas.set_guides(guides)
    h_ruler.set_guides(guides)
    v_ruler.set_guides(guides)


def apply_preview_guide(canvas, h_ruler, v_ruler, guides, preview_guide) -> None:
    """Show a preview guide while keeping ruler state in sync."""
    canvas.set_preview_guide(preview_guide)
    apply_guides(canvas, h_ruler, v_ruler, guides)