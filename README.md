# Basera - بصيرة
<img width="1920" height="1080" alt="splash_2" src="https://github.com/user-attachments/assets/625dfc5a-cdcd-471a-8047-3b2c2413a2f6" />


> **v0.5.0-alpha** — Native `.basera` project format, full project creation & export workflows, completely reworked UI with centralized theming, new adjustment layers, clipping/child layers, and zoom-to-cursor.

A **professional-grade, Photoshop-style photo editor** built in Python with a modular, extensible architecture. Designed for scalability, performance, and clean code — not a toy.

> [!WARNING]
> This is a **pre-1.0 early version**. The editor is under active development and many features are incomplete, unstable, or not yet functional. Use at your own risk — contributions and bug reports are welcome.
### v0.5.0
<img width="1920" height="1010" alt="1" src="https://github.com/user-attachments/assets/bf076e6b-6173-492c-8a69-e25507e7f866" />

### v0.4.0
<img width="1919" height="992" alt="v 0.4 pic 1" src="https://github.com/user-attachments/assets/117edfc0-33bd-4099-b474-c23a7984a5b8" />
<img width="1919" height="984" alt="v 0.4 pic 2" src="https://github.com/user-attachments/assets/84e2f4a3-3430-4eb4-bc12-0262acc14cab" />

### v0.3.0
<img width="1919" height="990" alt="v 0.3 pic" src="https://github.com/user-attachments/assets/ff11c565-47d9-4877-b1bc-538bf4efb923" />

### v0.2.0
<img width="1919" height="992" alt="v0.2.0 Screenshot" src="https://github.com/user-attachments/assets/e960e2ad-8b13-46a6-afc2-e2f562e7426f" />

### v0.1.0
<img width="1919" height="992" alt="image" src="https://github.com/user-attachments/assets/0b87d5d4-9866-4eff-b81a-6ad657589609" />


---

## What's New in v0.5.0

### Native `.basera` Project Format
- **Save & Share Projects**: Projects are now saved as `.basera` files — open, continue, and share your work at any time with nothing lost.
- **Full Fidelity**: All layers, adjustments, masks, and settings are preserved across sessions.

### Project Creation Window
- **Templates Library**: Dozens of built-in templates covering common print, web, and social media sizes.
- **Custom Dimensions**: Set width and height with full unit conversion support — pixels, centimeters, millimeters, inches, and more.
- **DPI Support**: Choose your output resolution (72, 96, 150, 300 dpi, or custom).
- **Color Profiles**: Select the working color space — RGB or CMYK — at project creation time.
- **Project Background**: Choose the initial canvas background (white, black, transparent, or a custom color).

### Export Window
- **Flexible Export**: Export your finished work to any supported format directly from a dedicated export dialog.
- **Format Options**: Configure extension-specific settings (quality, compression, color space) before exporting.

### Splash Screen
- **Reworked Splash Logic**: The splash screen flow has been redesigned for a cleaner, faster startup experience.

### Complete UI Refresh
- **Brand-new visual design** across the entire application — every panel, toolbar, and dialog has been modernized.
- **Centralized UI Theming**: All styling is driven through a single theming system, making it easy to scale and maintain visual consistency.
- **Reworked Theme List**: A new curated set of built-in UI themes is available, replacing the previous selection.

### Adjustment Windows
- Dedicated, purpose-built dialogs for **Hue/Saturation**, **Levels**, **Brightness/Contrast**, **Curves**, and **Vibrance** — each with real-time canvas preview.

### New Non-Destructive Adjustment Layers and Their Windows
- **Split Toning**: Apply independent color toning to highlights and shadows.
- **Normals**: Normal-map-aware adjustment for texture and 3D workflows.
- **Recolorer**: Remap specific hue ranges to new colors non-destructively.
- **White Balance**: Correct or creatively shift color temperature and tint.

### Clipping & Child Layers
- **Clipping Layers**: Clip any layer to the content of the layer below — fully implemented and composited correctly.
- **Child Layers**: Nest layers inside parent layers for organized, hierarchical compositing.

### Layers Panel Overhaul
- **Refactored Panel**: Significant bug fixes and a cleaner internal architecture.
- **Drag & Drop**: Improved drag-and-drop for reordering, nesting, and grouping layers with better visual feedback.
- **Groups & Nesting**: Easier creation and management of layer groups and nested hierarchies.

