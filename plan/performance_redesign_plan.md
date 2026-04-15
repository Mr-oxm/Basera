# Photo Editor Performance Redesign Plan

## Executive Summary

The editor is slow because it is still a CPU-first, full-frame compositor wrapped in a Python UI,
not a modern incremental image engine. The codebase has some good instincts — region blending, a
buffer pool, a render scheduler, and a tile cache scaffold — but the critical path still recomputes
too much, copies too much, snapshots too much, and throws most of its "incremental" machinery away
during interactive rendering.

The most important truth is this: the app does not have real GPU acceleration for image processing.
It has GPU-assisted presentation. The heavy work happens in NumPy, OpenCV, PIL, and QPainter on the
CPU, then the final RGBA buffer is uploaded and drawn. That is not the same thing as Photoshop-class
GPU compute.

At 1080p, a single `float32 RGBA` buffer is already about 31.6 MiB. This code routinely creates
multiple full-frame buffers per render, per preview, per history step, and sometimes per operation.
That is why the app can feel disproportionately slow and memory-hungry even before the layer count
gets large.

---

## Root Cause Analysis

### 1. Why it is slow even on one 1080p layer

The bottleneck is not one thing. It is a stack of bad multipliers.

`1080p float32 RGBA` is expensive by itself:

- `1920 * 1080 * 4 channels * 4 bytes` = about `31.6 MiB` per image buffer.
- Every extra full-frame temp, copy, premultiply/unpremultiply pass, uint8 conversion, or preview
  copy adds another tens of MiB of memory traffic.
- Even if CPU arithmetic is vectorized inside NumPy or OpenCV, memory bandwidth and allocation
  churn become dominant quickly.

The main render path is still full-document compositing. `RenderPipeline.execute()` simply calls
`Compositor.composite()` across the whole document. The tile cache is explicitly marked as not fully
implemented, and the background worker **invalidates the pipeline before every render anyway.**

**Critical smoking gun — `render_worker.py` line 66:**

```python
def _do_render(self) -> np.ndarray:
    self._pipeline.invalidate()        # <-- THIS LINE kills every cache
    rgba_float = self._pipeline.execute(self._document)
```

This is the single most damaging line in the entire codebase. Every single render worker —
including debounced 33ms interactive renders — begins by calling `invalidate()`, which internally
calls `TileCache.invalidate_all()` and sets `_uint8_valid = False`. This means:

- The `execute_to_uint8()` uint8 cache in `RenderPipeline` is **never** used during interaction.
- The `TileCache` dirty-tile bookkeeping from `invalidate_region()` calls (made by tools like the
  brush) is silently discarded and reset on every render.
- There is zero incremental benefit from any tool that correctly calls `invalidate_region()`.

This is a single-line fix that will deliver measurable improvement immediately, but it requires
dirty-region compositing to be correct first.

The async worker also defeats caching by invalidating the pipeline before rendering. So even though
there is a cached uint8 path in `RenderPipeline`, the async render path largely bypasses its
benefits during interaction.

**`_place_pixels` is still called on full-canvas allocations for clipping chains:**

`BlendingEngine.blend_region_inplace()` is a real optimization — it blends only the overlapping
region. However, the compositor still calls `_place_pixels()` (which allocates a full `(H, W, 4)`
canvas-sized buffer) whenever a layer participates in a clipping chain or `needs_placed`. In a
10-layer document with clipping masks, this produces many full-canvas allocations per frame even
though `blend_region_inplace` was designed to avoid exactly this. The refactor is half-done.

There are also too many full-canvas intermediates in the compositor. While
`BlendingEngine.blend_region_inplace()` is a real improvement, the compositor still repeatedly
materializes placed images and masks into document-sized buffers for clipping, child compositing,
and masks. That creates severe memory bandwidth pressure.

Python overhead is not the sole bottleneck, but it is absolutely part of the problem:

- The compositor orchestrates many Python-level layer scans, dict lookups, and branch-heavy paths.
- Brush stamping walks stroke points in Python.
- Some filters use outright nested Python loops.
- Undo/history serializes layer metadata and array copies in Python.
- Qt-side conversions add more Python/C++ boundary overhead.

The worst example of pure Python pixel work is the `OilPaint` filter — a `for y in range(h): for x
in range(w):` nested loop in pure Python, calling `np.bincount` per pixel. At 1080p (2,073,600
iterations) with a radius of 4 this is catastrophically slow and completely blocks the UI thread
if called synchronously.

**`np.any(over_a)` in `blend_region_inplace` is an O(N) scan per layer:**

For every layer blend call, the code does:

```python
if not np.any(over_a):
    return
```

This is correct as a short-circuit, but for a fully opaque 1920×1080 layer, it scans 2,073,600
pixels just to confirm blending is needed. A better design tracks whether a layer has any non-zero
alpha as a dirty flag at paint time rather than scanning every frame.

Adjustment and filter preview is also heavier than it should be. The dialog path keeps a full copy
of original pixels, then on every parameter change applies the processor to another full copy. That
is acceptable for small images and unacceptable for professional interactive editing.

**Preview downsampling happens after full-resolution compositing:**

`render_worker.py`'s `_downsample_to_preview()` runs after `execute()` returns the full composite.
The worker composites 1920×1080 in full float32, converts to uint8, then resizes. The correct
approach for interactive preview is to scale the source content down before compositing, so all
blend, adjustment, and filter passes run at preview resolution (e.g. 960×540), not at export
resolution. This is a 4× saving in compute at half-resolution preview.

There is also hidden conversion overhead:

- NumPy `float32` render buffer
- to `uint8`
- to `QImage`
- to `QPixmap`
- then drawn in Qt
- sometimes vector content goes through `QPainter -> QImage -> NumPy float32` before re-entering
  the compositor

`VectorRasterizer` is a CPU-side rasterization plus conversion path, not a retained GPU vector
pipeline. Vector layers are rasterized fresh every frame with no result cache.

**Pre-scan overhead is O(n) per frame, every frame:**

`Compositor.composite()` performs six separate O(n) passes over the full layer list before the main
render loop begins: building `mask_layer_ids`, `adj_children`/`adj_child_ids`,
`standalone_mask_ids`, `group_ids`, `regular_children`, and `needs_placed`. For a 20-layer
document, this is 120 Python-level layer iterations before a single pixel is blended. These
structures only need to be recomputed when the layer stack topology changes (add/remove/reorder),
not on every render.

**`_apply_filters_padded` always copies, even with zero padding:**

```python
pad = self._calc_filter_padding(adj_layers)
if pad > 0:
    ...
else:
    pixels = pixels.copy()     # <-- unconditional full-layer copy
```

Every layer with no filter effects gets an unconditional full-layer copy. At 1080p with 10 layers,
this is 10 × 31.6 MiB = 316 MiB of pointless memory traffic per frame.

### 2. Why performance collapses at 10+ layers

The render cost scales roughly like:

`full-frame passes * layer count * effect/mask/style complexity`

The common path is not truly `O(n^2)` for a flat stack, but it is also not a clean `O(n)` with a
low constant. It is `O(n * full-frame work)` with repeated scans, repeated placements, and
special-case branches for groups, masks, clipping, child filters, and styles. In real scenes with
grouped layers, clipping chains, masks, and previews, it can behave close to quadratic in practice
because multiple subsystems keep rescanning the layer stack and recomputing derived buffers.

The biggest reasons the curve gets ugly:

- No dirty-region compositing in the main path
- No tile-based evaluation in the main path
- No intermediate node cache for composited subtrees
- Group compositing is recomputed, not retained as reusable graph nodes
- `composite_group_tight()` scans the entire stack twice: once for bounds, once for pixels — this
  is O(n) per group, and nested groups make it O(n × depth)
- Filter previews and transforms keep rerendering full buffers
- Some panel refreshes trigger additional thumbnail and group-thumbnail work on top of canvas
  rendering
- Vector layers rasterized fresh every frame with no result cache
- The layer topology pre-scans repeat on every render regardless of what changed

The scheduler is also less efficient than it looks. It debounces request submission, but it does
not cancel in-flight work. Old renders can still burn CPU even if their result is discarded later.
That means dragging a slider or painting fast can produce a backlog of obsolete work that still
hammers the CPU.

**The GIL makes background rendering non-parallel with UI work:**

The `RenderWorker` runs in `QThreadPool`, and NumPy releases the GIL during pure-C array
operations. However, the Python-level compositor orchestration loop (layer iteration, dict lookups,
branch logic, style/mask dispatch) holds the GIL throughout. This means the UI thread contends
with the render thread for the GIL, causing micro-stutters during interaction even when the GPU is
idle. Moving the compositor core to Rust solves this permanently.

**Document is read from a background thread without synchronization:**

`RenderWorker` reads `document.layers` from a worker thread while the UI thread may be mutating
the same document. There is no lock, no snapshot, no copy-on-write. This is an active race
condition that can produce rendering artifacts, crashes, or torn frames under rapid interaction.

This becomes much worse with 10+ layers because:

- each stale worker still does a full composite
- the shared pipeline is mutable
- every worker calls `invalidate()`
- and the only thing discarded is the final displayed result, not the wasted compute

### 3. Why RAM usage explodes

The history system is the biggest offender. It stores full pixel copies of every layer for every
snapshot, plus masks, plus non-destructive transform sources, plus the full selection mask.

On a 10-layer 1080p document, a single snapshot can easily land in the hundreds of MiB if layers
are full-sized and some have `_source_pixels`. With 50 history states, the theoretical worst case
is absurd. Even if real projects are smaller than worst case, the design is still fundamentally
wrong for a professional editor.

**The `HistoryState` data model is blind to what changed:**

`layer_data: dict[str, np.ndarray]` stores arrays but has no record of which region was modified.
It cannot distinguish "painted 50 pixels" from "applied a filter to the full layer." Every undo
step has to restore the entire array, and there is no way to store a sparse delta. This design
forces full snapshots even for tiny edits.

Other memory problems:

- `Layer._pixels` is full `float32 RGBA`
- `Layer._source_pixels` duplicates it for non-destructive transforms
- Masks are separate full-resolution arrays
- Preview and filter workflows copy full layers
- Some operations allocate document-sized placement buffers even for small content
- Selection is a full-canvas float mask, not sparse
- There is no tile residency model, no mip chain, no compressed backing store, and no memory budget
  manager
- `float32` is 4 bytes per channel when `float16` (2 bytes/channel) suffices for all
  display-pipeline operations, halving memory bandwidth for every blend, adjustment, and mask
  operation

Brutally: the undo system is designed like a toy editor, not a production image engine.

---

## GPU Reality Check

This is not real GPU acceleration.

What exists:

- `CanvasView` uses `QOpenGLWidget` when available
- The final RGBA result is turned into a `QPixmap`
- Qt draws that pixmap with `QPainter`

What is missing for real GPU acceleration:

- No compute shaders
- No GPU-resident layer graph
- No persistent textures per layer or tile
- No GPU blend or composite kernels
- No async command buffers
- No zero-copy path from processing engine to presentation
- No Vulkan, Metal, DirectX, or OpenGL shader pipeline for adjustment or filter execution
- No GPU tile cache
- No GPU memory budget management
- No hybrid CPU/GPU scheduler

So the honest verdict is:

`CPU compositing + GPU blit != GPU-accelerated editor`

This architecture uses the GPU as a presentation layer, not as the image engine.

---

## Proposed Architecture

### 1. Core Processing Engine

Build a tile-based, lazy, non-destructive render graph.

Core principles:

- Use fixed-size tiles, e.g. `256x256` or `512x512`
- Every operation becomes a graph node: source image, transform, mask, adjustment, filter, style,
  blend, group, export
- Every node exposes:
  - `bounds()`
  - `dependencies()`
  - `version()`
  - `eval(tile_id, mip_level, context)`
- Evaluate only visible tiles and only the nodes needed for them
- Carry filter halos explicitly so blur or glow nodes request neighbor tiles without expanding
  whole-frame buffers
- Cache intermediate results per tile per node version

The document model should stop treating pixels as the document. The document should be a recipe.
Raster tiles are a cache.

**Node versioning must use a Merkle-style version chain.** A node's version is a hash of its own
parameter version plus the combined version of all its direct inputs. When input A changes, all
downstream nodes automatically have a new version and their cache entries become stale. This is how
the graph becomes correctly lazy without requiring explicit dirty-propagation calls.

Example pseudo-code:

```python
class RenderNode:
    def eval_tile(self, tile_id, mip, ctx) -> TileBuffer:
        raise NotImplementedError

class BlendNode(RenderNode):
    def __init__(self, base, over, mode, opacity, mask=None):
        self.base = base
        self.over = over
        self.mode = mode
        self.opacity = opacity
        self.mask = mask

    def version(self):
        return hash((self.mode, self.opacity, self.base.version(), self.over.version()))

    def eval_tile(self, tile_id, mip, ctx):
        key = (self.id, self.version(), tile_id, mip)
        if ctx.cache.has(key):
            return ctx.cache.get(key)

        base_tile = self.base.eval_tile(tile_id, mip, ctx)
        over_tile = self.over.eval_tile(tile_id, mip, ctx)
        mask_tile = self.mask.eval_tile(tile_id, mip, ctx) if self.mask else None

        out = ctx.device.blend(base_tile, over_tile, self.mode, self.opacity, mask_tile)
        ctx.cache.put(key, out)
        return out

class DocumentRenderer:
    def render_viewport(self, viewport, zoom):
        mip = choose_mip(zoom)
        visible_tiles = tiles_for_viewport(viewport, mip)
        for tile_id in priority_order(visible_tiles):
            schedule(root_node.eval_tile, tile_id, mip, ctx)
```

**Group subtree caching is critical for hierarchy performance.** A group node caches its composited
output tile per version. If no child in a group was modified, the group tile is returned from cache
without recursion. This changes group cost from `O(children * full-frame)` to `O(1)` for
unmodified groups.

### 2. GPU Acceleration Strategy — Phased Approach

The plan to jump directly to Rust+wgpu for the GPU backend is the correct final destination, but
the engineering path needs to be phased more carefully to deliver value sooner.

**Phase B bridge — Qt's QRhi before writing a custom GPU backend:**

Before building a fully custom Vulkan/Metal/DX12 compute pipeline, leverage Qt6's own `QRhi`
(Rendering Hardware Interface), which is already present in PySide6. `QRhi` provides cross-platform
compute shader dispatch on top of Vulkan, Metal, DirectX 11/12, and OpenGL. Since the app already
uses PySide6/Qt6, this is zero-cost to add and avoids writing a separate platform-abstraction
layer.

This means basic blend modes, mask application, and LUT-based adjustments can be moved to GPU
compute shaders via `QRhi` as part of Phase B, while the full Rust+wgpu engine is built for Phase
C. The tile result is kept in a `QRhiTexture` and presented directly to the canvas without CPU
readback, eliminating the `float32 → uint8 → QImage → QPixmap` conversion chain entirely.

**Longer-term — Rust + `wgpu` for the processing core:**

If the goal is Photoshop or Affinity class responsiveness, the engine has to become GPU-native for
the heavy path.

Recommended direction:

- Move the processing core to Rust with `wgpu`
- Use compute shaders for:
  - blend modes
  - masks
  - transforms
  - curves, levels, and LUT adjustments
  - blur, sharpen, and convolution
  - local filters
  - mip generation
- Keep tiles resident in GPU memory while editing
- Use async command submission and fence-based completion
- Composite directly into a presentation texture
- Avoid round-tripping through CPU float arrays unless needed for export or unsupported tools

Example pipeline:

```text
Decode image -> CPU staging tile cache
             -> upload dirty tiles to GPU texture atlas

For each frame:
1. determine visible tiles and required mip
2. build dependency list for dirty graph nodes
3. dispatch compute passes per node/tile
4. composite final visible tiles into framebuffer
5. present without CPU readback
```

What this fixes:

- No full-frame CPU recomposite on every brush move
- No `float32 -> uint8 -> QImage -> QPixmap` per interaction
- No repeated whole-document placement arrays
- Much better scaling with layer count

**Note: `wgpu-py` Python bindings have overhead. Do not use them for the hot path.** The Rust
library called from Python via `PyO3` is the correct architecture. The Python side only needs to
call into the Rust engine to submit commands (e.g., "composite this tile set") and receive opaque
handles. The Rust layer owns the GPU resources, command buffers, and sync primitives entirely.

### 3. Intermediate GPU Acceleration — CuPy and Numba

Before the Rust/wgpu engine exists, two Python-level GPU acceleration options are viable with
relatively low engineering cost:

**`CuPy`** — drop-in NumPy replacement that runs on CUDA. Blend mode functions, mask operations,
LUT-based adjustments, and mip generation can all be migrated to CuPy with minimal code change. The
primary cost is GPU memory allocation and CPU→GPU→CPU transfers. The correct approach is to keep
active layers on GPU memory during an editing session and only transfer at open/save/export time.

**`Numba @cuda.jit` and `@njit(parallel=True)`** — for CPU-heavy filters like OilPaint, Numba's
JIT compiler with `parallel=True` and `prange` instead of `range` can exploit all CPU cores
automatically. The OilPaint filter's nested `for y: for x:` loop is a perfect candidate for
`@numba.njit(parallel=True)` which would convert it from single-threaded Python to multi-core
native code with zero external dependencies. At 1080p this is likely a 30-100x speedup for that
specific filter.

These are tactical bridges, not permanent solutions. They let performance improvements ship during
Phase B while the Rust engine is built in Phase C.

### 4. Memory System

A professional memory model should be tile-centric, budgeted, and version-aware.

Use:

- CPU tile cache for source assets and fallback processing
- GPU tile cache for rendered and intermediate tiles
- LRU or segmented-LRU eviction by bytes, not entry count
- Mip pyramids for every raster source and rendered subtree
- Sparse residency semantics at the engine level even if the underlying API does not expose true
  sparse textures
- Undo as deltas:
  - changed tiles only
  - brush strokes as commands plus sparse tile snapshots
  - vector edits as parameter/history commands
  - transforms as metadata until rasterized

**Move the render pipeline to `float16` for all display-resolution operations:**

`float16` (2 bytes/channel) is sufficient precision for all blend modes, mask operations, and
adjustments in the display pipeline. This is not appropriate for 16-bit or 32-bit export paths, but
for the interactive viewport and all intermediate tiles, `float16` halves memory bandwidth. At
1080p, the compositor would work with 15.8 MiB buffers instead of 31.6 MiB, and every NumPy
operation would be twice as cache-friendly. Keep `float32` only for: 16-bit source layer storage,
export paths, and operations that explicitly require extra precision (HDR tone mapping, high-bit
depth adjustment layers).

Targets:

- No full-document history snapshots
- No full-resolution buffer per layer unless the layer is truly dense and fully materialized
- No repeated copies where views or ref-counted tile handles would work
- No `float32` in the display pipeline where `float16` suffices

### 5. Undo Architecture — Delta Tiles and Command Replay

The current `HistoryState` is fundamentally wrong:

```python
@dataclass
class HistoryState:
    name: str
    layer_data: dict[str, np.ndarray]  # full arrays for every modified layer
    metadata: dict[str, Any]
```

The replacement architecture has two parts:

**Command-based undo for structural operations** — all layer add/remove/reorder/rename/property
changes store only the command parameters and a reverse command. Zero pixel data is stored.
Reapplying just replays the commands. This is already partially the case (the `commands/`
architecture), but the history system doesn't exploit it — it still snapshots full pixel arrays.

**Tile-delta undo for pixel operations** — when a brush stroke, filter, or transform modifies
pixels, the undo entry stores only the before/after tiles for the affected region:

```python
@dataclass
class TileDelta:
    layer_id: str
    tile_ids: list[TileCoord]
    before_tiles: list[bytes]     # compressed tile data (zstd/lz4)
    after_tiles: list[bytes]

@dataclass
class HistoryEntry:
    name: str
    kind: Literal["command", "pixel_delta", "mixed"]
    command: Command | None
    pixel_deltas: list[TileDelta]
```

A 50px brush stroke on a 1080p canvas touches at most 4 tiles (each 256×256). Storing 4 tiles
instead of the full layer reduces undo memory by `(1920*1080) / (4*256*256) = ~8×` for that case.
With optional `zstd` compression on the tile data (which compresses well on image patches), the
ratio improves further.

For export-quality, the tile delta approach also enables non-destructive "undo to any point without
restoring" by replaying tile deltas forward/backward.

### 6. Multithreading — Real Cancellation and Job Isolation

The app currently has background rendering, but not a real compute scheduler.

You need:

- A job system with priorities and cancellation
- Tile tasks split across worker threads
- Dependency-aware execution for graph nodes
- Cooperative cancellation when a newer generation supersedes older work
- Separate queues for:
  - interactive viewport tiles
  - panel thumbnails
  - histograms
  - exports
  - idle background refinement

Critical rule:

**Obsolete work must stop, not merely be ignored after completion.**

The current scheduler discards old results via generation ID comparison in `_on_finished`, but the
in-flight `RenderWorker` continues executing. At 33ms intervals with a slow composite (say, 200ms),
there can be 6 stale renders in flight simultaneously, all burning CPU, all racing for the GIL.

The fix requires a cancellation token:

```python
class CancelToken:
    def __init__(self): self._cancelled = False
    def cancel(self): self._cancelled = True
    def is_cancelled(self): return self._cancelled

class RenderWorker(QRunnable):
    def run(self):
        for tile in self._tile_list:
            if self._cancel_token.is_cancelled():
                return
            self._render_tile(tile)
```

The tile loop checks the token at each tile boundary. This requires the compositor to be
tile-aware, which is Phase B work, but the infrastructure can be scaffolded in Phase A.

**Use a dedicated render thread pool, not Qt's global instance:**

`QThreadPool.globalInstance()` is shared with Qt internals. For CPU-intensive compositing, create a
dedicated `QThreadPool` with `setMaxThreadCount(cpu_count - 1)` so the UI thread always has at
least one core available.

**Document snapshot isolation for thread safety:**

The background render must operate on an immutable snapshot of the document, not the live object.
Two viable approaches:

1. **Copy-on-write (CoW) document** — when the render starts, the document increments its
   generation and the render works on the previous generation's data. Mutations to `Layer._pixels`
   create new arrays rather than modifying existing ones.

2. **Lightweight render snapshot** — before submitting the render job, the controller creates a
   `RenderSnapshot` that holds only the data the compositor needs: layer pixel references (not
   copies), positions, blend modes, opacities, masks, and adjustment params. The snapshot is
   immutable and safe to read from the worker thread. Layer pixel arrays are reference-counted;
   a write to any layer creates a new array and updates the reference.

Option 2 is easier to retrofit into the existing architecture.

### 7. Language Strategy

Keep in Python:

- UI
- tools orchestration
- menus, dialogs, shortcuts
- scripting and plugin surface
- document-level high-level commands

Move to Rust or C++:

- tile store
- render graph
- blend engine
- mask engine
- undo delta storage
- filter kernels
- transform engine
- mip generation
- task scheduler
- GPU backend abstraction

Recommended bridge:

- Rust + PyO3 for Python integration
- Expose opaque handles like `DocumentHandle`, `LayerHandle`, `TileHandle`
- Return lightweight metadata to Python
- Use zero-copy or borrowed array views only at explicit boundaries
- Keep NumPy interop for import/export and transitional filter migration

Incremental migration:

1. Replace history first — no render changes needed, immediate memory win
2. Replace compositor second — biggest interactive performance gain
3. Replace filter and adjustment execution third
4. Replace canvas presentation path fourth
5. Move remaining heavy tools last

---

## Migration Strategy

### Phase A — Critical Fixes (1–2 weeks, immediate impact)

These are bugs and architectural mistakes, not engineering trade-offs. They must be fixed before
any other work.

**A1. Remove `self._pipeline.invalidate()` from `render_worker.py`**

The worker calls `invalidate()` before every render, which destroys the uint8 cache and all tile
dirty state. Remove this call entirely. The worker should read the pipeline's current state, not
reset it. This is a one-line fix. Before landing it, ensure that the UI-side invalidation calls
(`ctx.invalidate(layer_id)` and `ctx.schedule_render()`) are correct and fired on every actual
document mutation.

**A2. Fix the document thread-safety race condition**

Before submitting a render job, take a lightweight snapshot of the document state:

```python
@dataclass(frozen=True)
class RenderSnapshot:
    layers: tuple[LayerSnapshot, ...]   # immutable view
    width: int
    height: int
    generation: int
```

Worker reads from snapshot; UI thread is free to mutate the live document.

**A3. Implement preview-resolution compositing**

The worker should composite at 50% or 25% of canvas dimensions during interaction and use full
resolution only for still frames (no input for 300ms). The correct implementation scales the layer
pixels (not the final result) using `cv2.INTER_AREA` downsampling before compositing. This reduces
float32 compositor work by 4× at half-res.

**A4. Fix the `_apply_filters_padded` unconditional copy**

Change:

```python
else:
    pixels = pixels.copy()    # wasteful
```

to:

```python
else:
    pass    # caller gets a view; only copy if mutation needed
```

Ensure downstream code never mutates returned pixels without copying first.

**A5. Cache the compositor pre-scan structures**

The six O(n) passes over `layers` at the start of `Compositor.composite()` should be cached as
`self._layer_topology` and invalidated only when the layer stack structure changes (add, remove,
reorder, reparent), not on every render. During normal interaction (paint, adjust params, move),
the topology does not change.

**A6. Rewrite OilPaint using vectorized NumPy or Numba**

The current `for y: for x:` pixel loop is a performance disaster. Replace it with:

```python
import numba

@numba.njit(parallel=True)
def _oil_paint_core(padded_rgb, padded_q, h, w, pad, levels):
    result = np.empty((h, w, 3), dtype=np.uint8)
    for y in numba.prange(h):      # parallel across rows
        for x in range(w):
            region_q = padded_q[y:y + 2*pad+1, x:x + 2*pad+1].ravel()
            # ... bin counting and averaging ...
    return result
```

Alternatively, implement the entire OilPaint kernel as a sliding-window integral image computation
using `cv2.boxFilter` per intensity bin — this is fully vectorized and requires no Python loop.

**A7. Cache vector layer rasterization results**

Every `Layer` of type `VECTOR` should store a `_rasterized_cache: np.ndarray | None` and a
`_rasterized_version: int`. The compositor uses the cache if the layer version is unchanged and
regenerates only when the vector scene has been modified.

**A8. Defer thumbnail generation strictly**

Panel thumbnail requests should never run during an active render. Use a `QTimer.singleShot(500,
generate_thumbnails)` deferred after the last render completes, not inline during the render path.

**A9. Add alpha presence flag to Layer**

Add `layer.has_alpha: bool` (or a bounding-box-of-non-transparent-pixels) updated at paint time.
Use this to skip the `np.any(over_a)` scan in `blend_region_inplace`. For a fully opaque layer,
this check is instantaneous instead of O(N).

Expected gain: **2x–5x** on common interaction with much less UI hitching.

---

### Phase B — Tiled CPU Engine and Partial GPU (4–8 weeks)

This is where the architecture starts becoming credible.

**B1. Implement true tile-based compositing for the viewport**

Replace `Compositor.composite()` with a tile-loop compositor:

```python
def composite_tile(self, stack, tile: TileCoord, mip: int) -> np.ndarray:
    tile_canvas = np.zeros((tile.h, tile.w, 4), dtype=np.float16)
    for layer in stack.visible_layers():
        if not layer.intersects(tile):
            continue    # skip layers entirely outside this tile
        layer_tile = layer.get_tile(tile.x, tile.y, mip)
        self._blend_tile_inplace(tile_canvas, layer_tile, layer)
    return tile_canvas
```

Each tile is composited independently and cached by `(tile_id, graph_version)`. Only tiles whose
upstream graph version changes are recomposited. For a brush stroke touching 2 tiles in a 20-layer
document, only 2 tiles × (layers that overlap those tiles) are recomposited.

**B2. Group subtree cache**

Cache `composite_tile(group, tile)` per `(group.version, tile_id)`. If the group contains 8 layers
but none were modified, the group tile costs one cache lookup.

**B3. Mip-level support for viewport**

Every raster layer computes mip levels `[1:1, 1:2, 1:4, 1:8]` on first load and stores them as
tile sets. The compositor uses the mip level that matches the current zoom ratio. At 25% zoom,
compositing runs at 1:4 resolution — 16× fewer pixels to process.

**B4. Add real cancellation tokens**

Each render generation carries a `CancelToken`. The tile loop checks it between tiles. When a new
render is requested, the previous token is cancelled. Old workers return early.

**B5. Move masks and adjustments to the tile evaluation path**

Adjustment layers evaluate their processor per-tile rather than per-full-frame. LUT-based
adjustments (curves, levels, color balance) are tile-independent and embarrassingly parallel.

**B6. QRhi compute shaders for blend modes**

Write GLSL/SPIR-V compute shaders for the five most common blend modes (Normal, Multiply, Screen,
Overlay, Soft Light). Dispatch one compute pass per tile per layer using `QRhiComputePipeline`.
This eliminates the NumPy blend cost for GPU-capable hardware. The CPU path remains as fallback.

**B7. Eliminate `_place_pixels` from the clipping chain**

Rework the clipping mask path to avoid full-canvas allocations. Clipping masks should be composited
at tile granularity: blend the clipped layer's tile into a scratch tile, apply the base layer's
alpha mask from the base tile, then blend the scratch tile into the canvas tile.

**B8. Introduce `float16` in the display pipeline**

