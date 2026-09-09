# Photo Editor — Architecture

This document describes the full architecture of the application: package responsibilities, class relationships, data flow, design patterns, and dependency rules.

---

## Tech Stack

| Library | Role |
|---------|------|
| **PySide6** | UI framework (Qt6 bindings) |
| **NumPy** | All image data as `(H, W, 4) float32` RGBA buffers |
| **OpenCV (cv2)** | Geometric transforms, morphological ops, blur kernels |
| **Pillow** | Text rendering, image I/O encode/decode |
| **arabic_reshaper / python-bidi** | RTL text shaping |
| **scikit-image** | Advanced image processing ops |

---

## Package Map

```
photo_editor/
├── __main__.py            Entry point
├── app.py                 QApplication bootstrap
│
├── core/                  Domain model (no UI, no rendering deps)
│   ├── document.py        Project container
│   ├── layer.py           Atomic compositing unit
│   ├── layer_stack.py     Ordered layer tree
│   ├── selection.py       Pixel-level selection mask
│   ├── history.py         Undo/redo stack
│   ├── canvas.py          Viewport state (zoom, pan, guides)
│   ├── enums.py           BlendMode, LayerType, ToolType constants
│   ├── color.py           Immutable RGBA + fill types
│   ├── color_engine.py    Internal color math used by adjustments
│   ├── text_layer.py      Rich-text data model
│   ├── brush_engine.py    ABR brush file parser
│   ├── image/             Tile processing contracts (tile_processor.py)
│   └── services/          Extracted document-level operations (document_resize.py)
│
├── engine/                Render & compositing pipeline
│   ├── compositor.py      Node-based layer compositing
│   ├── render_engine.py   Full-document render pass
│   ├── render_pipeline.py Orchestrator (uint8 cache + scheduling)
│   ├── tile_cache.py      Incremental 256px tile dirty tracking
│   ├── cache/             ImagePool (float32 buffer reuse)
│   └── renderer/          RenderScheduler + RenderWorker (async, ~30 fps)
│
├── commands/              Mutations with undo semantics
│   ├── base.py            Command ABC
│   ├── layer/             Add, Remove, Duplicate, Flatten, MergeDown, Reorder,
│   │                      Rename, AddGroup, MoveLayer, ClipLayer, DropAsMask,
│   │                      ResizeLayer, RotateLayer
│   ├── mask/              Add, Remove, Apply, Convert, Invert, Attach
│   ├── effect/            AttachAdjustment, UpdateEffect
│   └── document/          Save, PlaceImage
│
├── ui/                    PySide6 user interface
│   ├── main_window.py     Top-level window + controller wiring
│   ├── app_signals.py     Cross-controller signal hub
│   ├── document_session.py Open-doc & tab state
│   ├── file_tab_bar.py    Document tab bar widget
│   ├── filter_runner.py   Adjustment/filter dialog runner
│   ├── menus.py           Menu bar construction
│   ├── toolbar.py         Left-side tool toolbar
│   ├── tool_manager.py    Tool instance registry & switching
│   ├── shortcut_manager.py Keyboard shortcut binding table
│   ├── status_bar.py      Bottom status bar
│   ├── styles.py          Qt stylesheet helpers
│   ├── theme.py           ThemeManager singleton (dark/light palettes)
│   ├── welcome_screen.py  Startup splash / recent-projects screen
│   ├── controllers/       Domain controllers (ControllerBase)
│   ├── panels/            Dockable panels
│   │   ├── layers_panel.py        Legacy shim / entry point
│   │   ├── properties_panel.py    Legacy shim / entry point
│   │   ├── adjustments_panel.py   Adjustment presets panel
│   │   ├── brushes_panel.py       Brush preset browser
│   │   ├── channels_panel.py      RGBA channel visibility
│   │   ├── color_panel.py         Color picker panel
│   │   ├── history_panel.py       Undo history panel
│   │   ├── transform_panel.py     Numeric transform inputs
│   │   ├── layers/                Refactored layers panel sub-package
│   │   │   ├── panel.py           LayersPanel widget
│   │   │   ├── layer_list.py      QListView subclass
│   │   │   ├── layer_item.py      Per-row data model
│   │   │   ├── layer_delegate.py  Custom item painter
│   │   │   ├── blend_combo.py     Blend mode combo box
│   │   │   ├── drag_manager.py    Drag-reorder logic
│   │   │   ├── drag_overlay.py    Drop-indicator overlay
│   │   │   ├── thumbnails.py      Async thumbnail generation
│   │   │   ├── icons.py           Layer-type icon helpers
│   │   │   └── base.py            PanelBase mixin
│   │   └── properties/            Tool options bar sub-package
│   │       ├── panel.py           PropertiesPanel (stacked widget)
│   │       ├── brush_bar.py       Brush tool options
│   │       ├── crop_bar.py        Crop tool options
│   │       ├── gradient_bar.py    Gradient tool options
│   │       ├── move_bar.py        Move tool options
│   │       ├── selection_bar.py   Selection tool options
│   │       ├── text_bar.py        Text tool options
│   │       ├── vector_bar.py      Vector/pen tool options
│   │       ├── zoom_bar.py        Zoom/view options
│   │       └── base.py            BarBase mixin
│   ├── dialogs/           Modal windows
│   │   ├── filter_dialog.py       Generic filter parameter dialog
│   │   ├── new_document.py        New document wizard
│   │   ├── new_project_dialog.py  New project dialog
│   │   ├── export_dialog.py       Export (flatten + format options)
│   │   ├── layer_styles_dialog.py Layer styles editor
│   │   ├── param_dialog.py        Generic parameter input dialog
│   │   ├── shortcuts_dialog.py    Keyboard shortcuts editor
│   │   ├── text_dialog.py         Rich-text editor dialog
│   │   └── adjustments/           Per-adjustment parameter dialogs
│   │       ├── brightness_contrast_dialog.py
│   │       ├── color_balance_dialog.py
│   │       ├── curves_dialog.py
│   │       ├── hue_saturation_dialog.py
│   │       ├── levels_dialog.py
│   │       ├── normals_dialog.py
│   │       ├── recolor_dialog.py
│   │       ├── split_toning_dialog.py
│   │       ├── vibrance_dialog.py
│   │       ├── white_balance_dialog.py
│   │       └── adjustment_preview_timing.py  Debounce helper
│   ├── canvas/            Canvas overlays & input handling
│   │   ├── canvas_input.py        Mouse/tablet event routing
│   │   ├── canvas_overlays.py     Selection, transform & guide overlays
│   │   └── canvas_cursors.py      Tool-aware cursor factory
│   ├── widgets/           Reusable UI components
│   │   ├── color_wheel.py
│   │   ├── color_sliders.py
│   │   ├── color_dropdown.py
│   │   ├── gradient_editor.py
│   │   ├── gradient_slider_row.py
│   │   ├── rulers.py
│   │   └── swatch_grid.py
│   ├── icons/             Icon factories (programmatic + asset-based)
│   │   ├── assets.py      General app asset icons
│   │   ├── layers.py      Layer-type icons
│   │   ├── properties.py  Properties panel icons
│   │   └── tool_icons.py  Toolbar tool icons
│   ├── css/               Qt stylesheet fragments
│   └── services/          Shared UI-state helpers
│       ├── layer_panel_state.py
│       ├── selection_ui_state.py
│       ├── guide_ui_state.py
│       ├── vector_ui_state.py
│       └── rasterize_guard.py
│
├── processors/            Shared processor interface
│   └── image_processor.py ImageProcessor ABC
│
├── registries/            Lazy processor lookup (no UI coupling)
│   ├── adjustment_registry.py
│   └── filter_registry.py
│
├── adjustments/           Non-destructive adjustment layer ops (19 total)
├── filters/               Destructive filter layer ops (20+ total)
├── effects/               Runtime effects pipeline
├── styles/                Layer style effects (drop shadow, glow, etc.)
├── blending/              Blend mode functions + BlendingEngine
├── masks/                 Mask management (legacy + mask-layer API)
├── tools/                 Interactive canvas tools
│   ├── move/              Move tool sub-package
│   │   ├── move_tool.py   Multi-layer move with live preview
│   │   ├── align_ops.py   Align / distribute operations
│   │   ├── auto_select.py Click-to-select layer logic
│   │   ├── float_selection.py  Float selection helpers
│   │   ├── hit_test.py    Layer hit-testing
│   │   ├── resize_ops.py  Handle-based resize helpers
│   │   ├── rotate_ops.py  Handle-based rotation helpers
│   │   ├── vector_commit.py    Vector transform commit
│   │   └── _enums.py      Internal move-tool enums
│   └── (tool_base.py, brush.py, eraser.py, clone_stamp.py, healing_brush.py,
│        gradient_tool.py, paint_bucket.py, selection_tools.py, shape_tool.py,
│        text_tool.py, transform_tool.py, crop_tool.py, pan_tool.py,
│        zoom_tool.py, eyedropper.py)
├── transforms/            Geometric transform engine
├── vector/                Vector graphics (paths, shapes, SVG, boolean, PDF)
│   ├── scene.py, path.py, shapes.py, style.py, geometry.py
│   ├── bezier.py          Bezier math helpers
│   ├── boolean.py         Boolean path ops (entry point)
│   ├── boolean_ops.py     Boolean op implementations
│   ├── spatial.py         RTree / spatial index helpers
│   ├── shape_tool.py      Interactive shape drawing tool
│   ├── pick_segments.py   Segment-level selection helpers
│   ├── svg.py, pdf.py     SVG and PDF import/export
│   └── rasterizer.py, pen_tool.py, node_tool.py
├── color/                 Color management (distinct from core/color.py)
└── utils/                 Misc helpers
    ├── color_utils.py     Color math helpers
    ├── image_io.py        Format-detecting imread/imwrite
    ├── math_utils.py      Geometric and numeric utilities
    ├── project_io.py      .basera project serialization (read/write)
    ├── recent_projects.py Recent-files list persistence
    └── worker.py          Worker QThread wrapper for async operations
```

