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
│   ├── text_layer.py      Rich-text data model
│   ├── brush_engine.py    ABR brush file parser
│   ├── color/             Color science (conversions, harmonies, gradients)
│   ├── image/             Tile processing contracts
│   └── services/          Extracted document-level operations
│
├── engine/                Render & compositing pipeline
│   ├── compositor.py      Node-based layer compositing
│   ├── render_engine.py   Full-document render pass
│   ├── render_pipeline.py Orchestrator (uint8 cache + scheduling)
│   ├── tile_cache.py      Incremental 256px tile dirty tracking
│   ├── cache/             ImagePool (float32 buffer reuse)
│   └── renderer/          RenderScheduler (async, ~30 fps)
│
├── commands/              Mutations with undo semantics
│   ├── base.py            Command ABC
│   ├── layer/             Add, Remove, Duplicate, Flatten, Reorder, Rename
│   ├── mask/              Add, Remove, Apply, Convert, Invert, Attach
│   ├── effect/            AttachAdjustment, UpdateEffect
│   └── document/          Save, PlaceImage
│
├── ui/                    PySide6 user interface
│   ├── main_window.py     Top-level window + controller wiring
│   ├── app_signals.py     Cross-controller signal hub
│   ├── document_session.py Open-doc & tab state
│   ├── filter_runner.py   Adjustment/filter dialog runner
│   ├── controllers/       Domain controllers (ControllerBase)
│   ├── panels/            Dockable panels
│   ├── dialogs/           Modal windows
│   ├── widgets/           Reusable UI components
│   ├── canvas/            Canvas overlays & components
│   └── services/          Shared UI-state helpers
│
├── processors/            Shared processor interface
│   └── image_processor.py ImageProcessor ABC
│
├── registries/            Lazy processor lookup (no UI coupling)
│   ├── adjustment_registry.py
│   └── filter_registry.py
│
├── adjustments/           Non-destructive adjustment layer ops
├── filters/               Destructive filter layer ops
├── effects/               Runtime effects pipeline
├── styles/                Layer style effects (drop shadow, glow, etc.)
├── blending/              Blend mode functions + BlendingEngine
├── masks/                 Mask management (legacy + mask-layer API)
├── tools/                 Interactive canvas tools
├── transforms/            Geometric transform engine
├── vector/                Vector graphics (paths, shapes, SVG, boolean)
├── color/                 Color management (distinct from core/color.py)
└── utils/                 Misc helpers (IO, math, worker thread)
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
| `text_layer.py` | `TextRun`, `CharFormat`, `ParagraphFormat`, Arabic/RTL support |
| `brush_engine.py` | `BrushPreset`, `BrushManager` (singleton), ABR v1/v2/v6+ parser |
| `color/` | `ColorManager` (FG/BG singleton), color-space conversions (HSV/HSL/CMYK/Lab/Oklab), harmonies, gradients, swatch palette |
| `image/` | Tile processing contracts |
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
| `renderer/scheduler.py` | `RenderScheduler` — off-UI thread at ~30 fps, configurable preview down-scale |

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
| `layer/` | AddLayer, RemoveLayer, DuplicateLayer, FlattenCommand, MergeDownCommand, MoveLayer, ReorderLayers, RenameLayer, AddGroup |
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

15 non-destructive adjustments, each a concrete `Adjustment(ImageProcessor)`:

Brightness/Contrast · Levels · Curves · Exposure · Vibrance · Hue/Saturation · Color Balance · Black & White · Photo Filter · Gradient Map · Selective Color · Channel Mixer · Invert · Posterize · Threshold

All implement `apply(image, params) → image` where both input and output are `(H, W, 4) float32` RGBA.

---

### `filters/`

20+ destructive filters, each a concrete `Filter(ImageProcessor)`, organized by category:

| Category | Filters |
|----------|---------|
| `blur/` | Gaussian Blur, Motion Blur, Radial Blur, Lens Blur, Surface Blur |
| `distort/` | Warp, Twist, Bulge, Pinch, Perspective |
| `noise/` | Gaussian, Poisson, Salt-and-Pepper |
| `sharpen/` | Unsharp Mask, High Pass |
| `stylize/` | Pixelate, Oil Paint, Cartoon, Emboss |
| `render/` | Clouds, Plasma, Noise |

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

| Tool | Description |
|------|-------------|
| Brush / Eraser | Dab-based painting with pressure, size, hardness, opacity |
| Clone Stamp | Sample-then-paint from an offset source |
| Healing Brush | Content-aware blending at paint site |
| Gradient | Linear/radial/conical/diamond gradient fill |
| Paint Bucket | Flood fill with tolerance |
| Selection tools | Rect, Ellipse, Lasso, Magic Wand |
| Move | Translate layers (multi-select aware) |
| Transform | Non-destructive scale/rotate/skew via handle drag |
| Crop | Interactive canvas crop with aspect-ratio lock |
| Text | In-canvas rich-text editor |
| Shape / Pen / Node | Vector drawing and path editing |
| Pan / Zoom | Viewport navigation |
| Eyedropper | Sample canvas color → FG/BG |

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
| `boolean.py` | Union, intersection, subtract, XOR path operations |
| `svg.py` | SVG import and export |
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