Change the tile compositor to work in `float16`. Keep source layers in `float32` as the
authoritative representation, but downsample to `float16` for all compositor tile buffers. Profile
first to confirm the precision is acceptable for all 32 blend modes.

Expected gain: **5x–15x** on viewport responsiveness for multi-layer documents. Memory usage drops
significantly because whole-frame intermediates stop being the default.

---

### Phase C — Native Core (3–6 months)

This is the serious engine transition.

**C1. Build Rust core with PyO3**

Core modules to build first:
1. `TileStore` — LRU tile cache with byte-budget eviction and mip pyramids
2. `BlendEngine` — SIMD-accelerated blend kernels for all 32 modes, plus Porter-Duff variants
3. `HistoryStore` — tile-delta undo with `zstd` compression
4. `RenderGraph` — lazy node graph with Merkle version chains
5. `TaskScheduler` — priority work queue with cancellation and per-core worker threads

**C2. GPU compute backend via wgpu**

Implement blend modes, adjustments, and blur kernels as WGSL compute shaders. The Rust backend
owns all GPU resources (adapter, device, queue, texture atlases) and exposes a high-level API:

```rust
pub fn composite_tile(
    ctx: &mut RenderContext,
    tile_id: TileCoord,
    graph: &RenderGraph,
) -> GpuTileHandle;
```

Python calls `composite_tile` via PyO3 and gets back a handle. The handle references a GPU texture
that can be passed to Qt's `QRhiTexture` via external texture import (VkImage, MTLTexture,
D3D11Texture), enabling direct GPU→GPU presentation with zero CPU readback.

**C3. SIMD CPU kernels as fallback**

All blend mode functions have SIMD implementations using Rust's `std::simd` or `portable_simd`
(stable since Rust 1.75). On Intel, these compile to AVX2 256-bit vector operations processing 8
`float32` pixels per instruction.

**C4. Replace `QImage/QPixmap` round-trip with direct GPU presentation**

When the compositor's output is a GPU texture (Phase C), the canvas widget renders it directly via
a `QRhiGraphicsPipeline` (textured quad, no CPU readback). The `float32 → uint8 → QImage → QPixmap
→ QPainter` chain is eliminated entirely.

Expected gain: order-of-magnitude improvement on blend/filter-heavy scenes, especially above 4K
and above 20 layers.

---

### Phase D — Elite Tier

This is the level where the editor stops imitating Photoshop and starts competing with it.

**D1. Fully non-destructive node graph with live edits**

Every adjustment parameter change is a graph node parameter update. The graph evaluates only the
affected subtree for the affected tiles. Changing a Curves adjustment on layer 7 recomputes only
the tiles where layer 7 is visible, and only the nodes downstream of the Curves node.

**D2. Tile-local undo deltas and replayable procedural history**

Undo becomes `O(changed_tiles)` rather than `O(document_size)`. Brush strokes store their stroke
parameters and a before-snapshot of affected tiles. Re-applying a stroke from history replays the
stroke command without storing the after-pixels.

**D3. Background progressive refinement**

While the user is idle, the engine upgrades lower-mip-level tiles to full resolution in priority
order (viewport center first, edges last). The canvas shows a visually correct low-resolution
result immediately and refines to full quality within 100–500ms.

**D4. GPU-first brush engine with tiled splat accumulation**

Brush dabs are accumulated in a GPU scratch texture per stroke, not blended into the layer on each
dab. On stroke commit, the scratch texture is blended into the layer tile set using a compute pass.
This replaces the current per-dab full-rerender cycle with a single GPU composite per frame.

**D5. Multi-resolution caches for viewport and export**

The viewport shows mip-accurate tiles at the current zoom. Export renders at full resolution on
demand (potentially using the GPU for speed), reading from the same render graph as the viewport
but at full quality.

**D6. 100+ visible layers with real-time panning and zooming**

With tile-local compositing and group subtree caching, panning and zooming become O(visible_tiles)
operations rather than O(layer_count × canvas_area). At 25% zoom on a 1080p canvas, the
compositor works on a 480×270 equivalent with cached group tiles.

---

## Performance Expectations (Before vs After)

These are engineering estimates, not measured benchmarks.

### Before

- Single 1080p layer: acceptable only when mostly static and effect-free
- Single 1080p filtered layer during preview: easily sluggish due to full-layer copies,
  full-frame recomposite, and CPU conversions
- 10+ layers: interaction cost grows roughly linearly with layer count, but with large constants
  and repeated rescans, temp buffers, and stale worker waste
- Undo memory: potentially explosive because it scales with `layers * full-resolution buffers *
  history depth`

### After

- Phase A quick wins: smooth basic painting, transforms, and slider drags on 1080p and many 1440p
  documents
- Phase B tiled CPU engine: responsive viewport editing on 10–30 layers for common cases; memory
  usage reduced 2–5×
- Phase C GPU compute engine: real-time or near-real-time edits on 30–100+ layers depending on
  effect stack, viewport size, and VRAM budget
- Phase D full system: interactive performance on 100+ layers at 4K; undo memory reduced to
  touched-tiles-only (often 10–50× smaller than full snapshots)

### Complexity Comparison

- Current model: `render_cost ~= full_document_area * number_of_passes * layer_count`
- Target model: `render_cost ~= visible_tiles * dirty_subgraph_passes`

That is the architectural difference between a demo editor and a production editor.

---

## GPU Architecture — The Full Engineering Blueprint

This section is the detail that separates "we added some compute shaders" from an engine that
competes with Affinity Photo on GPU hardware. Each subsection maps to a specific engineering
decision that must be made correctly to reach maximum GPU throughput.

### The Honest Assessment of the Current GPU Plan

The previous GPU sections in this document are directionally correct but architected at the level
of a blog post, not an engineering spec. Saying "use wgpu and compute shaders for blend modes" is
like saying "use fast algorithms" — true, but not enough to ship a 60 fps editor at 4K with 100
layers. The following sections fill in every critical detail.

---

### GPU API Selection — The Real Trade-offs

The GPU API choice is the most consequential architectural decision in the entire engine. It locks
in portability, performance ceiling, maintenance cost, and future capability for years.

**Option A: wgpu (Rust) — Recommended primary path**

`wgpu` implements the WebGPU standard in Rust and translates to Vulkan, Metal, DX12, and OpenGL
transparently. It is what Bevy, Veloren, and other serious Rust graphics projects use.

Advantages:
- Single codebase runs on Vulkan/Metal/DX12 without platform branches
- Memory-safe, no raw pointer management
- Excellent ecosystem, active development
- WGSL shaders are readable, well-specified, and portable
- Future-proof: WebGPU is the web GPU standard, so the same code will work in a future web
  deployment with zero shader changes
- Overhead vs. raw Vulkan is typically 2–8% on modern hardware — irrelevant for image processing

Disadvantages:
- Cannot access GPU vendor-specific extensions directly (e.g., NVIDIA mesh shaders, AMD NGG)
- WGSL lacks some advanced features (cooperative matrices for ML)

**Option B: ash (raw Vulkan in Rust) — For elite-tier control**

`ash` gives you Vulkan 1.3 with the full extension ecosystem. If you need:
- Vulkan ray tracing (`VK_KHR_ray_tracing_pipeline`) for photorealistic layer styles
- Sparse textures (`VK_EXT_fragment_shader_interlock`) for very large canvases
- Cooperative matrices for GPU-accelerated ML inference
- Explicit timeline semaphores for zero-overhead GPU synchronization
- NV_shader_sm_builtins for warp-level intrinsics in shaders

...then `ash` is the answer. The cost is enormous complexity: you manage descriptor sets, render
passes, pipeline cache, memory barriers, and synchronization manually. Bugs are hard to find and
can cause GPU hangs or silent corruption.