---

## Dependency Rules

```
ui  →  commands  →  core
ui  →  engine    →  { blending, effects, styles, adjustments, filters }
ui  →  registries
core  →  (nothing internal — pure domain model)
engine  →  core
commands  →  core
```

**Never allowed:**

- `core → ui` or `core → engine`
- `engine → ui`
- Any feature package importing a controller or dialog directly
- `registries → ui`

---

## Layer Responsibilities

### `core/`

Pure domain model. No Qt, no numpy rendering. All business rules and data structures that define what a document *is*.

| File / Sub-package | Responsibility |
|--------------------|---------------|
| `document.py` | Project: layers, history, selection, width/height, dirty flag |
| `layer.py` | Single compositing unit: pixels, mask, blend mode, opacity, position, transform params, vector data, adjustment processor |
| `layer_stack.py` | Ordered collection with multi-select, group/reparent, mask-layer attachment, `update_group_bbox()` |
| `selection.py` | Float32 selection mask: rect, ellipse, feather, grow/shrink, invert, `apply_to()` |
| `history.py` | Document snapshots: push (50-state ring), undo, redo |
| `canvas.py` | Viewport state: zoom, pan, rotation, grid pitch, guide list, snap flags |
| `enums.py` | `BlendMode` (32 modes), `LayerType` (RASTER, GROUP, ADJUSTMENT, FILTER, MASK, SHAPE, TEXT, VECTOR), `ToolType` (25 tools) |
| `color.py` | Immutable `Color` RGBA, `SolidFill`, `LinearGradient`, `RadialGradient`, `GradientStop` |
| `color_engine.py` | Internal color math utilities used by adjustments (channel ops, blend helpers) |
| `text_layer.py` | `TextRun`, `CharFormat`, `ParagraphFormat`, Arabic/RTL support |
| `brush_engine.py` | `BrushPreset`, `BrushManager` (singleton), ABR v1/v2/v6+ parser |
| `image/` | Tile processing contracts (`tile_processor.py`) |
| `services/` | Extracted operations shared by controllers and not belonging in core data classes (e.g. `document_resize.py`) |