### Zoom to Mouse Position
- **Smart Zoom**: The canvas now zooms toward the cursor position, matching the behaviour of professional design tools.

---

## Previous v0.4.0 Highlights

### Performance & Engine Optimizations
- **Off-UI-Thread Compositing**: Rendering is now fully asynchronous in a background worker.
- **Render Scheduler**: Debouncing and throttling limits renders to ~30 FPS during rapid events.
- **Image Pool (Buffer Reuse)**: Reduces allocation churn and GC pressure during interactive rendering.
- **Tile Processor**: Infrastructure ready for parallel filter processing.
- **Async Operations**: Saving documents runs off the UI thread to avoid freezes.

### Full Brush System
- **Brush Engine**: Support for standard `.abr` Photoshop brush files!
- **Brush Panel & Selector**: New dedicated panel and selector to configure brush dynamics.
- **Tool Support**: Complete brush system integrated across Brush Tool, Eraser, and Masks.

### Advanced Vector Boolean Operations
- **Full Boolean System**: Union, Subtract, Intersection, Extrude, and Divide.
- **Pick Segments**: Click to selectively include/exclude sub-paths across layers to create complex curves.

### Multi-Layer Handling
- **Multi-layer Selection**: Ability to select and manipulate multiple pixel and vector layers simultaneously.

### UI & Identity Overhaul
- **Dynamic Themes**: Fully dynamic real-time theme switching capability.
- **New App Identity**: Rebranded as Basera - بصيرة with a new localized name, logo, and splash screen.
- **Improved Toolbars & Panels**: New tool bar with updated UI icons.
- **Channels Panel**: New dedicated channels panel to toggle visibility of Red, Green, Blue, and Alpha channels.

### Quality of Life & Bug Fixes
- **Tool Refinements**: Quality improvements across Node Tool, Gradient Tool, Move Tool, and Selection Tools.
- **Stability**: Multiple bug fixes in history, transformations, rotations, accidental clicks, UI behaviors, and vectors.

---

## Previous v0.3.0 Highlights

### Vector Revolution
- **Full Vector Support**: SVG import/export and scalable vector layers
- **Pen Tool**: Create precise paths and shapes using Bezier curves
- **Node Tool**: Edit paths, manipulate nodes, and adjust curves
- **Shape Tools**: Rectangle, Ellipse, Polygon and customizable shapes

### Advanced Selection & Masking
- **New Selection Tools**: Lasso, Magic Wand, Rectangle & Ellipse Select
- **Masking System**: Create masks from selections, paint directly on masks to hide/reveal content
- **Refined Selection workflow**: Visual indicators and better interaction

### Retouching Power
- **Healing Brush**: Remove blemishes and unwanted objects seamlessly
- **Clone Stamp**: Duplicate parts of an image with precision

### Enhanced UI & Panels
- **Transform Panel**: Precise numerical control over position, size, and rotation
- **Rulers & Guides**: Drag guides from rulers for precise alignment
- **Improved Workspace**: Better panel organization and visual feedback

### Tool Enhancements
- **Crop Tool**: Now fully functional at both layer and canvas levels

## Previous v0.2.0 Highlights
- **Text Layers**: Rich text editing with real-time preview
- **Redesigned Color System**: Color wheel, HSV/RGB/Hex modes
- **Layers Panel Overhaul**: Group layers, adjustment layers, layer effects
- **Multi-Project Support**: Tabs for multiple open documents

---

### Module Map

| Module | Responsibility |
|--------|----------------|
| `core/` | Data models — Layer, Document, Selection, History, Canvas state, enums, color engine |
| `engine/` | Render engine, pipeline orchestrator, compositor, tile cache, render scheduler + worker |
| `commands/` | Reversible document mutations — layer, mask, effect, and document commands |
| `processors/` | `ImageProcessor` ABC shared by all adjustments and filters |
| `registries/` | Lazy importlib-based processor registries (no UI coupling) |
| `adjustments/` | 19 non-destructive adjustments (Brightness, Levels, Curves, Split Toning…) |
| `filters/` | 20+ destructive filters across 6 categories |
| `blending/` | 32 blend modes + extensible registry + BlendingEngine |
| `effects/` | Effect base class and ordered post-process pipeline |
| `styles/` | 10 layer styles (Drop Shadow, Glow, Bevel…) + StyleEngine |
| `masks/` | Mask manager — legacy per-layer masks + mask-layer API |
| `transforms/` | Geometric transforms (scale, rotate, skew) in premultiplied-alpha space |
| `tools/` | 15+ interactive canvas tools incl. `move/` sub-package (align, auto-select, float…) |
| `vector/` | Full vector subsystem — SVG/PDF, paths, shapes, boolean ops, pen/node/shape tools |
| `color/` | Color management — space conversions, harmonies, gradients, swatches |
| `ui/` | PySide6 interface — window, canvas, toolbar, panels, dialogs, icons, theming |
| `utils/` | Image I/O, `.basera` project I/O, recent files, math helpers, background worker |

