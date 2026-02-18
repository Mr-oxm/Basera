"""Controllers — domain-specific handlers split from the main window.

Each controller owns a slice of UI logic and wires menu/panel signals to
its handlers. Controllers hold a reference to the main window (self._mw)
and call its methods (e.g. _refresh, _update_rulers) for shared behavior.

Controllers
-----------
DocumentController
    Document lifecycle: new, open, save, save-as, place image. File tabs
    (switch/close). Import/export SVG and PDF. Undo/redo and history jump.

LayerController
    Layer operations: add, duplicate, delete, group. Mask add/remove/apply/
    invert. Opacity, blend mode, visibility, lock, rename. Drag-drop reorder
    and reparent. Flatten, merge down. Resize canvas/image. Layer styles dialog.

SelectionController
    Selection modify: select all, deselect, invert, feather, grow, shrink.
    Clipboard: cut, copy, paste, duplicate selection. Fill and delete.
    Selection-to-mask. Props panel selection bar (mode, feather, tolerance).

ViewController
    View state: zoom (menu, tool, props bar), pan. Toggle grid, rulers,
    guides. Ruler/guide creation, move, delete. Syncs rulers with canvas.

FilterController
    Adjustment/filter layer add and edit. Menu filter_* (Blur, Sharpen, etc.).
    Uses FilterDialog for parameter editing. Live preview render for filter/
    adjustment dialogs.

TransformController
    Flip horizontal/vertical, rotate 90° CW/CCW. Alignment/distribution
    from Move tool bar.

CropController
    Crop tool: canvas crop, layer crop. Props bar (mode, apply, cancel).
    Rasterize prompt for non-raster layers.

VectorController
    Vector props bar: fill/stroke color, width, shape params. Node actions
    (delete, break path, handle mode). Propagates style to selected objects.

GradientController
    Gradient tool setup and props: type, opacity, reverse, gradient_fill.
    Handles overlay callback.

TextController
    Text tool: setup, overlay, key handler. Auto-enter editing on text layer.
    Exit editing, hover cursor for handles.

ColorController
    Foreground color from Color panel. Forwards to tools and brush preview.

ToolController
    Tool selection, properties panel, eyedropper, pan widget, brush cursor,
    clone/heal preview.

CanvasController
    Canvas mouse input: press, move, release, hover, double-click. Selection
    move-by-drag, tool delegation, clone source, rasterize check.

ShortcutController
    QShortcuts for tools, swap/reset colors, brush size, fullscreen. Text
    editing shortcut toggling.

DropController
    Drag and drop: place image from file manager.
"""

from .canvas_ctrl import CanvasController
from .color_ctrl import ColorController
from .drop_ctrl import DropController
from .crop_ctrl import CropController
from .document_ctrl import DocumentController
from .filter_ctrl import FilterController
from .gradient_ctrl import GradientController
from .layer_ctrl import LayerController
from .selection_ctrl import SelectionController
from .shortcut_ctrl import ShortcutController
from .text_ctrl import TextController
from .tool_ctrl import ToolController
from .transform_ctrl import TransformController
from .vector_ctrl import VectorController
from .view_ctrl import ViewController

__all__ = [
    "CanvasController",
    "ColorController",
    "DropController",
    "CropController",
    "DocumentController",
    "FilterController",
    "GradientController",
    "LayerController",
    "SelectionController",
    "ShortcutController",
    "TextController",
    "ToolController",
    "TransformController",
    "VectorController",
    "ViewController",
]