---

### `engine/`

Rendering and compositing pipeline. Converts a `Document` into a flat `(H, W, 4) float32` RGBA frame displayed on screen.

| File | Responsibility |
|------|---------------|
| `compositor.py` | Walks the visible layer list bottom-to-top. Handles: clipping masks, groups (recursive `_composite_group`), root-level and child-scoped adjustment/filter layers, standalone mask attenuation, style application, blur padding for filter overflow |
| `render_engine.py` | Drives the compositor, owns a dirty-layer cache |
| `render_pipeline.py` | Orchestrates: calls `RenderEngine`, caches the `uint8` result, integrates `TileCache` and `ImagePool` |
| `tile_cache.py` | Tracks 256 px dirty tiles for incremental rendering |
| `cache/image_pool.py` | `ImagePool` — reusable `(H, W, 4) float32` buffer pool, avoids alloc/dealloc churn |
| `renderer/render_scheduler.py` | `RenderScheduler` — off-UI thread at ~30 fps, configurable preview down-scale |
| `renderer/render_worker.py` | `RenderWorker` — QThread that executes a single render pass |

**Compositing order inside `Compositor.composite()`:**

1. Root-level **adjustment/filter** layers are included in the visible pass. When encountered they apply their processor to the entire accumulated canvas (affects all layers below — Photoshop adjustment layer semantics).
2. Child adjustment/filter layers (`parent_id` set) are collected into `adj_children` and applied to their parent layer's pixels before blending.
3. **Group** layers are recursively composited as a sub-canvas via `_composite_group()`, child adj/filter applied to the group image, then the group blended into the main canvas.
4. **Clipping masks** are detected in a pre-scan and applied using the previous layer's alpha.
5. **Standalone mask layers** attenuate the accumulated canvas.