---

## Features

### Layer System
- **Raster, Vector, Text, Shape, Adjustment, Group, Smart Object** (architecture-ready)
- **Text layers** with full typography controls (font, bold, italic, alignment, spacing, color)
- Opacity, visibility, locking, reordering, clipping masks
- **Clipping layers** — clip any layer to the content boundary of the layer below
- **Child layers** — nest layers inside parent layers for hierarchical compositing
- Layer masks with feather, grow, shrink, refine
- Layer groups with nested compositing
- **Layer styles** — Color Overlay, Stroke, Drop Shadow, Inner Shadow, Outer Glow, Inner Glow, Bevel & Emboss, Satin, Gradient Overlay, Pattern Overlay

### Blending Modes (28)
Normal · Dissolve · Darken · Multiply · Color Burn · Linear Burn · Darker Color · Lighten · Screen · Color Dodge · Linear Dodge · Lighter Color · Overlay · Soft Light · Hard Light · Vivid Light · Linear Light · Pin Light · Hard Mix · Difference · Exclusion · Subtract · Divide · Hue · Saturation · Color · Luminosity

### Non-Destructive Adjustments (19)
Brightness/Contrast · Levels · Curves · Exposure · Vibrance · Hue/Saturation · Color Balance · Black & White · Photo Filter · Gradient Map · Selective Color · Channel Mixer · Invert · Posterize · Threshold · **Split Toning** · **Normals** · **Recolorer** · **White Balance**

### Filters (24)
**Blur:** Gaussian · Motion · Radial · Surface · Lens  
**Sharpen:** Sharpen · Unsharp Mask · Smart Sharpen  
**Noise:** Add Noise · Reduce Noise · Dust & Scratches · Median  
**Distort:** Ripple · Wave · Twirl · Pinch · Perspective  
**Stylize:** Emboss · Find Edges · Solarize · Oil Paint  
**Render:** Clouds · Difference Clouds · Lighting Effects

### Move & Transform (unified on-canvas workflow)
- **Move tool** with a Photoshop-style **bounding box** around the selected layer
- **Resize** by dragging corner / edge handles — anchor-based positioning keeps the opposite side fixed
- **Rotate** by dragging outside the bounding box — bounding box visually rotates with the content
- **Resize after rotation** works correctly: the pre-rotation pixels are scaled then re-rotated, so the rotation is never lost and quality is preserved
- Per-layer rotation state — switch layers or tools and come back; the bounding box shows the correct rotation
- Smart cursor feedback: resize arrows, move cross, or rotation crosshair depending on hover position
- All transform operations are fully **undoable / redoable**

### History & Undo System
- Linear undo / redo stack (configurable depth, default 50 states)
- **Full structural undo**: adding, placing, duplicating, and deleting layers can all be undone and redone — the entire layer stack (order, metadata, pixels) is saved and rebuilt on restore
- Per-layer state (position, visibility, opacity, blend mode, rotation) is captured in every snapshot
- History panel with click-to-jump navigation
- Opening an image creates an "Open Image" base state — undo never goes back to a blank canvas

### Drawing Tools (15)
Brush · Eraser · Clone Stamp · Healing Brush · **Gradient** · Paint Bucket · Rectangle Select · Ellipse Select · Lasso · Magic Wand · **Text** · **Pen** · **Node** · Shape · **Move** (with integrated Transform) · **Eyedropper** · **Crop**

### Layer Styles (10)
Drop Shadow · Inner Shadow · Outer Glow · Inner Glow · Bevel & Emboss · Satin · **Color Overlay** · Gradient Overlay · Pattern Overlay · **Stroke**

### Layers Panel
- Dedicated **eye icon** button to toggle layer visibility
- Dedicated **lock icon** button to toggle layer locking
- **Layer effects/styles** indicators and editing
- Icons update in real time; buttons positioned to the right of the layer name
- Click to select, add, duplicate, delete layers
- Drag-and-drop reordering

