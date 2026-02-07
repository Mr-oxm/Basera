# Photo Editor

A **professional-grade, Photoshop-style photo editor** built in Python with a modular, extensible architecture. Designed for scalability, performance, and clean code — not a toy.

<img width="1919" height="992" alt="image" src="https://github.com/user-attachments/assets/0b87d5d4-9866-4eff-b81a-6ad657589609" />


> **Screenshots placeholder** — screenshots go here once the UI is running.

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
| `tools/` | 14 interactive tools (Brush, Eraser, Clone Stamp…) |
| `styles/` | 10 layer styles (Drop Shadow, Glow, Bevel…) + engine |
| `masks/` | Mask manager and low-level mask operations |
| `transforms/` | Geometric transforms (scale, rotate, skew, perspective, warp) |
| `ui/` | PySide6 interface — main window, canvas, toolbar, panels, dialogs |
| `utils/` | Image I/O, color conversion, math helpers, background worker |

---

## Features

### Layer System
- Raster, Text, Shape, Adjustment, Group, Smart Object (architecture-ready)
- Opacity, visibility, locking, reordering, clipping masks
- Layer masks with feather, grow, shrink, refine
- Layer groups with nested compositing

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

### Drawing Tools (14)
Brush · Eraser · Clone Stamp · Healing Brush · Gradient · Paint Bucket · Rectangle Select · Ellipse Select · Lasso · Magic Wand · Text · Shape · Transform · Move

### Layer Styles (10)
Drop Shadow · Inner Shadow · Outer Glow · Inner Glow · Bevel & Emboss · Satin · Color Overlay · Gradient Overlay · Pattern Overlay · Stroke

### Selection System
Rectangle · Ellipse · Lasso · Magic Wand · Feather · Grow/Shrink · Invert

### Transform Tools
Scale · Rotate · Skew · Flip · Perspective · Free Transform · Grid Warp

### UI
- Professional dark theme
- Dockable panels (Layers, History, Adjustments, Properties, Color)
- Full menu bar with keyboard shortcuts
- Zoomable canvas with pan (middle-click) and scroll-wheel zoom
- Transparency checkerboard
- Status bar with cursor position, zoom level, document info
- Drag & drop image loading
- New Document dialog with presets

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
├── tools/                   # 14 interactive tools
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
│   │   ├── properties_panel.py
│   │   └── color_panel.py
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

## Roadmap

- [ ] GPU acceleration via CuPy backend
- [ ] Plugin system with hot-reload
- [ ] PSD file import/export
- [ ] RAW file support (via rawpy)
- [ ] Brush engine with texture and dynamics
- [ ] Vector layer rendering (SVG)
- [ ] Smart Object editing
- [ ] Content-Aware Fill
- [ ] Liquify tool
- [ ] Actions / macro recording
- [ ] Batch processing
- [ ] HDR tone mapping
- [ ] Color management (ICC profiles)
- [ ] Multi-document tabs
- [ ] Pen tablet pressure sensitivity

---

## License

MIT — see [LICENSE](LICENSE) for details.