---

### `commands/`

Each command encapsulates one reversible document mutation. The `Command` ABC defines `execute(document)`. Commands are dispatched via `ControllerContext.execute_command()` which pushes them to `HistoryManager`.

| Sub-package | Commands |
|-------------|---------|
| `layer/` | AddLayer, RemoveLayer, DuplicateLayer, FlattenCommand, MergeDownCommand, MoveLayer, ReorderLayers, RenameLayer, AddGroup, ClipLayer, DropAsMask, ResizeLayer, RotateLayer |
| `mask/` | AddMaskLayer, RemoveMaskLayer, ApplyMaskLayer, ConvertToMask, InvertMaskLayer, AttachAdjustmentToLayer, AttachMaskToLayer |
| `effect/` | AttachAdjustmentToLayer, UpdateEffectCommand |
| `document/` | SaveDocument, PlaceImage |

---

### `ui/`

All PySide6 code. Only layer that imports Qt. Calls into `commands/` and `core/` — never the reverse.

**`MainWindow`** is the root widget. It owns:
- One active `Document` (plus others via `DocumentSession`)
- `RenderPipeline` and `RenderScheduler`
- `ToolManager` and `BrushManager`
- `DocumentSession` (multi-document tab state)
- `AppSignals` (cross-controller event hub)
- All controller instances (wired at startup)

**`DocumentSession`** — owns the list of open documents, tab order, and active document switching. Separates multi-document session lifecycle from `MainWindow`.

**`AppSignals`** — PySide6 signals used for explicit cross-controller coordination: selection overlay, transform bounding box, canvas updates, layer-panel processor actions, duplicate-selection dispatch, clone preview, panel refresh requests.

**`ControllerBase` / `ControllerContext`** — all controllers inherit from `ControllerBase`. `ControllerContext` provides a facade over `MainWindow` for document access, render scheduling, command execution, and panel queries. Controllers should not call `MainWindow` internals directly.