### Selection System
Rectangle · Ellipse · Lasso · Magic Wand · Feather · Grow/Shrink · Invert

### Transform Engine
Scale · Rotate · Skew · Flip · Perspective · Free Transform · Grid Warp

### UI
- Professional dark theme with a **centralized theming system** for scalable UI customization
- **Reworked theme list** — a new curated set of built-in UI themes
- Dockable panels (Layers, History, Adjustments, **Properties Bar**, Color, **Transform**)
- **Projects bar** for multi-document navigation
- Full menu bar with keyboard shortcuts
- Zoomable canvas with pan (middle-click), scroll-wheel zoom, **rulers/guides**, and **zoom-to-cursor**
- Transparency checkerboard
- Status bar with cursor position, zoom level, document info
- Drag & drop image loading
- **Project Creation dialog** — templates, custom dimensions, unit conversion, DPI, color profiles (RGB/CMYK), and background
- **Export dialog** — export to any supported format with per-format settings
- **Real-time blend mode preview** — hover over blend modes in the dropdown to see a live preview on the canvas before committing
- **Real-time brush/eraser preview** — see stroke as you paint
- **Real-time layer style preview** — adjust parameters and see results instantly
- **Adjustment windows** — dedicated dialogs for Hue/Saturation, Levels, Brightness/Contrast, Curves, and Vibrance

---

## Installation

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### With uv (recommended)

```bash
# Clone the repository
git clone https://github.com/Mr-oxm/Basera

cd Basera

# Create environment and install dependencies
uv sync

# Run
uv run python -m photo_editor
```

### With pip

```bash
pip install -e .
python -m photo_editor
```

### Run Tests

```bash
uv run pytest tests/ -v
```

---

## Extending the Editor

### Adding a New Blend Mode

1. Create a function in `photo_editor/blending/` or a new file:

```python
def blend_my_mode(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    return np.clip(base + overlay * 0.5, 0, 1)
```

2. Register it in your plugin or startup code:

```python
from photo_editor.blending import register_blend_mode
from photo_editor.core.enums import BlendMode

# Extend the enum or use a custom key
register_blend_mode(BlendMode.NORMAL, blend_my_mode)  # or a custom mode
```

### Adding a New Filter

1. Create a file in the appropriate `filters/` subdirectory:

```python
from ..filter_base import Filter
import numpy as np

class MyFilter(Filter):
    def __init__(self):
        super().__init__("My Filter", {"intensity": 50})

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image)
        alpha = self._alpha(image)
        # Your processing here
        result = rgb * (params["intensity"] / 100.0)
        return self._merge(result, alpha)
```

### Adding a New Adjustment

Follow the same pattern in `adjustments/` — inherit from `Adjustment`, implement `apply()`.

### Adding a New Layer Style

Inherit from `LayerStyle` in `styles/`, implement `apply()`.

---

## Project Structure

