# Basera - بصيرة
![splash](https://github.com/user-attachments/assets/c00cfe66-a38b-4bf6-99df-6dcc78d992d8)



> **v0.4-alpha** — Performance optimizations, dynamic themes, full brush system, advanced vector booleans, UI overhaul, and multi-layer select.

A **professional-grade, Photoshop-style photo editor** built in Python with a modular, extensible architecture. Designed for scalability, performance, and clean code — not a toy.

> [!WARNING]
> This is a **pre-1.0 early version**. The editor is under active development and many features are incomplete, unstable, or not yet functional. Use at your own risk — contributions and bug reports are welcome.

### v0.4.0
<img width="1919" height="992" alt="Screenshot 2026-03-03 173450" src="https://github.com/user-attachments/assets/117edfc0-33bd-4099-b474-c23a7984a5b8" />
<img width="1919" height="984" alt="Screenshot 2026-03-03 175004" src="https://github.com/user-attachments/assets/84e2f4a3-3430-4eb4-bc12-0262acc14cab" />

### v0.3.0
<img width="1919" height="990" alt="Screenshot 2026-02-16 221017" src="https://github.com/user-attachments/assets/ff11c565-47d9-4877-b1bc-538bf4efb923" />

### v0.2.0
<img width="1919" height="992" alt="v0.2.0 Screenshot" src="https://github.com/user-attachments/assets/e960e2ad-8b13-46a6-afc2-e2f562e7426f" />

### v0.1.0
<img width="1919" height="992" alt="image" src="https://github.com/user-attachments/assets/0b87d5d4-9866-4eff-b81a-6ad657589609" />


---

## What's New in v0.4.0 (Basera - بصيرة)

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

## Architecture

```
┌──────────┐    ┌─────────────┐    ┌─────────────────┐    ┌──────────────┐    ┌──────────────┐
│  Canvas   │ →  │ Layer Stack  │ →  │ Blending Engine  │ →  │ Effects Pipe │ →  │ Final Render │
│ Viewport  │    │  (ordered)   │    │ (28 blend modes) │    │ (styles etc) │    │  (RGBA buf)  │
└──────────┘    └─────────────┘    └─────────────────┘    └──────────────┘    └──────────────┘
```

### Rendering Pipeline

1. **Canvas** — viewport state (zoom, pan, grid, guides)
2. **Layer Stack** — ordered collection of layers with group, mask, and clipping support
3. **Blending Engine** — composites each layer onto the canvas using Photoshop-compatible blend modes with proper Porter-Duff alpha compositing
4. **Effects Pipeline** — applies non-destructive adjustment layers, filters, and layer styles
5. **Final Render** — outputs RGBA float32 buffer, converted to uint8 for display

### Module Map

| Module | Responsibility |
|---|---|
| `core/` | Data models — Layer, Document, Selection, History, Canvas state, enums |
| `engine/` | Render engine, pipeline orchestrator, tile cache, compositor |
| `vector/` | Vector engine & tools (SVG, shapes, paths, pen/node tools) |
| `blending/` | 28 blend modes + extensible registry + engine |
| `effects/` | Effect base class and pipeline |
| `adjustments/` | 15 non-destructive adjustments (Brightness, Levels, Curves…) |
| `filters/` | 24 destructive filters across 6 categories |
| `tools/` | 13 interactive tools (Brush, Eraser, Clone Stamp, Move w/ transform…) |
| `styles/` | 10 layer styles (Drop Shadow, Glow, Bevel…) + engine |
| `masks/` | Mask manager and low-level mask operations |
| `transforms/` | Geometric transforms (scale, rotate, skew, perspective, warp) |
| `ui/` | PySide6 interface — main window, canvas, toolbar, panels, dialogs |
| `utils/` | Image I/O, color conversion, math helpers, background worker |

---

## Features

### Layer System
- **Raster, Vector, Text, Shape, Adjustment, Group, Smart Object** (architecture-ready)
- **Text layers** with full typography controls (font, bold, italic, alignment, spacing, color)
- Opacity, visibility, locking, reordering, clipping masks
- Layer masks with feather, grow, shrink, refine
- Layer groups with nested compositing
- **Layer styles** — Color Overlay, Stroke, Drop Shadow, Inner Shadow, Outer Glow, Inner Glow, Bevel & Emboss, Satin, Gradient Overlay, Pattern Overlay

### Blending Modes (28)
Normal · Dissolve · Darken · Multiply · Color Burn · Linear Burn · Darker Color · Lighten · Screen · Color Dodge · Linear Dodge · Lighter Color · Overlay · Soft Light · Hard Light · Vivid Light · Linear Light · Pin Light · Hard Mix · Difference · Exclusion · Subtract · Divide · Hue · Saturation · Color · Luminosity

### Non-Destructive Adjustments (15)
Brightness/Contrast · Levels · Curves · Exposure · Vibrance · Hue/Saturation · Color Balance · Black & White · Photo Filter · Gradient Map · Selective Color · Channel Mixer · Invert · Posterize · Threshold

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
- Professional dark theme
- Dockable panels (Layers, History, Adjustments, **Properties Bar**, Color, **Transform**)
- **Projects bar** for multi-document navigation
- Full menu bar with keyboard shortcuts
- Zoomable canvas with pan (middle-click), scroll-wheel zoom, and **rulers/guides**
- Transparency checkerboard
- Status bar with cursor position, zoom level, document info
- Drag & drop image loading
- New Document dialog with presets
- **Real-time blend mode preview** — hover over blend modes in the dropdown to see a live preview on the canvas before committing
- **Real-time brush/eraser preview** — see stroke as you paint
- **Real-time layer style preview** — adjust parameters and see results instantly

---

## Installation

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### With uv (recommended)

```bash
# Clone the repository
git clone https://github.com/Mr-oxm/PhotoEditor

cd PhotoEditor

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
├── __init__.py              # Package root
├── __main__.py              # Entry point
├── app.py                   # QApplication bootstrap
├── core/                    # Data models & enums
│   ├── brush_engine.py      # Brush dynamics & ABR parsing
│   ├── canvas.py
│   ├── color.py
│   ├── document.py
│   ├── enums.py
│   ├── history.py
│   ├── layer.py
│   ├── layer_stack.py
│   └── selection.py
├── commands/                # Action handling & undo system
├── engine/                  # Rendering pipeline
│   ├── compositor.py
│   ├── render_engine.py
│   ├── render_pipeline.py
│   └── tile_cache.py
├── vector/                  # Vector engine & tools
│   ├── svg.py               # SVG import/export
│   ├── boolean.py           # Vector boolean ops (union, subtract...)
│   ├── pick_segments.py     # Pick segment selection for complex curves
│   ├── shapes.py            # Shape primitives
│   ├── path.py              # Bezier path logic
│   ├── pen_tool.py          # Pen tool implementation
│   └── node_tool.py         # Node editing tool
├── blending/                # 28 blend modes + engine
│   ├── blend_modes.py       # Registry
│   ├── blending_engine.py   # Compositor
│   ├── normal.py
│   ├── darken.py
│   ├── lighten.py
│   ├── contrast.py
│   ├── comparative.py
│   └── color_blend.py
├── adjustments/             # 15 non-destructive adjustments
├── filters/                 # 24 filters in 6 categories
│   ├── blur/
│   ├── sharpen/
│   ├── noise/
│   ├── distort/
│   ├── stylize/
│   └── render/
├── tools/                   # Interactive tools
│   ├── brush.py             # Brush dynamics and abr support
│   ├── clone_stamp.py
│   ├── healing_brush.py
│   ├── selection_tools.py
│   ├── shape_tool.py
│   └── text_tool.py
├── styles/                  # 10 layer styles + engine
├── effects/                 # Effect pipeline
├── masks/                   # Mask manager & operations
├── transforms/              # Geometric transforms
├── ui/                      # PySide6 interface
│   ├── theme.py             # Dynamic themes setup
│   ├── main_window.py
│   ├── canvas_view.py
│   ├── toolbar.py           # New dynamic toolbar UI
│   ├── menus.py
│   ├── status_bar.py
│   ├── panels/
│   │   ├── layers_panel.py
│   │   ├── channels_panel.py # New channels panel
│   │   ├── brushes_panel.py  # Setting panel for brushes
│   │   ├── history_panel.py
│   │   ├── adjustments_panel.py
│   │   ├── properties_bar.py
│   │   ├── color_panel.py
│   │   ├── transform_panel.py
│   │   └── projects_bar.py
│   ├── widgets/
│   │   └── rulers.py
│   └── dialogs/
│       ├── new_document.py
│       ├── filter_dialog.py
│       └── text_dialog.py
└── utils/                   # Shared utilities
    ├── color_utils.py
    ├── image_io.py
    ├── math_utils.py
    └── worker.py
tests/
├── test_blending.py
└── test_adjustments.py
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

---

## Roadmap

- [ ] GPU acceleration via CuPy backend
- [ ] Plugin system with hot-reload
- [ ] PSD file import/export
- [ ] RAW file support (via rawpy)
- [x] ~~Brush engine with texture, dynamics and .abr support~~ (v0.4.0)
- [x] ~~Multi-layer selection~~ (v0.4.0)
- [x] ~~Vector boolean operations~~ (v0.4.0)
- [x] ~~Vector layer rendering (SVG)~~ (v0.3.0)
- [ ] Smart Object editing
- [ ] Content-Aware Fill
- [ ] Liquify tool
- [ ] Actions / macro recording
- [ ] Batch processing
- [ ] HDR tone mapping
- [ ] Color management (ICC profiles)
- [x] ~~Multi-document tabs~~ (implemented as Projects bar in v0.2.0)
- [ ] Pen tablet pressure sensitivity

---
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/mr-oxm/photoeditor)
---

## License

MIT — see [LICENSE](LICENSE) for details.
