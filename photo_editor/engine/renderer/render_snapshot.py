"""Immutable document snapshot for thread-safe background rendering.

The UI thread creates a snapshot before submitting a render job.
The worker thread reads from the snapshot, never from the live document.
This eliminates the race condition where the UI mutates layers while the
compositor is iterating them.

Pixel arrays are shared by reference (not copied) for performance.
Safety relies on copy-on-write discipline: any mutation to a layer's
pixels must create a new array rather than modifying the existing one
in-place.  Brush/eraser tools already do this naturally (they write
into a fresh region of the array and then assign it back).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ...core.enums import BlendMode, LayerType


@dataclass(frozen=True, slots=True)
class LayerSnapshot:
    """Immutable view of a single layer's compositing-relevant state."""

    id: str
    name: str
    width: int
    height: int
    layer_type: LayerType
    opacity: float
    blend_mode: BlendMode
    visible: bool
    position: tuple[int, int]
    clipping_mask: bool
    clips_parent: bool
    parent_id: str | None
    mask_enabled: bool
    mask_layers: tuple[str, ...]
    children: tuple[str, ...]
    ex_parent_id: str | None
    channel_r: bool
    channel_g: bool
    channel_b: bool
    channel_a: bool
    has_alpha: bool

    # Pixel data — shared reference, NOT a copy
    pixels: np.ndarray
    mask: np.ndarray | None

    # Styles and adjustments
    styles: list
    adjustment: Any  # ImageProcessor | None
    adjustment_params: dict

    def get_mask_grayscale(self) -> np.ndarray:
        """Luminance of the RGB channels (for MASK layers)."""
        return (
            self.pixels[..., 0] * 0.299
            + self.pixels[..., 1] * 0.587
            + self.pixels[..., 2] * 0.114
        ).astype(np.float32)


@dataclass(frozen=True, slots=True)
class RenderSnapshot:
    """Immutable snapshot of the full document state needed for rendering."""

    width: int
    height: int
    generation: int
    layers: tuple[LayerSnapshot, ...]
    layer_map: dict[str, LayerSnapshot]


def create_render_snapshot(document: Any, generation: int = 0) -> RenderSnapshot:
    """Build an immutable RenderSnapshot from the live Document.

    Called on the UI thread before submitting a render job. The snapshot
    captures references to pixel arrays (zero-copy) and freezes all
    metadata so the worker thread can safely iterate without locks.
    """
    from ...core.layer import Layer
    from ...core.layer_stack import LayerStack

    snaps: list[LayerSnapshot] = []
    snap_map: dict[str, LayerSnapshot] = {}

    stack: LayerStack = document.layers
    for layer in stack:
        snap = LayerSnapshot(
            id=layer.id,
            name=layer.name,
            width=layer.width,
            height=layer.height,
            layer_type=layer.layer_type,
            opacity=layer.opacity,
            blend_mode=layer.blend_mode,
            visible=layer.visible,
            position=layer.position,
            clipping_mask=layer.clipping_mask,
            clips_parent=layer.clips_parent,
            parent_id=layer.parent_id,
            mask_enabled=layer.mask_enabled,
            mask_layers=tuple(layer.mask_layers),
            children=tuple(layer.children),
            ex_parent_id=layer.ex_parent_id,
            channel_r=layer.channel_r,
            channel_g=layer.channel_g,
            channel_b=layer.channel_b,
            channel_a=layer.channel_a,
            has_alpha=layer.has_alpha,
            pixels=layer.pixels,
            mask=layer.mask,
            styles=list(layer.styles),
            adjustment=layer.adjustment,
            adjustment_params=dict(layer.adjustment_params),
        )
        snaps.append(snap)
        snap_map[snap.id] = snap

    return RenderSnapshot(
        width=document.width,
        height=document.height,
        generation=generation,
        layers=tuple(snaps),
        layer_map=snap_map,
    )