```
photo_editor/
├── __main__.py              Entry point
├── app.py                   QApplication bootstrap
├── core/                    Data models & enums
│   ├── document.py
│   ├── layer.py
│   ├── layer_stack.py
│   ├── selection.py
│   ├── history.py
│   ├── canvas.py
│   ├── enums.py
│   ├── color.py
│   ├── color_engine.py      Internal color math used by adjustments
│   ├── text_layer.py
│   ├── brush_engine.py      Brush dynamics & ABR parsing
│   ├── image/               Tile processing contracts
│   └── services/            Extracted domain operations
├── commands/                Reversible mutations (undo/redo)
│   ├── base.py
│   ├── layer/               Add, Remove, Duplicate, Flatten, Clip, DropAsMask,
│   │                        Resize, Rotate, Reorder, Rename, AddGroup…
│   ├── mask/                Add, Remove, Apply, Convert, Invert, Attach
│   ├── effect/              AttachAdjustment, UpdateEffect
│   └── document/            Save, PlaceImage
├── engine/                  Rendering pipeline
│   ├── compositor.py
│   ├── render_engine.py
│   ├── render_pipeline.py
│   ├── tile_cache.py
│   ├── cache/               ImagePool — float32 buffer reuse
│   └── renderer/            RenderScheduler + RenderWorker (~30 fps)
├── processors/              ImageProcessor ABC
├── registries/              Lazy processor registries
├── adjustments/             19 non-destructive adjustments
├── filters/                 20+ destructive filters
│   ├── blur/                Gaussian, Motion, Radial, Lens, Surface
│   ├── sharpen/             Sharpen, Smart Sharpen, Unsharp Mask
│   ├── noise/               Add Noise, Reduce Noise, Dust & Scratches, Median
│   ├── distort/             Twirl, Pinch, Perspective, Ripple, Wave
│   ├── stylize/             Emboss, Find Edges, Oil Paint, Solarize
│   └── render/              Clouds, Difference Clouds, Lighting Effects
├── blending/                32 blend modes + BlendingEngine
│   ├── blend_modes.py       Registry
│   ├── blending_engine.py
│   ├── normal.py / darken.py / lighten.py
│   ├── contrast.py / comparative.py / color_blend.py
│   └── ...
├── effects/                 Effect pipeline
├── styles/                  10 layer styles + StyleEngine
├── masks/                   Mask manager & operations
├── transforms/              Geometric transforms (scale, rotate, skew)
├── tools/                   Interactive canvas tools
│   ├── move/                Move tool sub-package
│   │   ├── move_tool.py     Multi-layer move + bounding box
│   │   ├── align_ops.py     Align / distribute
│   │   ├── auto_select.py   Click-to-select layer
│   │   ├── float_selection.py
│   │   ├── hit_test.py
│   │   ├── resize_ops.py
│   │   ├── rotate_ops.py
│   │   ├── vector_commit.py
│   │   └── _enums.py
│   ├── brush.py / eraser.py / clone_stamp.py / healing_brush.py
│   ├── gradient_tool.py / paint_bucket.py / selection_tools.py
│   ├── shape_tool.py / text_tool.py / transform_tool.py
│   └── crop_tool.py / pan_tool.py / zoom_tool.py / eyedropper.py
├── vector/                  Full vector subsystem
│   ├── scene.py / path.py / shapes.py / style.py / geometry.py
│   ├── bezier.py            Bezier math helpers
│   ├── boolean.py / boolean_ops.py
│   ├── spatial.py           RTree spatial index helpers
│   ├── shape_tool.py        Interactive shape drawing
│   ├── pick_segments.py
│   ├── svg.py / pdf.py      Import/export
│   └── rasterizer.py / pen_tool.py / node_tool.py
├── color/                   Color management
│   ├── conversions.py       HSV/HSL/CMYK/Lab/Oklab + perceptual lerp
│   ├── harmonies.py         Complementary, triadic, etc.
│   ├── gradients.py         Conical, diamond gradients + presets
│   ├── swatches.py          Persistent swatch palette (JSON)
│   └── manager.py           ColorManager singleton (FG/BG)
├── ui/                      PySide6 interface
│   ├── main_window.py
│   ├── app_signals.py       Cross-controller signal hub
│   ├── document_session.py  Multi-document tab state
│   ├── file_tab_bar.py      Document tab bar widget
│   ├── toolbar.py / menus.py / status_bar.py
│   ├── tool_manager.py / shortcut_manager.py
│   ├── theme.py / styles.py / welcome_screen.py
│   ├── filter_runner.py
│   ├── controllers/         14 domain controllers (ControllerBase)
│   ├── canvas/              canvas_input, canvas_overlays, canvas_cursors
│   ├── panels/
│   │   ├── layers/          Full layers panel sub-package (10 modules)
│   │   ├── properties/      Tool options bar sub-package (10 modules)
│   │   └── adjustments_panel, brushes_panel, channels_panel,
│   │                color_panel, history_panel, transform_panel
│   ├── dialogs/
│   │   ├── adjustments/     11 adjustment-specific dialogs
│   │   └── filter_dialog, export_dialog, layer_styles_dialog,
│   │                new_project_dialog, shortcuts_dialog, text_dialog…
│   ├── icons/               assets, layers, properties, tool_icons
│   ├── widgets/             color_wheel, color_sliders, gradient_editor,
│   │                gradient_slider_row, rulers, swatch_grid
│   └── services/            layer_panel_state, selection_ui_state,
                     guide_ui_state, vector_ui_state, rasterize_guard
└── utils/
    ├── color_utils.py
    ├── image_io.py          Format-detecting imread/imwrite
    ├── math_utils.py
    ├── project_io.py        .basera project serialization
    ├── recent_projects.py   Recent-files list persistence
    └── worker.py            Background QThread wrapper
```

---

## Performance Notes