**Option C: Dawn (Google's WebGPU implementation in C++)**

Dawn is what Chrome uses for WebGPU. It is production-quality, battle-hardened, and slightly lower
overhead than wgpu on some platforms. The disadvantage is that it is a C++ library, requiring
either a C FFI from Rust or a direct C++ integration. If the core is already in C++, Dawn is
worth considering.

**Decision: Start with wgpu, gate an `ash` (Vulkan) fast path behind a feature flag.**

The primary implementation is `wgpu` for correctness and portability. For the three highest-cost
operations (blend compositing, Gaussian blur, and HDR display), optionally use raw Vulkan extensions
when available. This way 95% of users get solid performance and you can optimize the remaining 5%
incrementally.

---

### GPU Memory Architecture — The Foundation Everything Else Depends On

Getting GPU memory management wrong destroys performance more than any shader optimization can
recover. Every Photoshop-class editor is built on explicit GPU memory management.

**Use VMA (Vulkan Memory Allocator) or equivalent:**

Raw `vkAllocateMemory` is the worst way to manage GPU memory. It is slow, limited (implementations
support only 4096 allocations on some hardware), and fragmentation-prone. VMA (open-source,
maintained by AMD) provides:
- Sub-allocation from large VRAM blocks (one `vkAllocateMemory` per 256 MiB block, sub-allocated
  with bump/slab allocators)
- Automatic selection of heap type (DEVICE_LOCAL, HOST_VISIBLE, etc.)
- Defragmentation passes
- Statistics and budget tracking

`wgpu` uses VMA internally. `ash` requires explicit VMA integration. Either way, VMA must be the
memory manager.

**VRAM-resident working set during an editing session:**

While a document is open and being edited, the entire layer tile set stays in VRAM. Tile eviction
to host memory only happens when the VRAM budget is exceeded (configurable, default 80% of
reported VRAM). This means:

```
Session open:   upload all layer tiles to GPU textures
During editing: only transfer *changed* tiles (staging buffer → GPU)
Session close:  GPU textures freed back to VMA pool
```

The upload cost at session open is acceptable (a few hundred milliseconds for a typical document).
All interaction from that point forward involves only delta transfers.

**GPU texture tile atlas:**

Do not allocate one `VkImage`/`MTLTexture` per layer tile. Instead, use a texture atlas — a few
large textures subdivided into tile slots. For `float16 RGBA` at 256×256 tiles:

- Each tile: `256 * 256 * 4 * 2 bytes = 524 KiB`
- Atlas of 1024 tiles: `512 MiB` (one `VkImage` with 1024 slots)
- This accommodates `~16 layers × 64 tiles per 1080p document` comfortably

Atlas management: maintain a free-list of tile slots. When a layer tile is loaded or computed, it
is assigned a slot from the free list. When evicted, the slot is returned.

**Staging buffer ring:**

For CPU→GPU uploads (when tiles are modified), use a persistent ring buffer allocated in
`HOST_VISIBLE | HOST_COHERENT` memory:

```
Ring buffer: 128 MiB (adjustable)
Write pointer advances per upload
GPU reads from ring; CPU writes to ring (no synchronization needed with timeline semaphores)
Wraps around when space is available (checked via GPU fence value)
```

This eliminates `malloc`/`free` for upload buffers and avoids GPU stalls during uploads.

---

### GPU Synchronization — Eliminating Stalls

GPU performance is destroyed by CPU–GPU synchronization points. Every `vkQueueWaitIdle` or
`glFinish` stops the GPU pipeline and throws away in-flight work. The correct synchronization
model for an image editor:

**Timeline semaphores (Vulkan 1.2+) / MTLFence (Metal):**

A timeline semaphore is a monotonically increasing counter. The GPU signals it after completing
work; the CPU waits on it only when it actually needs the result (e.g., readback for export). For
normal interactive rendering:

```
Frame N:   signal semaphore value 100 when compositing complete
Frame N+1: signal value 101; only wait on value 99 (two frames ago)
           → GPU is always 2 frames ahead; CPU never stalls
```

This model, used by modern game engines, means GPU and CPU work in parallel with a fixed latency
of 1–2 frames.

**Multi-queue execution:**

Modern GPUs expose multiple queue families:
- **Graphics/Compute queue**: blend passes, compositing, adjustments
- **Async compute queue** (NVIDIA Ampere+, AMD RDNA2+): runs compute shaders concurrently with
  graphics. While frame N's compositing runs on the graphics queue, the next frame's dirty tile
  evaluations can begin on the async compute queue.
- **Transfer queue**: DMA engine for host→GPU uploads. Runs entirely in parallel with both above.

For the editor, the transfer queue handles staging buffer uploads while the compute queue handles
compositing. On good hardware this means uploads for the next edit are pipelined with rendering the
current frame.

---

### GPU Compute Shader Design — What Actually Makes Shaders Fast

Writing a compute shader that "does blending" is straightforward. Writing one that achieves peak
GPU throughput requires knowing how the GPU hardware works.

**Workgroup sizing:**

The GPU processes threads in groups called warps (NVIDIA, 32 threads) or wavefronts (AMD, 64
threads). Your workgroup size must be a multiple of the hardware warp/wavefront size or you waste
execution lanes:

```wgsl
// WGSL compute shader
@compute @workgroup_size(16, 16, 1)   // 256 threads = 8 NVIDIA warps = 4 AMD wavefronts
fn blend_normal(@builtin(global_invocation_id) gid: vec3<u32>) {
    let pixel = gid.xy;
    ...
}
```

For blend modes working on 2D tiles:
- `@workgroup_size(16, 16)` = 256 threads — good balance for both NVIDIA and AMD
- Match tile size to workgroup size: 256×256 tiles processed as 16×16 blocks of 16×16 workgroups

**Half-precision (fp16) in shaders — 2× throughput on modern GPUs:**

NVIDIA RTX, AMD RDNA, and Apple M-series all execute `f16` operations at 2× the throughput of
`f32` (or 4× for AI accelerators). All blend operations, mask operations, and LUT-based adjustments
should run in `f16` inside the shader:

```wgsl
// Use f16 for intermediate blend computations
// (wgpu supports f16 via WGSL f16 extension on capable hardware)
let src_a: f16 = f16(src.a) * f16(opacity);
let inv_a: f16 = 1.0h - src_a;
let out_a: f16 = src_a + dst_a * inv_a;
```

Keep `f32` only for: accumulation in multi-pass filters (Gaussian blur with large radius, HDR
exposure), and the final presentation pass.

**Push constants for layer parameters:**

Adjustment parameters (curves LUT point, brightness/contrast values, hue rotation, levels min/max)
must go through push constants, not uniform buffers. Push constants are stored directly in command
buffer state — access is zero-latency with no descriptor set management:

```rust
// Rust side (wgpu)
render_pass.set_push_constants(
    wgpu::ShaderStages::COMPUTE,
    0,
    bytemuck::cast_slice(&[BrightnessContrastParams { brightness: 0.1, contrast: 0.5 }]),
);
```

For blend mode dispatch, the blend mode ID is a push constant, and the shader uses it to select
a code path — no separate shader variant per blend mode needed (the GPU's branch predictor handles
this efficiently when all tiles in a workgroup use the same mode).

**Bindless descriptors — bind all layers at once:**

Traditional rendering binds a descriptor set per layer (one `vkCmdBindDescriptorSets` per layer).
For 100 layers, this is 100 binding calls per tile per frame. With bindless descriptors (Vulkan
`VK_EXT_descriptor_indexing`, Metal argument buffers Tier 2):

```wgsl
// Bindless: all layer tiles bound at once, indexed by layer ID in push constants
@group(0) @binding(0) var tile_atlas: texture_2d_array<f16>;

@compute
fn composite(@builtin(global_invocation_id) gid: vec3<u32>) {
    let pixel = gid.xy;
    for (var layer_idx = 0u; layer_idx < push.layer_count; layer_idx++) {
        let layer_tile = textureLoad(tile_atlas, pixel, push.layer_slot[layer_idx], 0);
        // blend...
    }
}
```

This reduces CPU-side dispatch work from O(layers) to O(1) per tile, and keeps the GPU's shader
execution uninterrupted.

**Occupancy optimization:**

GPU occupancy = percentage of GPU hardware threads actively executing (vs. stalling on memory
or synchronization). Target 80–100% occupancy on the compositing shader:

- Keep register usage below 32 per thread (too many registers → fewer threads active)
- Use `@workgroup_size` that fills wavefronts completely
- Avoid branch divergence within a workgroup (all threads in a warp should take the same path)
  - For blend modes: if all layers in a tile use NORMAL mode (common), dispatch a specialized
    shader rather than the generic branch-heavy version

---

### Sparse Textures — Handling Very Large Canvases

For canvases above 4K × 4K (print documents, 100MP medium format), even a tile atlas strategy
requires more VRAM than most cards have. Sparse textures (Vulkan sparse residency, DX12 tiled
resources, Metal sparse textures) solve this:

- The texture is allocated at full size but no physical VRAM is committed
- Only resident tiles (those the compositor needs for the current viewport) are backed by real
  VRAM pages (64 KiB granularity on most hardware)
- Non-resident tiles return a predefined mip fallback value

For a 20,000 × 14,000 canvas, the total tile count is `~3,000` at 256×256. With sparse residency,
a 1080p viewport only needs `~240` resident tiles at any time. The rest stay on disk or in CPU RAM
until zoomed in or exported.

This is how professional RAW editors handle 100-megapixel files without needing 32 GB of VRAM.

---

### Zero-Copy GPU Presentation — Eliminating the Final Copy

The current chain is:
```
GPU texture → CPU readback → QImage → QPixmap → QPainter → screen
```

Even with `QRhi`, if the compositor output stays in GPU memory, the goal is:
```
GPU texture → platform texture interop → Qt swapchain → screen
```

The mechanisms:

**Vulkan + Qt (VK_KHR_external_memory):**

Qt6's `QVulkanWindow` or `QRhiSwapchain` can import a `VkImage` created by the compositor directly
into the Qt rendering pipeline. The compositor writes its output to this shared image. Qt's
presentation blit reads from it without any CPU copy.

```rust
// Rust: create a VkImage with VK_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_FD_BIT
// Share the file descriptor with the Qt process / same-process Qt renderer
// Qt imports the handle: QRhiTexture::createFrom(QRhiTexture::VkImage, { vk_image })
```

**Metal (macOS/iOS):**

`IOSurface` is the shared memory primitive on Apple platforms. The Rust Metal backend allocates an
`IOSurface`-backed `MTLTexture`. Qt's `QRhiTexture` on macOS accepts an `MTLTexture` pointer
directly. Same zero-copy story.

**DirectX 12 (Windows, optional):**

`wgpu`'s DX12 backend can share a `ID3D12Resource` as a shared handle. Qt 6.5+ supports DX12
texture interop via `QRhiTexture::createFrom`.

**Result:** the GPU writes compositor output directly to the texture that Qt presents to the
swapchain. Zero bytes cross the CPU. The only timing cost is the GPU→GPU copy implicit in Qt's
presentation blit (a single textured quad draw call), which is measured in microseconds.

---

### GPU Brush Engine — The Correct Architecture

The current brush engine stamps dabs in Python and triggers a full re-render per event. The GPU
brush engine architecture used by professional tools:

**Wet layer accumulation buffer:**

The brush stroke accumulates into a "wet layer" — a GPU texture the same size as the active tile
region being painted. Dabs are GPU compute dispatches, one per dab center, writing into the wet
layer:

```wgsl
@compute @workgroup_size(16, 16)
fn stamp_dab(
    @builtin(global_invocation_id) gid: vec3<u32>,
) {
    let pixel = vec2f(gid.xy) + push.dab_center;
    let dist = length(pixel - push.dab_center);
    let falloff = smoothstep(push.radius, 0.0, dist) * push.opacity;
    let existing = textureLoad(wet_layer, vec2i(gid.xy), 0);
    let blended = mix(existing, push.color, falloff * (1.0 - existing.a));
    textureStore(wet_layer, vec2i(gid.xy), blended);
}
```

**Stroke commit:**

When the stroke ends (mouse release), a single compute pass blends the wet layer into the actual
layer tile set. The wet layer is then cleared for the next stroke.

**Per-frame GPU composite, not per-dab:**

The canvas display always composites the finalized layer tiles PLUS the wet layer as an additional
overlay. The user sees every dab appear instantly (the wet layer is displayed every frame), but the
actual layer is only updated at stroke end. This means:

- No re-render of the full layer stack per dab
- Pressure curves evaluated on CPU once per dab, passed as push constants
- Brush texture is a GPU texture with mip levels — no per-dab CPU texture sampling
- Sub-pixel dab positions handled in the shader (no rasterization artifacts)

**Tablet pressure and tilt:**

Pressure → opacity mapping, size mapping, and tilt → direction mapping are all evaluated as GPU
LUT lookups (1D textures per curve), not CPU-side Python computations.

---

### GPU Histogram — Real-Time Without CPU Cost

The current histogram (for the Levels/Curves panels) is computed on the CPU from the composited
uint8 result. At 1080p, that is 2M pixels × 4 channels of CPU work, blocking the render thread.

The GPU histogram:

```wgsl
// Shared memory histogram accumulation
var<workgroup> local_hist: array<atomic<u32>, 256>;

@compute @workgroup_size(16, 16)
fn histogram_pass(@builtin(global_invocation_id) gid: vec3<u32>) {
    let pixel = textureLoad(composite_texture, vec2i(gid.xy), 0);
    let luma = u32(pixel.r * 0.2126 + pixel.g * 0.7152 + pixel.b * 0.0722) * 255u);
    atomicAdd(&local_hist[luma], 1u);
    workgroupBarrier();
    // merge local histogram into global output buffer...
}
```

The histogram pass runs as a separate compute dispatch on the GPU after compositing completes,
reading from the same texture the compositor wrote. The result (a 256-entry buffer) is read back
by the CPU only when the panel is visible. The GPU computation is pipelined with the next frame's
compositing — zero additional latency.

---

### GPU-Accelerated Adjustments — LUT3D and Per-Pixel Parallelism

Every adjustment (Curves, Levels, Hue/Saturation, Color Balance, etc.) is an embarrassingly
parallel per-pixel operation — the ideal GPU workload.

**LUT3D for complex adjustments:**

Rather than computing Curves, Hue/Saturation, and Color Balance separately, bake them into a
combined 3D lookup table (64×64×64 `float16` RGBA texture, = 3 MiB). The adjustment dialog
updates the LUT on the CPU side (fast for a 64³ table), uploads it once, and the compute shader
does a single trilinear interpolated texture lookup per pixel:

```wgsl
let adjusted = textureSampleLevel(lut3d, lut_sampler, vec3f(pixel.rgb), 0.0);
```

This replaces 3–5 separate adjustment passes with a single texture lookup. Photoshop and Affinity
both use this approach. The LUT covers arbitrary color correction with no per-pixel conditional
logic.

**Adjustment layer ordering with LUT chaining:**

Multiple adjustment layers can have their LUTs composed on the CPU (LUT3D → LUT3D composition via
CPU trilinear sampling, ~1ms for a 64³ table) and presented to the GPU as a single combined LUT.
This means 5 stacked adjustment layers cost the same GPU compute as 1.

---

### GPU Gaussian Blur — The Separable Shader Approach

Naive 2D Gaussian blur at radius R requires `(2R+1)²` texture samples per pixel. A separable
implementation runs two 1D passes (horizontal then vertical), costing `2*(2R+1)` samples per pixel
— quadratic to linear.

The GPU implementation runs both passes in compute shaders using shared memory:

```wgsl
// Horizontal pass: load a 256+2R row into shared memory, process 256 pixels
var<workgroup> row_cache: array<vec4f, 288>;  // 256 + 2*16 for R=16

@compute @workgroup_size(256, 1)
fn blur_horizontal(gid: vec3<u32>) {
    // cooperative load: threads load (256+2R) values into shared memory
    row_cache[gid.x + R] = textureLoad(input_tile, vec2i(gid.x, gid.y), 0);
    workgroupBarrier();
    // compute Gaussian sum from shared memory (no texture fetches in inner loop)
    var sum = vec4f(0.0);
    for (var k = -R; k <= R; k++) {
        sum += row_cache[gid.x + R + k] * gaussian_weight[k + R];
    }
    textureStore(output_tile, vec2i(gid.x, gid.y), sum);
}
```

Using shared memory, each pixel's kernel reads from L1 cache (~4 cycles) instead of global VRAM
(~200 cycles). For a 1080p layer with radius 20, this is the difference between 10ms and 0.3ms.

---

### ML/AI Acceleration — Tensor Cores and Future Operations

Modern GPUs have dedicated matrix multiplication hardware (NVIDIA Tensor Cores, AMD Matrix Cores,
Apple Neural Engine). This hardware accelerates:

- **Content-aware fill** (in-painting via diffusion models) — run fully on-device
- **AI-powered sharpening** (similar to Topaz Labs Sharpen AI) — ONNX model via ONNX Runtime GPU
- **Background removal** — semantic segmentation model
- **Noise reduction** (Lightroom-style) — CNN-based denoise

These should be `MLNode` types in the render graph. They take GPU tile input, dispatch a neural
inference pass, and output a GPU tile. The ONNX Runtime already supports Vulkan and CUDA backends.
The architecture should make these nodes first-class rather than bolted on later.

For Vulkan, the `VK_KHR_cooperative_matrix` extension exposes tensor operations directly. For the
near term, ONNX Runtime with its TensorRT/CUDA backend is the practical path.

---

### HDR and Wide Gamut Pipeline

To be truly future-proof, the color pipeline must be linear-light from source to display:

**Rendering in scene-linear light:**

All compositing should happen in linear `float16` (not gamma-encoded). The current sRGB uint8
pipeline has gamma encoding baked into the blending, which produces incorrect results for
transparency, gradients, and blending in non-normal modes. The correct pipeline:

```
Source pixel (sRGB encoded)
→ GPU sRGB decode (linearize, free via hardware sRGB texture format)
→ Linear-light compositing in f16 compute shaders
→ Tone mapping (if HDR output) or sRGB encode (if SDR output)
→ Present
```

Qt6's `QRhi` on Windows supports HDR10 output via `VK_EXT_swapchain_colorspace` and DX12's HDR
swapchain. On macOS, Metal supports EDR (Extended Dynamic Range). On Linux, Vulkan + KWin/Mutter
on Wayland supports HDR via the `VK_EXT_hdr_metadata` extension.

Exposing HDR output is a competitive differentiator. Affinity Photo 2 supports it. Photoshop
supports it on macOS.

---

### GPU Profiling Infrastructure — Mandatory from Day One

Performance improvements without measurement are guesswork. Build GPU profiling in from the start:

**GPU timestamp queries:**

Insert `vkCmdWriteTimestamp` (Vulkan) or Metal `MTLCommandBuffer.addScheduledHandler` at the
start and end of each major pass (tile upload, blend pass, adjustment pass, blur pass). Read these
back asynchronously (no GPU stall) and log them to a ring buffer accessible to the profiling panel.

**Statistics the profiling panel should show:**

- Tiles composited this frame (hit vs. miss)
- GPU time per pass (ms)
- VRAM resident (MiB, with budget indicator)
- Staging buffer utilization
- Frames per second with the render budget (33ms at 30fps, 16ms at 60fps)
- Cache hit rate for group subtrees

Without this instrumentation, GPU optimization is impossible. Build the infrastructure before
writing a single compute shader.

---

### Adaptive Quality System — The Key to "Always Fast"

The fastest GPU engine still can't composite 100 high-complexity layers at 60fps in every scenario.
Professional editors handle this with an adaptive quality system:

**Three rendering modes:**

1. **Interaction mode** (mouse/tablet actively moving): lowest quality that still looks correct
   - Half-resolution compositing upscaled via bilinear filter
   - Skip expensive blur/filter layers (show their cached results from the previous still frame)
   - Group subtree caches aggressively reused
   - Target: ≤8ms GPU time (120 fps equivalent)

2. **Preview mode** (brief pause, ≥100ms idle): medium quality
   - Full-resolution compositing
   - All adjustment layers evaluated at full precision
   - Group caches updated if stale
   - Target: ≤33ms GPU time (30 fps)

3. **Still mode** (≥500ms idle): full quality
   - Full-resolution at full precision
   - Progressive mip refinement (center tiles first)
   - All filters at full parameters
   - Background histograms and thumbnails updated
   - Target: ≤500ms total (acceptable for still frame)

This system is why Affinity Photo feels instant during brushing but takes a fraction of a second
to show the final quality result. The user perceives this as "smooth + accurate" rather than
"slow."

---

### Platform-Specific Optimizations

These are optional performance improvements on top of the unified architecture. They are not
required for correctness — the core engine runs everywhere without them.

**Windows (optional optimizations):**

- Use DX12 instead of Vulkan if the user has an older GPU (Intel HD Graphics 4000–6xx era where
  Vulkan support is poor or absent). DX12 should be the wgpu fallback after Vulkan.
- NVMe DirectStorage API for fast project loading — stream tile data from disk directly to GPU
  staging buffers, bypassing the CPU memory copy. Windows 11 + DX12 only.
- Windows HDR output via `VK_EXT_swapchain_colorspace` + DXGI HDR.

**macOS (optional optimizations):**

- Metal is the only GPU backend. wgpu's Metal backend is mature and production-quality.
- Apple M-series unified memory: `MTLBuffer` allocated as shared memory is accessible to both CPU
  and GPU without any transfer cost. The staging buffer → GPU upload step is free on M1/M2/M3/M4.
- Metal Performance Shaders (MPS) for Gaussian blur, histogram, morphological ops — hardware-
  tuned by Apple, faster than generic WGSL on Apple hardware. Optional fast path, same WGSL
  fallback.

**Linux (optional optimizations):**

- Wayland: `linux-dmabuf-v1` for zero-copy GPU texture presentation to the compositor.
- AMD RDNA2/3: async compute queue for pipelining tile evaluation with presentation.
- Mesa/Intel: validate against mesa-vulkan (lavapipe for software fallback CI testing).

---

### Future-Proofing Checklist

These are architectural decisions that, if made wrong today, require expensive rewrites later:

| Decision | Wrong approach | Correct approach |
|---|---|---|
| Color pipeline | sRGB gamma-encoded float32 | Linear-light f16, sRGB decode at source |
| GPU API surface | Direct QOpenGL calls | wgpu abstraction with Vulkan fast path |
| Memory management | Per-texture allocation | VMA with tile atlas slab allocator |
| Shader parameters | Uniform buffers per-draw | Push constants + bindless descriptors |
| Synchronization | vkQueueWaitIdle / glFinish | Timeline semaphores, 2-frame pipelining |
| Blend precision | float32 everywhere | f16 in shaders, f32 accumulation only |
| ML operations | CPU Python | ONNX Runtime GPU, first-class MLNode in graph |
| HDR output | 8-bit sRGB only | Wide gamut + HDR10/EDR output from day one |
| GPU profiling | None / ad hoc | Timestamp queries + stats panel from day one |
| Large canvas | Full VRAM residency | Sparse textures / virtual texturing |
| Brush engine | Per-dab CPU → rerender | Wet layer GPU accumulation buffer |
| History | Full snapshots | Tile deltas + zstd, GPU staging for undo replay |
| Render graph | Imperative compositor | Declarative node graph with Merkle versioning |

---

## Cross-Platform Architecture

The app must run on Windows, macOS, and Linux with full feature parity and comparable performance.
This is achievable without platform-specific code branches in the core engine, because every
technology choice in this plan was made with cross-platform first as a hard constraint.

This section defines the full cross-platform story from the GPU all the way to the Python package.

---

### The Unified GPU Stack

The entire GPU engine works on all three platforms through a single abstraction chain:

```
WGSL compute shaders   (one shader codebase, runs everywhere)
        ↓
     wgpu (Rust)        (translates WGSL to the native GPU API below)
        ↓
┌──────────────┬────────────────┬──────────────────┐
│   Windows    │     macOS      │      Linux       │
│  Vulkan 1.2  │     Metal      │   Vulkan 1.2     │
│  (primary)   │  (only option) │   (primary)      │
│  DX12        │                │   OpenGL 4.6     │
│  (fallback)  │                │   (fallback)     │
│  DX11        │                │                  │
│  (last resort│                │                  │
└──────────────┴────────────────┴──────────────────┘
```

**What this means in practice:**

- You write one set of WGSL shaders. wgpu compiles them to SPIR-V for Vulkan, MSL for Metal, and
  HLSL for DX12 automatically at build time or first launch.
- The Rust engine code is identical on all three platforms. No `#[cfg(target_os)]` branches in
  the hot path.
- The performance difference between platforms is hardware and driver quality, not code branches.

**macOS has no Vulkan — this is fine.** Apple deprecated OpenGL in 2018 and never adopted Vulkan.
wgpu's Metal backend is first-class and production-quality. On Apple Silicon (M1–M4), the GPU
performance is excellent. You do not need Vulkan to be fast on macOS.

---

### GPU Feature Detection and Fallback Hierarchy

Not every user has a GPU capable of the full feature set. The engine detects capabilities at
startup and silently degrades to the best available backend:

```
At startup: query wgpu adapter capabilities
    │
    ├─ Vulkan 1.2+ with compute?     → Full GPU path (Tier 1)
    ├─ Metal (macOS)?                → Full GPU path (Tier 1)
    ├─ DX12 (Windows)?               → Full GPU path (Tier 1)
    ├─ Vulkan 1.0 / OpenGL 4.3?      → Partial GPU: blending + LUT, no async compute (Tier 2)
    ├─ OpenGL 3.3?                   → Presentation only (Tier 3)
    └─ No GPU / software renderer?  → CPU-only (Tier 4, always available)
```

**Tier definitions:**

| Tier | What runs on GPU | What runs on CPU | Who this affects |
|------|-----------------|-----------------|-----------------|
| 1 | Everything: blend, adjust, filters, brush, histogram | Python orchestration only | All modern GPUs (2016+) |
| 2 | Blend modes, LUT adjustments, presentation | Filters (blur, distort, stylize), histogram | Old Vulkan hardware, some iGPUs |
| 3 | Presentation blit only | Full compositor | Very old GPUs, VMs, CI servers |
| 4 | Nothing | Full compositor (Rust SIMD) | Servers, CI, headless export |

**The Tier 4 CPU path is not a degraded experience — it uses Rust SIMD.**

The Rust CPU blend engine (`BlendEngine`) uses `std::simd` / `portable_simd` for AVX2 on x86/x64
and NEON on ARM. For a user with no GPU, the Tier 4 path still runs significantly faster than the
current Python/NumPy compositor. This is the export path for CI systems and headless servers.

**The fallback is automatic and transparent.** The Python UI does not need to know which tier is
active. The Rust engine exposes the same API regardless. The only difference is render time.

---

### Rust Cross-Compilation — The Native Core on All Platforms

The Rust core is compiled into a native Python extension module using `PyO3` + `maturin`. This
produces a platform-specific `.pyd` / `.so` / `.dylib` that Python imports like any other module.

**Build targets:**

| Platform | Rust target triple | Output |
|---|---|---|
| Windows x86-64 | `x86_64-pc-windows-msvc` | `photo_engine.pyd` |
| macOS x86-64 (Intel) | `x86_64-apple-darwin` | `photo_engine.so` |
| macOS ARM64 (Apple Silicon) | `aarch64-apple-darwin` | `photo_engine.so` |
| macOS Universal | `universal2-apple-darwin` | `photo_engine.so` (fat binary) |
| Linux x86-64 | `x86_64-unknown-linux-gnu` | `photo_engine.so` |
| Linux ARM64 | `aarch64-unknown-linux-gnu` | `photo_engine.so` |

**maturin** is the standard tool for building PyO3 extensions into Python wheels. It handles the
entire cross-compilation pipeline:

```bash
# Build for current platform
maturin build --release

# Build a universal macOS binary (Intel + Apple Silicon in one .so)
maturin build --release --target universal2-apple-darwin

# Build for Linux inside a manylinux Docker container (broadest compatibility)
docker run --rm -v $(pwd):/io ghcr.io/pyo3/maturin build --release
```

The resulting `.whl` files are uploaded to PyPI per-platform. Users `pip install` the app and get
the pre-built native extension for their platform — no Rust compiler needed.

**WGSL shaders are compiled at build time**, not at runtime. `wgpu` validates and translates WGSL
to the target backend's IR at compile time using `naga` (the wgpu shader compiler). The compiled
shader modules are embedded in the Rust binary as static byte arrays. First-launch GPU pipeline
compilation still occurs (SPIR-V → GPU driver binary), but this is cached to disk in a platform-
appropriate location:

```
Windows:  %APPDATA%\PhotoEditor\shader_cache\
macOS:    ~/Library/Caches/PhotoEditor/shader_cache/
Linux:    ~/.cache/PhotoEditor/shader_cache/
```

Subsequent launches skip shader compilation entirely.

---

### Qt / PySide6 Cross-Platform

PySide6 is cross-platform by design. Everything in the `ui/` package already works on all three
platforms without modification. Qt6 abstracts:

- Window management, DPI scaling, HiDPI retina displays
- Font rendering (DirectWrite on Windows, CoreText on macOS, FreeType on Linux)
- Native file dialogs, drag-and-drop, clipboard
- Input handling including tablet/stylus via `QTabletEvent` (works on all three platforms
  with Wacom, XP-Pen, Huion drivers)
- Dark mode detection (`QPalette` responds to OS dark mode on all platforms)

**Platform-specific Qt considerations:**

| Topic | Windows | macOS | Linux |
|---|---|---|---|
| HiDPI | Auto-scaled via Qt | Retina auto-handled | Set `QT_ENABLE_HIGHDPI_SCALING=1` |
| File paths | `os.path` / `pathlib` (`\` separator) | POSIX paths | POSIX paths |
| App data dir | `%APPDATA%` | `~/Library/Application Support` | `~/.local/share` or `$XDG_DATA_HOME` |
| Cache dir | `%LOCALAPPDATA%` | `~/Library/Caches` | `~/.cache` or `$XDG_CACHE_HOME` |
| Temp dir | `%TEMP%` | `/tmp` | `/tmp` or `$TMPDIR` |
| GPU context | Qt `QVulkanWindow` or `QRhiWidget` | Same (Metal backend) | Same (Vulkan or OpenGL) |

**Always use `platformdirs` (Python package) for data/cache/log paths.** Never hardcode OS-
specific paths. This is a one-line fix at the application layer:

```python
from platformdirs import user_cache_dir, user_data_dir
CACHE_DIR = Path(user_cache_dir("PhotoEditor"))
DATA_DIR  = Path(user_data_dir("PhotoEditor"))
```

---

### Python Packaging — Distributing to All Three Platforms

The distribution strategy must produce a working app with zero dependencies on the user's system
(no "install Rust", no "install Vulkan SDK", no "install Qt manually").

**Recommended: PyInstaller + maturin wheels**

The app is packaged as a standalone executable per platform using PyInstaller, which bundles:
- The Python interpreter
- All Python dependencies (PySide6, NumPy, OpenCV, Pillow, etc.)
- The compiled Rust extension (`photo_engine.pyd`/`.so`)
- The Qt plugins directory (PySide6 ships these)
- Any shader cache pre-warming assets

```
PyInstaller output:
  Windows:  PhotoEditor.exe  (+ DLLs in _internal/)  → packaged as .msi or NSIS installer
  macOS:    PhotoEditor.app  (universal2 bundle)      → packaged as .dmg
  Linux:    PhotoEditor      (ELF binary + libs)      → packaged as .AppImage or .deb/.rpm
```

**Linux AppImage** is the most portable Linux format — it runs on any distribution without
installation. For distro-specific packages, provide `.deb` (Debian/Ubuntu) and `.rpm`
(Fedora/RHEL) via GitHub Releases.

**No `pip install` required for end users.** The pip wheel (`photo_engine` or `basera-editor`)
is for developers and CI. End users get a native installer.

---

### CI/CD Matrix — Testing on All Three Platforms

Every PR must pass on all three platforms before merge. The GitHub Actions matrix:

```yaml
strategy:
  matrix:
    os: [windows-latest, macos-13, macos-14, ubuntu-22.04]
    # macos-13 = Intel, macos-14 = Apple Silicon (M1)

steps:
  - name: Build Rust extension
    run: maturin build --release

  - name: Run Python tests
    run: pytest tests/ -x --timeout=60

  - name: Run render correctness tests
    run: pytest tests/render/ --compare-screenshots

  - name: GPU smoke test (software renderer)
    run: python -m photo_editor --headless --self-test
    # uses wgpu's software rasterizer (vulkan-emulated via lavapipe/swiftshader)
    # validates GPU path works correctly even without real GPU in CI
```

**GPU in CI:** GitHub Actions runners do not have a discrete GPU. Use wgpu's software backend
(`wgpu::Backends::GL` with software rasterizer, or `WGPU_BACKEND=vulkan` with
`lavapipe`/`swiftshader`) to validate GPU code paths without real hardware. This catches shader
compilation errors, API misuse, and correctness bugs on all platforms.

**Render correctness testing:** The test suite maintains a set of reference images. Each CI run
composites the same test documents and compares pixel output to the reference. A tolerance of
±2/255 per channel accounts for minor floating-point differences across platforms.

---

### Shader Portability — One WGSL Codebase

WGSL (WebGPU Shading Language) is the shader language for `wgpu`. It compiles to:
- SPIR-V (Vulkan, Linux + Windows)
- MSL — Metal Shading Language (macOS)
- HLSL (DX12, Windows)

via `naga`, wgpu's built-in shader compiler. This means you write shaders once and they run on
all platforms without any platform conditional.

**Things WGSL does NOT support (important constraints):**

- No `f16` in vanilla WGSL — requires the `shader-f16` wgpu feature, which requires
  `VK_KHR_shader_float16_int8` (Vulkan) or Metal 3 (macOS 14+) or DX12 SM 6.2. Fallback to
  `f32` on older hardware/macOS.
- No bindless descriptors in base WGSL — requires `WGPU_FEATURE_SAMPLED_TEXTURE_AND_STORAGE_BUFFER_ARRAY_NON_UNIFORM_INDEXING`
- No cooperative matrices — Vulkan extension only, not available in wgpu WGSL yet

These features degrade gracefully: the shader compiles with `f32` fallback if `f16` is
unavailable; bindless degrades to per-pass descriptor binding; cooperative matrices are simply
not available in the WGSL path (ML acceleration would use ONNX Runtime instead).

---

### Dependency Compatibility Matrix

| Dependency | Windows | macOS | Linux | Notes |
|---|---|---|---|---|
| PySide6 6.7+ | ✅ | ✅ | ✅ | Pre-built wheels on PyPI |
| NumPy 2.x | ✅ | ✅ (ARM64) | ✅ | Pre-built wheels |
| OpenCV 4.x | ✅ | ✅ (ARM64) | ✅ | Pre-built `opencv-python-headless` |
| Pillow 10+ | ✅ | ✅ (ARM64) | ✅ | Pre-built wheels |
| Rust 1.75+ | ✅ (MSVC) | ✅ | ✅ | For building extension |
| maturin 1.x | ✅ | ✅ | ✅ | For building wheel |
| wgpu (Rust) | ✅ Vulkan/DX12 | ✅ Metal | ✅ Vulkan/GL | Bundled in Rust extension |
| Numba (Phase A) | ✅ | ✅ | ✅ | Pre-built wheels |
| platformdirs | ✅ | ✅ | ✅ | Pure Python |
| ONNX Runtime (Phase D) | ✅ GPU/CPU | ✅ CoreML | ✅ GPU/CPU | Optional, per-platform wheels |

---

### What Is Explicitly NOT Platform-Specific

To be explicit about what the core engine does NOT contain:

- No `#ifdef WIN32` or `if sys.platform == "win32"` in the render engine
- No Windows-only GPU API calls in the critical path
- No macOS-only Metal calls in the critical path
- No Linux-only Vulkan calls in the critical path

All platform divergence lives in exactly three places:
1. `wgpu` (handles the GPU API translation internally)
2. `platformdirs` (handles OS-specific directory paths)
3. The packaging scripts (PyInstaller spec files per platform)

The Python UI, Rust engine, WGSL shaders, and render graph are 100% shared across platforms.

---

This table resolves the execution priority across all phases. Items marked **CRITICAL** are bugs
that should be fixed before anything else.

| Priority | Item | Phase | Impact | Effort |
|----------|------|-------|--------|--------|
| 1 | Remove `invalidate()` from render worker | A | Enables all caching | 1 line |
| 2 | Fix document thread-safety race | A | Correctness | Low |
| 3 | Preview-resolution compositing | A | 4× interactive speedup | Low |
| 4 | Fix unconditional layer copy | A | Reduces memory traffic | Trivial |
| 5 | Cache compositor pre-scan topology | A | Removes per-frame O(n) scans | Low |
| 6 | OilPaint vectorization (Numba/njit parallel) | A | Unblocks large image usage | Low-Med |
| 7 | Vector layer rasterization cache | A | Eliminates repeated rasterization | Low |
| 8 | Layer alpha presence flag | A | Removes O(N) scan per blend | Low |
| 9 | Tile-based compositor + cancellation tokens | B | Core architecture shift | High |
| 10 | Group subtree cache (Merkle versioning) | B | O(n²) → O(1) for unchanged groups | Med |
| 11 | Mip-level viewport rendering | B | 16× faster at small zoom | Med |
| 12 | Tile-delta undo (zstd compressed) | B | 10–50× undo memory reduction | High |
| 13 | float16 display pipeline (CPU and shaders) | B | 2× memory bandwidth | Med |
| 14 | QRhi GPU presentation (zero-copy texture) | B | Eliminates float32→QPixmap chain | High |
| 15 | GPU profiling infrastructure (timestamps) | C-pre | Makes all optimization measurable | Med |
| 16 | Rust core: TileStore + BlendEngine + History | C | Foundation for GPU engine | Very High |
| 17 | VMA tile atlas + staging ring buffer | C | Correct GPU memory architecture | High |
| 18 | wgpu compute: blend modes + adjustments | C | Core GPU compositing | Very High |
| 19 | Bindless descriptors + push constants | C | Eliminates per-layer bind overhead | High |
| 20 | f16 GPU shaders + LUT3D for adjustments | C | 2× GPU throughput + adj. pipelining | High |
| 21 | Separable Gaussian blur (shared memory) | C | Quadratic → linear blur cost | Med |
| 22 | Zero-copy GPU presentation (platform interop) | C | Eliminates final CPU copy | High |
| 23 | Async compute queue + timeline semaphores | C | Pipelined GPU/CPU execution | High |
| 24 | GPU histogram (workgroup atomics) | C | Real-time histogram off CPU | Med |
| 25 | Adaptive quality system (3-mode rendering) | C | Always-fast perception | Med |
| 26 | Sparse texture residency for large canvases | D | 100MP+ document support | Very High |
| 27 | GPU brush engine (wet layer accumulation) | D | Real-time painting at 4K | High |
| 28 | Fully non-destructive node graph | D | Photoshop/Affinity parity | Very High |
| 29 | ONNX Runtime GPU for ML operations | D | AI-powered tools on-device | High |
| 30 | HDR/wide-gamut linear-light pipeline | D | Display future-proofing | High |

---

## Final Verdict

The current system is not fundamentally slow because Python is inherently unusable. It is slow
because the architecture still thinks in full images, full snapshots, full invalidations, and
CPU-side presentation buffers. Python then adds orchestration overhead on top of an already
expensive design.

The tile cache is mostly aspirational. The GPU acceleration is mostly cosmetic. The undo system is
extremely expensive. The compositor is too full-frame. The scheduler discards results but not
in-flight work. Some filters are outright non-scalable. And the single biggest active bug is that
the render worker actively destroys the cache it was supposed to use.

None of these are fundamental language limitations. They are design decisions that can be fixed
incrementally, starting with the Phase A items this week.

**Does this plan cover every performance problem?**

Phase A covers every active bug and every quick-win that has asymmetric impact-to-effort ratio.
Phase B and C cover the architectural shifts that define the performance ceiling. The GPU
Architecture section defines the exact engineering decisions that separate a "we use the GPU" story
from a GPU engine that outperforms Photoshop on modern hardware.

What this plan does NOT address (intentionally out of scope for now):

- Network / cloud rendering (distributed tile evaluation across machines)
- Procedural texture generation (GPU noise, voronoi, fractals as layer sources)
- Real-time collaborative editing (CRDT-based document model)
- Plugin sandboxing (running third-party filters in isolated GPU contexts)

These are valid extensions for after the core engine is solid. Adding them to an unstable core
produces a fast-but-broken system.

**What "fastest on the planet" actually requires:**

The app will not be faster than Affinity Photo by making better Python code. It will be faster by
building an engine with:

1. A GPU that never waits on the CPU (timeline semaphores + 2-frame pipelining)
2. A compositor that touches only pixels that changed (tile graph + Merkle versioning)
3. Shaders that run at hardware peak (f16, correct workgroup size, bindless, push constants)
4. Memory that never crosses PCIe needlessly (VRAM-resident working set + sparse textures)
5. A brush engine that accumulates strokes on the GPU instead of triggering CPU rerenders
6. An adaptive quality system that is always fast to the user, not always accurate

That is the full blueprint. Every item in the priority table above contributes to one or more of
these six properties. None of the items is optional if the goal is elite-tier performance.
