"""Runs adjustment and filter dialogs and applies results to the document.

Supports real-time preview: while the dialog is open, every parameter
change temporarily applies the filter/adjustment to the active layer so
the user sees the effect on the full canvas before committing.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
from PySide6.QtWidgets import QWidget

from ..core.document import Document
from ..processors import ImageProcessor
from ..registries import (
    get_adjustment_class,
    get_adjustment_map,
    get_filter_class,
    get_filter_map,
    get_filter_name_map,
)
from .dialogs.filter_dialog import FilterDialog


# ---- Adjustment class registry ---------------------------------------------

def _adj_map() -> dict[str, type]:
    return get_adjustment_map()


# ---- Filter class registry ------------------------------------------------

def _filter_map() -> dict[str, type]:
    return get_filter_map()


def _filter_name_map() -> dict[str, type]:
    """Return a mapping from *display name* → filter class.

    Unlike ``_filter_map`` (which uses internal underscore keys), this
    dict is keyed by each filter's ``.name`` attribute so that snapshot
    restore and the layers panel can look up classes by display name.
    """
    return get_filter_name_map()


# ---- Public API -----------------------------------------------------------

def run_adjustment(
    name: str,
    doc: Document,
    parent: QWidget | None = None,
    preview_fn: Callable[[], None] | None = None,
) -> bool:
    """Show a dialog for *name*, apply to active layer. Returns True if applied.

    If *preview_fn* is provided it is called after every parameter change so
    the canvas updates in real time.
    """
    adj_cls = get_adjustment_class(name)
    if adj_cls is None:
        return False
    adj = adj_cls()

    # Invert has no params — apply immediately
    if not adj.default_params:
        return _apply_to_layer(doc, adj, {})

    return _run_dialog_with_preview(
        title=f"Adjustment — {name}",
        processor=adj,
        doc=doc,
        parent=parent,
        preview_fn=preview_fn,
    )


def run_filter(
    key: str,
    doc: Document,
    parent: QWidget | None = None,
    preview_fn: Callable[[], None] | None = None,
) -> bool:
    """Show a dialog for filter *key*, apply to active layer."""
    filt_cls = get_filter_class(key)
    if filt_cls is None:
        return False
    filt = filt_cls()

    if not filt.default_params:
        return _apply_to_layer(doc, filt, {})

    return _run_dialog_with_preview(
        title=f"Filter — {filt.name}",
        processor=filt,
        doc=doc,
        parent=parent,
        preview_fn=preview_fn,
    )


# ---- Internal helpers -----------------------------------------------------

def _run_dialog_with_preview(
    title: str,
    processor: ImageProcessor,
    doc: Document,
    parent: QWidget | None,
    preview_fn: Callable[[], None] | None,
) -> bool:
    """Show *FilterDialog*, live-preview on the canvas, commit or rollback."""
    layer = doc.layers.active_layer
    if layer is None or layer.locked:
        return False

    # Keep a copy of the original pixels so we can restore on cancel
    # or re-apply cleanly on each param change.
    original_pixels = layer.pixels.copy()

    dlg = FilterDialog(title, processor.default_params, parent=parent)

    # ---- live-preview callback -------------------------------------------
    def _on_params_changed(params: dict) -> None:
        """Apply the filter with current params and refresh the canvas."""
        try:
            layer.pixels = processor.apply(original_pixels.copy(), params)
        except Exception:
            # If the filter fails with some param combo, silently keep
            # the last good state so the UI doesn't freeze.
            return
        if preview_fn is not None:
            preview_fn()

    dlg.params_changed.connect(_on_params_changed)

    # Show an initial preview with default params so the user immediately
    # sees the effect.
    _on_params_changed(processor.default_params)

    accepted = dlg.exec()

    if accepted:
        # Apply with the final params (might already be set by preview,
        # but re-apply to be safe with the exact dialog values).
        final_params = dlg.get_params()
        layer.pixels = processor.apply(original_pixels.copy(), final_params)
        doc.save_snapshot(processor.name)
        return True
    else:
        # Cancelled — restore original pixels
        layer.pixels = original_pixels
        if preview_fn is not None:
            preview_fn()
        return False


def _apply_to_layer(doc: Document, processor: ImageProcessor, params: dict) -> bool:
    """Immediate apply (no dialog, no preview)."""
    layer = doc.layers.active_layer
    if layer is None or layer.locked:
        return False
    doc.save_snapshot(processor.name)
    layer.pixels = processor.apply(layer.pixels, params)
    return True