- All image processing uses **NumPy vectorised operations** — no Python-level pixel loops
- Heavy operations run **off the UI thread** via `Worker` (QThreadPool)
- Layer rendering is **cached** — only dirty layers are re-rendered
- **Tile-based rendering** architecture is included and ready for activation on large canvases
- GPU-ready abstraction: the blending engine's functional interface allows drop-in CuPy/GPU replacements

---

## Known Issues & Limitations

This is an early alpha — the following are known problems that need to be addressed:

### Performance
- [ ] Rendering can be slow on large canvases or with many layers
- [ ] UI may freeze during heavy filter/adjustment operations
- [ ] Memory usage is not optimized — large documents consume excessive RAM
- [ ] Undo/redo stack holds full image copies (including pre-rotation originals), causing memory bloat

### Layers
- [ ] Layer groups do not composite correctly in all cases
- [ ] Dragging layers to reorder can be unreliable in some edge cases
- [ ] Clipping masks may not update visually in real time
- [x] ~~Deleting layers sometimes leaves stale render artifacts~~ (fixed — full structural undo rebuilds the stack)

### Masking
- [x] ~~Layer masks do not paint or preview correctly in many scenarios~~ (fixed — full masking support)
- [x] ~~Mask feathering and refinement produce inconsistent results~~ (fixed)
- [ ] No quick mask mode for visual mask editing

### Tools
- [x] ~~**Move tool** is not working — cannot drag layers on the canvas~~ (fixed — full move/resize/rotate via bounding box)
- [x] ~~**Clone Stamp and Healing Brush** are not functional~~ (fixed — fully implemented)
- [x] ~~**Shape tool** not implemented~~ (fixed — Rectangle, Ellipse, Polygon, etc.)
- [x] ~~**Crop tool** incomplete — selection-to-crop pipeline missing~~ (fixed — works on layer and canvas level)
- [x] ~~**Selection tools** (Lasso, Magic Wand, etc.) have no visible selection box / marching ants indicator~~ (fixed — new selection engine)
- [ ] Text tool has limited editing — no in-canvas text reflow
- [ ] Brush engine pressure sensitivity (partial support)
- [x] ~~Transform handles are not rendered on the canvas~~ (fixed — bounding box with 8 handles, rotates with content)
- [x] ~~**Gradient tool** not functional~~ (fixed — real-time manipulation and preview)
- [x] ~~**Eyedropper tool** not working~~ (fixed)

### General
- [ ] Keyboard shortcuts may conflict or not work on all platforms
- [ ] Zoom and pan can feel sluggish at high zoom levels
- [ ] No crash recovery or auto-save
- [x] ~~Filter previews are not live — must apply to see result~~ (blend mode preview is now live on hover)
- [x] ~~No file save/export~~ (Save / Save As now functional)
- [x] ~~No native project format~~ (`.basera` project files in v0.5.0)
- [x] ~~Clipping masks may not update visually in real time~~ (clipping layers fully implemented in v0.5.0)
- [x] ~~Dragging layers to reorder can be unreliable~~ (layers panel overhauled in v0.5.0)

---

## Roadmap

- [ ] GPU acceleration
- [ ] Plugin system with hot-reload
- [ ] PSD file import/export
- [ ] RAW file support (via rawpy)
- [x] ~~Brush engine with texture, dynamics and .abr support~~ (v0.4.0)
- [x] ~~Multi-layer selection~~ (v0.4.0)
- [x] ~~Vector boolean operations~~ (v0.4.0)
- [x] ~~Vector layer rendering (SVG)~~ (v0.3.0)
- [x] ~~Native project file format (save/share/resume)~~ (`.basera` in v0.5.0)
- [x] ~~Project creation dialog with templates, units, DPI, and color profiles~~ (v0.5.0)
- [x] ~~Dedicated export dialog~~ (v0.5.0)
- [x] ~~Clipping layers and child layers~~ (v0.5.0)
- [x] ~~Zoom to mouse position~~ (v0.5.0)
- [x] ~~Centralized UI theming system~~ (v0.5.0)
- [ ] Smart Object editing
- [ ] Content-Aware Fill
- [ ] Liquify tool
- [ ] Actions / macro recording
- [ ] Batch processing
- [ ] HDR tone mapping
- [ ] Color management (full ICC profile pipeline)
- [x] ~~Multi-document tabs~~ (implemented as Projects bar in v0.2.0)
- [ ] Pen tablet pressure sensitivity

---

## License

MIT — see [LICENSE](LICENSE) for details.