| Controller | Responsibility |
|------------|---------------|
| `DocumentController` | New/open/save/export/close/flatten/merge documents |
| `LayerController` | Add/delete/group/mask/reorder/rename/property layers |
| `FilterController` | Adjustment and filter layer creation, editing, and menu filter application |
| `SelectionController` | Selection tools, transform, clipboard |
| `TransformController` | Non-destructive scale/rotate/skew with commit/cancel |
| `CropController` | Crop tool and canvas trim |
| `VectorController` | Vector layer creation, node/pen tool orchestration |
| `GradientController` | Gradient tool application |
| `TextController` | Text layer creation and editing |
| `ColorController` | FG/BG color, swatch, color picker |
| `CanvasController` | Canvas resize, rotate canvas, grid/guide management |
| `ToolController` | Tool switching, brush settings, tool options bar |
| `ViewController` | Zoom, pan, guides toggle, screen mode |
| `ShortcutController` | Dynamic keyboard shortcut binding |
| `DropController` | Drag-and-drop file import |

**`ui/services/`** — Shared UI policies extracted from controllers. Each module handles one focused concern:

| Module | Responsibility |
|--------|---------------|
| `layer_panel_state.py` | Layer panel reorder math, selection sync |
| `selection_ui_state.py` | Selection overlay propagation |
| `guide_ui_state.py` | Guide state propagation to canvas |
| `vector_ui_state.py` | Vector panel/mode state |
| `rasterize_guard.py` | Rasterize active text/vector layer before destructive ops |

**Top-level `ui/` modules** added since initial design:

| Module | Responsibility |
|--------|---------------|
| `file_tab_bar.py` | Document tab bar widget (open-doc tabs) |
| `menus.py` | Menu bar construction and wiring |
| `toolbar.py` | Left-side tool toolbar |
| `tool_manager.py` | Tool instance registry and active-tool switching |
| `shortcut_manager.py` | Keyboard shortcut binding table (singleton) |
| `status_bar.py` | Bottom status bar (cursor coords, zoom level, doc info) |
| `styles.py` | Qt stylesheet helpers and global style application |
| `theme.py` | `ThemeManager` singleton (dark/light palette management) |
| `welcome_screen.py` | Startup splash / recent-projects screen |

**`ui/canvas/`** — Canvas input and overlay sub-package:

| Module | Responsibility |
|--------|---------------|
| `canvas_input.py` | Mouse/tablet event routing to active tool |
| `canvas_overlays.py` | Selection march, transform handles, guide overlays |
| `canvas_cursors.py` | Tool-aware cursor factory |

**`ui/icons/`** — Programmatic icon factories:

| Module | Responsibility |
|--------|---------------|
| `assets.py` | General app asset icons |
| `layers.py` | Layer-type icons (raster, group, text, vector, etc.) |
| `properties.py` | Properties panel icons |
| `tool_icons.py` | Toolbar tool icons |

**`ui/dialogs/adjustments/`** — Per-adjustment parameter dialogs (one per adjustment type): Brightness/Contrast, Color Balance, Curves, Hue/Saturation, Levels, Normals, Recolor, Split Toning, Vibrance, White Balance. Each shares `adjustment_preview_timing.py` for debounced live preview.

**`ui/panels/layers/`** — Refactored layers panel sub-package: `panel.py` (widget), `layer_list.py` (view), `layer_item.py` (model), `layer_delegate.py` (painter), `blend_combo.py`, `drag_manager.py`, `drag_overlay.py`, `thumbnails.py`, `icons.py`, `base.py`.

**`ui/panels/properties/`** — Tool options bar sub-package: `panel.py` (stacked widget), per-tool bars (`brush_bar`, `crop_bar`, `gradient_bar`, `move_bar`, `selection_bar`, `text_bar`, `vector_bar`, `zoom_bar`), `base.py`.

---

### `processors/`

`ImageProcessor` is the shared ABC for all pixel-manipulating operations.

```python
class ImageProcessor(ABC):
    name: str
    default_params: dict

    @abstractmethod
    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        """image: (H,W,4) float32 RGBA → returns (H,W,4) float32 RGBA"""
```

Both `Adjustment` and `Filter` extend `ImageProcessor`. Effects in the pipeline also conform to this contract.

---

### `registries/`

