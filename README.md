# Photo Editor

> **v0.2.0-alpha** — Text layers, adjustment layers, layer styles, and major UI improvements. Still experimental—expect bugs.

A **professional-grade, Photoshop-style photo editor** built in Python with a modular, extensible architecture. Designed for scalability, performance, and clean code — not a toy.

> [!WARNING]
> This is a **pre-1.0 early version**. The editor is under active development and many features are incomplete, slow, unstable, or not yet functional. Use at your own risk — contributions and bug reports are welcome.

<img width="1919" height="992" alt="Screenshot 2026-02-10 211250" src="https://github.com/user-attachments/assets/e960e2ad-8b13-46a6-afc2-e2f562e7426f" />


---

## What's New in v0.2.0

### Text Layers
- **Full text properties support**: font family, size, bold, italic, underline, alignment, color, letter spacing, line height
- Rich text editing with real-time preview
- Text layer manipulation and transformation

### Redesigned Color System
- **Color wheel picker** for intuitive color selection
- HSV/RGB/Hex input modes
- Live color preview and history
- Improved color panel with swatches

### Layers Panel Overhaul
- **Editable adjustment layers** — non-destructive color grading directly in the layer stack
- **Filter layers** — apply filters as stackable, editable layers
- **Layer effects/styles** — Color Overlay, Stroke, Drop Shadow, Glow, and more
- **Group layers** with proper nested compositing
- **Lock layers** to prevent accidental edits
- Drag-and-drop layer reordering

### Real-Time Previews
- **Blending modes** — hover to preview before applying
- **Brush and Eraser** — see stroke preview as you paint
- **Layer styles** — live preview of effects as you adjust parameters

### Multi-Project Support
- Open and switch between **multiple documents** in the same session
- **Projects bar** for quick navigation between open files
- Per-project undo/redo stacks

### UI Improvements
- **Properties bar** (formerly Properties panel) — streamlined, context-aware controls
- **Improved toolbar** with tool grouping and new icons
- **Enhanced color panel** with color wheel
- Better spacing, alignment, and visual hierarchy across all panels

### Working Tools
- **Gradient tool** with real-time manipulation and live preview
- **Eyedropper tool** now fully functional

### Still Not Working
- Healing Brush and Clone Stamp (source point selection broken)
- Shape tool (drawing primitives not implemented)
- Crop tool (selection → crop pipeline incomplete)
- Advanced selection tools (Lasso, Magic Wand, etc.) — only Move tool is functional

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
- **Raster, Text, Shape, Adjustment, Group, Smart Object** (architecture-ready)
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

### Drawing Tools (14)
Brush · Eraser · Clone Stamp · Healing Brush · **Gradient** · Paint Bucket · Rectangle Select · Ellipse Select · Lasso · Magic Wand · **Text** · Shape · **Move** (with integrated Transform) · **Eyedropper**

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
- Dockable panels (Layers, History, Adjustments, **Properties Bar**, Color)
- **Projects bar** for multi-document navigation
- Full menu bar with keyboard shortcuts
- Zoomable canvas with pan (middle-click) and scroll-wheel zoom
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
git clone https://github.com/yourname/photo-editor.git
cd photo-editor

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
│   ├── canvas.py
│   ├── color.py
│   ├── document.py
│   ├── enums.py
│   ├── history.py
│   ├── layer.py
│   ├── layer_stack.py
│   └── selection.py
├── engine/                  # Rendering pipeline
│   ├── compositor.py
│   ├── render_engine.py
│   ├── render_pipeline.py
│   └── tile_cache.py
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
├── tools/                   # Interactive tools (Move, Brush, Gradient, Eyedropper, Text)
├── styles/                  # 10 layer styles + engine
├── effects/                 # Effect pipeline
├── masks/                   # Mask manager & operations
├── transforms/              # Geometric transforms
├── ui/                      # PySide6 interface
│   ├── main_window.py
│   ├── canvas_view.py
│   ├── toolbar.py
│   ├── menus.py
│   ├── theme.py
│   ├── status_bar.py
│   ├── panels/
│   │   ├── layers_panel.py
│   │   ├── history_panel.py
│   │   ├── adjustments_panel.py
│   │   ├── properties_bar.py
│   │   ├── color_panel.py
│   │   └── projects_bar.py
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
- [ ] Layer masks do not paint or preview correctly in many scenarios
- [ ] Mask feathering and refinement produce inconsistent results
- [ ] No quick mask mode for visual mask editing

### Tools
- [x] ~~**Move tool** is not working — cannot drag layers on the canvas~~ (fixed — full move/resize/rotate via bounding box)
- [ ] **Clone Stamp and Healing Brush** are not functional — source point selection broken
- [ ] **Shape tool** not implemented
- [ ] **Crop tool** incomplete — selection-to-crop pipeline missing
- [ ] **Selection tools** (Lasso, Magic Wand, etc.) have no visible selection box / marching ants indicator
- [ ] Text tool has limited editing — no in-canvas text reflow
- [ ] Brush engine lacks pressure sensitivity and dynamics
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
- [ ] Brush engine with texture and dynamics
- [ ] Vector layer rendering (SVG) (in the works)
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

## License

MIT — see [LICENSE](LICENSE) for details.
