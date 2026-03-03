"""Command system — decouples UI from engine.

UI emits commands; engine executes them. Commands integrate with document
history for undo/redo.

Structure:
  commands/
    base.py           # Command ABC
    layer/            # add, remove, duplicate, reorder, merge
    mask/             # add, remove, apply, invert, convert, attach
    effect/           # update params, attach adjustment
    document/         # save, place image
"""

from .base import Command

# Re-export from subpackages
from .layer import (
    AddGroupCommand,
    AddLayerCommand,
    DuplicateLayerCommand,
    FlattenCommand,
    MergeDownCommand,
    MoveLayerCommand,
    RemoveLayerCommand,
    RenameLayerCommand,
    ReorderLayersCommand,
    ResizeLayerCommand,
    RotateLayerCommand,
)
from .mask import (
    AddMaskLayerCommand,
    ApplyMaskLayerCommand,
    AttachMaskToLayerCommand,
    ConvertToMaskCommand,
    InvertMaskLayerCommand,
    RemoveMaskLayerCommand,
)
from .effect import (
    AttachAdjustmentToLayerCommand,
    UpdateEffectCommand,
)
from .document import (
    PlaceImageCommand,
    SaveDocumentCommand,
)

__all__ = [
    "Command",
    # Layer
    "AddGroupCommand",
    "AddLayerCommand",
    "DuplicateLayerCommand",
    "FlattenCommand",
    "MergeDownCommand",
    "MoveLayerCommand",
    "RemoveLayerCommand",
    "RenameLayerCommand",
    "ReorderLayersCommand",
    "ResizeLayerCommand",
    "RotateLayerCommand",
    # Mask
    "AddMaskLayerCommand",
    "ApplyMaskLayerCommand",
    "AttachMaskToLayerCommand",
    "ConvertToMaskCommand",
    "InvertMaskLayerCommand",
    "RemoveMaskLayerCommand",
    # Effect
    "AttachAdjustmentToLayerCommand",
    "UpdateEffectCommand",
    # Document
    "PlaceImageCommand",
    "SaveDocumentCommand",
]