Lazy importlib-based registries. Return processor classes on demand without the UI or engine needing to import all processor modules at startup.

- `get_adjustment_class(name)` / `get_adjustment_map()` → `{str: type[Adjustment]}`
- `get_filter_class(key)` / `get_filter_map()` / `get_filter_name_map()` → `{str: type[Filter]}`

---

### `adjustments/`

19 non-destructive adjustments, each a concrete `Adjustment(ImageProcessor)`:

Brightness/Contrast · Levels · Curves · Exposure · Vibrance · Hue/Saturation · Color Balance · Black & White · Photo Filter · Gradient Map · Selective Color · Channel Mixer · Invert · Posterize · Threshold · Normals · Recolor · Split Toning · White Balance

All implement `apply(image, params) → image` where both input and output are `(H, W, 4) float32` RGBA.

---

### `filters/`

20+ destructive filters, each a concrete `Filter(ImageProcessor)`, organized by category:

| Category | Filters |
|----------|---------|
| `blur/` | Gaussian Blur, Motion Blur, Radial Blur, Lens Blur, Surface Blur |
| `distort/` | Twirl, Pinch, Perspective, Ripple, Wave |
| `noise/` | Add Noise, Dust & Scratches, Median, Reduce Noise |
| `sharpen/` | Sharpen, Smart Sharpen, Unsharp Mask |
| `stylize/` | Emboss, Find Edges, Oil Paint, Solarize |
| `render/` | Clouds, Difference Clouds, Lighting Effects |

Blur filters include premultiplied-alpha helpers (`_premultiply`, `_unpremultiply`) to prevent dark fringing on transparent edges. The compositor adds padding around layers when blur filters are in use so the blur can extend beyond the original layer boundary.

---

### `effects/`

Runtime ordered post-process chain. Distinct from document-owned adjustment/filter layers:

- `Effect` — wraps an `ImageProcessor` with `enabled` flag and `params` dict
- `EffectsPipeline` — ordered list: `add()`, `remove()`, `move()`, `clear()`, `process(image)` applies all enabled effects sequentially

Effects are not part of the layer stack; they are applied as a final pass after compositing.

---

### `styles/`

10 layer style effects composited live with a layer's pixels. Each is a `LayerStyle(ABC)` with `StyleParams` (enabled, opacity, blend mode):

Drop Shadow · Inner Shadow · Outer Glow · Inner Glow · Bevel & Emboss · Color Overlay · Gradient Overlay · Pattern Overlay · Satin · Stroke

Applied by `StyleEngine.apply_styles(pixels, styles)` during compositing.

---

### `blending/`

`BlendingEngine.blend_region_inplace(canvas, src, position, blend_mode, opacity, mask)` — computes the intersection of `src` and `canvas`, blends only the overlapping region in-place, no temporary full-canvas allocation.

32 blend functions registered lazily by mode key. Organized in six files: `normal`, `darken`, `lighten`, `contrast`, `comparative`, `color_blend`.

---

### `masks/`

`MaskManager` provides two APIs:

- **Legacy mask**: per-layer float32 alpha mask stored on `layer._mask`. `add_mask()`, `remove_mask()`, `apply_mask()`, `invert_mask()`, `fill_mask()`, `gradient_mask()`.
- **Mask-layer API**: `LayerType.MASK` layers composited as part of the layer stack. `add_mask_layer()`, `remove_mask_layer()`, `apply_mask_layer()`, `convert_to_mask()`, `selection_to_mask()`.

`MaskManager.get_combined_mask(layer, stack)` merges legacy mask + attached mask layers into a single alpha used by the compositor.

---

### `tools/`

15+ interactive canvas tools, all subclasses of `Tool(ABC)` with `on_press(event, doc, canvas)`, `on_move(…)`, `on_release(…)`:

| Tool | File(s) | Description |
|------|---------|-------------|
| Brush | `brush.py` | Dab-based painting with pressure, size, hardness, opacity |
| Eraser | `eraser.py` | Alpha-erasing dab tool |
| Clone Stamp | `clone_stamp.py` | Sample-then-paint from an offset source |
| Healing Brush | `healing_brush.py` | Content-aware blending at paint site |
| Gradient | `gradient_tool.py` | Linear/radial/conical/diamond gradient fill |
| Paint Bucket | `paint_bucket.py` | Flood fill with tolerance |
| Selection tools | `selection_tools.py` | Rect, Ellipse, Lasso, Magic Wand |
| Move | `move_tool.py` + `move/` | Translate layers (multi-select, align, auto-select, float) |
| Transform | `transform_tool.py` | Non-destructive scale/rotate/skew via handle drag |
| Crop | `crop_tool.py` | Interactive canvas crop with aspect-ratio lock |
| Text | `text_tool.py` | In-canvas rich-text editor |
| Shape | `shape_tool.py` | Parametric shape drawing (rect, circle, polygon, star) |
| Pen / Node | `vector/pen_tool.py`, `vector/node_tool.py` | Bezier path drawing and node editing |
| Pan / Zoom | `pan_tool.py`, `zoom_tool.py` | Viewport navigation |
| Eyedropper | `eyedropper.py` | Sample canvas color → FG/BG |

**`move/` sub-package** — Move tool helpers extracted for clarity:

| Module | Responsibility |
|--------|---------------|
| `align_ops.py` | Align and distribute selected layers |
| `auto_select.py` | Click-to-auto-select topmost layer under cursor |
| `float_selection.py` | Float (detach) active selection to a new layer |
| `hit_test.py` | Per-pixel layer hit testing |
| `resize_ops.py` | Handle-based layer resize during move |
| `rotate_ops.py` | Handle-based layer rotation during move |
| `vector_commit.py` | Commit in-progress vector transform |
| `_enums.py` | Internal move-tool enums (handle type, drag state) |

Shared helpers on `Tool`: `_rasterize_if_needed()` (bakes ND-transforms before destructive edits), `_get_sel_mask()` (selection in layer coords), `_stamp_circle()` (region-optimized circular dab).

---

### `transforms/`

`TransformEngine` — OpenCV-backed:

- `scale(image, sx, sy, fast)` — anti-aliased by default; `INTER_NEAREST` in fast/preview mode
- `rotate(image, angle, expand, fast)` — expands canvas to fit rotated content
- `skew(image, sx, sy)` — affine shear

All ops work in premultiplied-alpha space to keep transparent-edge quality.

Non-destructive transform flow on `Layer`:
1. `init_non_destructive()` — snapshots current pixels as `_source_pixels`
2. `compute_display(scale_x, scale_y, angle)` — re-derives `_pixels` from source
3. `invalidate_transform()` — sets dirty flag for lazy recompute
4. Committing bakes `_pixels` back into `_source_pixels` (clears ND state)

---

### `vector/`

Full vector graphics subsystem:

| Module | Responsibility |
|--------|---------------|
| `scene.py` | `VectorObject` (path/shape + style + transform), `VectorLayer` (flat list + RTree spatial index for hit testing) |
| `path.py` | `VectorPath` — open/closed Bezier curves, segments, fill rule, `offset()`, `transformed()`, `hit_test_fill()` |
| `shapes.py` | `ShapePrimitive` — rectangle, circle, polygon, star with live parameters; `to_path()` converts to `VectorPath` |
| `style.py` | `VectorStyle` — stroke + fill, color, width, dash pattern, line cap/join |
| `geometry.py` | `Vec2`, `BBox`, `AffineTransform`, geometric primitives |
| `bezier.py` | Bezier math helpers (evaluate, split, intersect, offset) |
| `boolean.py` | Boolean path op entry point (union, intersect, subtract, XOR) |
| `boolean_ops.py` | Boolean op implementations |
| `spatial.py` | RTree spatial index helpers for fast hit-testing |
| `shape_tool.py` | Interactive parametric shape drawing tool |
| `pick_segments.py` | Segment-level selection helpers for node tool |
| `svg.py` | SVG import and export |
| `pdf.py` | PDF vector import |
| `rasterizer.py` | Vector → raster conversion for compositing |
| `pen_tool.py` | Interactive Bezier path drawing |
| `node_tool.py` | Node editing (select, move, add, delete control points) |

Vector layers are rasterized on demand during the render pass.

---

### `color/`

Color management separate from `core/color.py`. Provides a richer API used by the UI and tools:

| Module | Responsibility |
|--------|---------------|
| `conversions.py` | `HSV/HSL/CMYK/Lab/OklabColor`, bidirectional conversions, `perceptual_lerp()`, `contrast_ratio()`, `kelvin_to_color()` |
| `harmonies.py` | `HarmonyType` enum + `generate_harmony(color, type)` (complementary, triadic, etc.) |
| `gradients.py` | `ConicalGradient`, `DiamondGradient`, `GRADIENT_PRESETS` |
| `swatches.py` | `SwatchPalette` — persistent swatch collection with JSON I/O |
| `manager.py` | `ColorManager` singleton — current FG/BG color, active gradient, swatch set |

---

### `utils/`

| Module | Responsibility |
|--------|---------------|
| `color_utils.py` | Color math helpers (blend, clamp, etc.) |
| `image_io.py` | Format-detecting imread/imwrite |
| `math_utils.py` | Geometric and numeric utilities |
| `project_io.py` | `.basera` project serialization — read/write full document to disk |
| `recent_projects.py` | Recent-files list persistence (JSON) |
| `worker.py` | `Worker` QThread wrapper for async operations |

---

## Data Flow

### Render Path

```
Tool / Command modifies Layer.pixels or Layer.adjustment_params
  ↓
ControllerContext.invalidate(layer_id) marks layer dirty in RenderEngine
ControllerContext.schedule_render() posts to RenderScheduler
  ↓
RenderScheduler (off-UI thread, ~30 fps)
  → RenderPipeline.execute()
    → Compositor.composite(stack, w, h)
        walks layers bottom-to-top
        applies blend modes, masks, styles, adj/filter layers
    → uint8 cache updated
  ↓
Main thread: CanvasView.update() → QPainter draws cached QImage
```

### Command Path

```
User action in controller
  ↓
Controller instantiates Command(args)
  ↓
ControllerContext.execute_command(cmd)
  → cmd.execute(document)        ← mutates document
  → HistoryManager.push(snapshot)
  ↓
ctx.refresh() → panel update + render schedule
```

### Non-Destructive Adjustment Preview

```
FilterDialog.params_changed signal fires
  ↓
layer.adjustment_params = new_params        ← no pixel mutation
  ↓
ctx.schedule_render()
  ↓
Compositor picks up new params during next render pass
  → applies processor to layer pixels / accumulated canvas
  → update shown on canvas without committing
  ↓
On accept: UpdateEffectCommand commits final params to HistoryManager
On reject: old_params restored, render scheduled
```

---

## Key Design Patterns

| Pattern | Where used |
|---------|-----------|
| **MVC** | `core/` = model, `ui/panels` + `ui/canvas` = view, `ui/controllers` = controller |
| **Command** | `commands/` + `HistoryManager` — every mutation is reversible |
| **Registry** | `registries/` for processors, `blending/` for blend mode functions — lazy importlib loading |
| **Observer** | `AppSignals` PySide6 signals — cross-controller events without direct coupling |
| **Strategy** | `ImageProcessor` / `Tool` / `LayerStyle` / blend-mode functions — swappable algorithms |
| **Composite** | `LayerStack` tree of layers and groups; `VectorLayer` flat list with spatial index |
| **Pipeline** | `RenderPipeline` → `RenderEngine` → `BlendingEngine`; `EffectsPipeline` |
| **Facade** | `ControllerContext` over `MainWindow` internals; `MaskManager` over mask operations |
| **Singleton** | `BrushManager`, `ColorManager`, `ShortcutManager`, `ThemeManager` |
| **Buffer Pool** | `ImagePool` — reuses `(H, W, 4) float32` allocations across frames |
| **Non-destructive transform** | `Layer._source_pixels` + `compute_display()` — original preserved until explicit commit |
