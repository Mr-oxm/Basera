# PhotoEditor Performance Optimizations

This document describes all performance optimizations implemented in the PhotoEditor application, including technical details, file locations, code changes, and rationale.

---

## Table of Contents

1. [Render Worker (Off-UI-Thread Compositing)](#1-render-worker-off-ui-thread-compositing)
2. [Render Scheduler (Debouncing & Throttling)](#2-render-scheduler-debouncing--throttling)
3. [Live Preview Fix](#3-live-preview-fix)
4. [Preview Pipeline (Optional Downsampling)](#4-preview-pipeline-optional-downsampling)
5. [Image Pool (Buffer Reuse)](#5-image-pool-buffer-reuse)
6. [Tile Processor (Parallel Filter Processing)](#6-tile-processor-parallel-filter-processing)
7. [Command System](#7-command-system)
8. [Async Save](#8-async-save)
9. [Deferred Panel Refresh](#9-deferred-panel-refresh)
10. [Render Pipeline Caching](#10-render-pipeline-caching)

---

## 1. Render Worker (Off-UI-Thread Compositing)

### Problem
Compositing (blending all layers into a single image) was running on the UI thread. For large documents or many layers, this blocked the main thread, causing the application to freeze during brush strokes, filter adjustments, and other interactive operations.

### Solution
Move compositing to a background thread using Qt's `QThreadPool` and `QRunnable`.

### Location
- `photo_editor/engine/renderer/render_worker.py`

### Implementation Details

**RenderCommand** — Immutable dataclass describing a render request:
- `document_width`, `document_height` — Target output size
- `preview_max_size` — Max dimension for downsampled preview (0 = full resolution)
- `full_resolution` — Whether to output full-res or downsampled

**RenderWorker** — `QRunnable` that:
1. Receives `RenderPipeline`, `Document`, `RenderCommand`, and `generation_id`
2. In `run()`: calls `_do_render()` which:
   - Invalidates the pipeline cache
   - Executes `pipeline.execute(document)` to composite layers
   - Converts float32 RGBA to uint8
   - Optionally downsamples if `preview_max_size > 0`
3. Emits `finished(rgba, generation_id, full_refresh)` or `error(message)` via signals
4. Uses `setAutoDelete(True)` so Qt cleans up after completion

**Signal flow:** Worker runs in thread pool → emits on completion → MainWindow's `_on_render_ready` updates canvas on the UI thread (Qt ensures signal delivery on correct thread).

### Result
The UI never blocks on compositing. Users can continue interacting while a render is in progress.

---

## 2. Render Scheduler (Debouncing & Throttling)

### Problem
Without throttling, every mouse move (brush, move tool, resize, rotate) or slider change would trigger an immediate render. At 60+ events/second, this caused:
- Hundreds of renders per second
- UI thread overload from scheduling
- Wasted work (intermediate frames never seen)

### Solution
A `RenderScheduler` that:
1. **Debounces** — Replaces pending requests with the latest; only one job runs per batch
2. **Throttles** — Limits render rate to ~30 FPS (33 ms interval) via `QTimer`
3. **Runs off UI thread** — Dispatches to `RenderWorker` via `QThreadPool`

### Location
- `photo_editor/engine/renderer/render_scheduler.py`

### Implementation Details

**State:**
- `_generation` — Incremented on each `enqueue_render()`; used for job identity
- `_last_shown_generation` — Highest generation_id we've displayed (see Live Preview Fix)
- `_pending` — `_PendingJob` (document, command, generation_id, full_refresh) waiting for timer
- `_timer` — Single-shot `QTimer` (33 ms default)

**enqueue_render(document, full_resolution, full_refresh):**
1. Increment `_generation`
2. Build `RenderCommand` from document dimensions
3. Store as `_pending` (replaces any previous pending job)
4. If timer not active, start it

**When timer fires (`_execute_pending`):**
1. Take `_pending`, clear it
2. Start `RenderWorker` with that job
3. Worker runs in thread pool; on completion, `_on_finished` is called

**enqueue_immediate(document, ...):**
- Skips debounce: stops timer, clears pending, runs worker immediately
- Used when a render is needed right away (e.g. before a modal operation)

### Integration
- `MainWindow._refresh()`, `_refresh_canvas_only()`, `_schedule_render()` all call `scheduler.enqueue_render()`
- `MainWindow` connects `scheduler.render_ready` → `_on_render_ready`, `render_error` → `_on_render_error`
- Controllers (canvas_ctrl, filter_ctrl, vector_ctrl, text_ctrl, gradient_ctrl) call `mw._schedule_render()` during interaction

### Result
Renders are limited to ~30 FPS. Rapid slider drags or brush strokes coalesce into a single render per 33 ms window.

---

## 3. Live Preview Fix

### Problem
After introducing the async render scheduler, live previews stopped working: brush strokes, move, resize, and rotate showed no visual feedback until the user released the mouse. The canvas appeared frozen during interaction.

### Root Cause
The scheduler's `_on_finished` discarded completed renders when `generation_id != self._generation`. During rapid interaction:
- Each mouse move calls `enqueue_render()` → `_generation` increments (e.g. 1, 2, 3, …)
- Timer fires, worker runs for the latest generation (e.g. 5)
- User moves again → `_generation` becomes 6, 7, 8…
- Worker for gen 5 completes → `5 != 8` → result discarded
- No frame ever displayed during continuous drag

### Solution
Change the discard logic: show the **latest completed result** we've seen, and only skip results **older** than what we've already shown.

### Location
- `photo_editor/engine/renderer/render_scheduler.py`

### Code Change

**Before:**
```python
def _on_finished(self, rgba: object, generation_id: int, full_refresh: bool) -> None:
    """Worker completed — emit only if result is not stale."""
    if generation_id == self._generation:
        self.render_ready.emit(rgba, generation_id, full_refresh)
```

**After:**
```python
_last_shown_generation = 0  # Added to __init__

def _on_finished(self, rgba: object, generation_id: int, full_refresh: bool) -> None:
    """Worker completed — emit if this is the newest result we've seen."""
    if generation_id >= self._last_shown_generation:
        self._last_shown_generation = generation_id
        self.render_ready.emit(rgba, generation_id, full_refresh)
```

### Rationale
- `generation_id >= _last_shown_generation` ensures we never show an older frame after a newer one (no visual "rewind")
- We always show the newest completed frame, so during interaction the user sees progressive updates
- Out-of-order completion (worker 3 finishes before worker 2) is handled: we only show if the result is newer than last shown

### Result
Live previews work for brush, move, resize, rotate, filters, and all interactive tools.

---

## 4. Preview Pipeline (Optional Downsampling)

### Problem
Rendering a 4K or 8K document at full resolution for every preview frame is expensive. For zoomed-out or panning views, a lower-resolution preview would be sufficient and much faster.

### Solution
`RenderWorker` supports optional downsampling: after compositing at full resolution, the result can be resized to a maximum dimension (e.g. 2048 px) for display. Export/save always uses full resolution.

### Location
- `photo_editor/engine/renderer/render_worker.py`

### Implementation Details

**RenderCommand.preview_max_size:**
- `0` — No downsampling; output full resolution (current default)
- `2048` — Downsample so the longest side is at most 2048 px

**_downsample_to_preview(rgba):**
- If image already fits within `preview_max_size`, return as-is
- Otherwise compute scale factor, resize using:
  - `cv2.resize(..., INTER_AREA)` if OpenCV available
  - `PIL.Image.resize(..., LANCZOS)` as fallback

**Current configuration:**
- `MainWindow` creates `RenderScheduler(preview_max_size=0)` — full resolution for now
- Can be set to `2048` when coordinate scaling (canvas ↔ document space) is implemented for downsampled previews

### Result
Infrastructure is in place for faster previews on large documents; currently disabled to preserve correct coordinate mapping.

---

## 5. Image Pool (Buffer Reuse)

### Problem
The compositor allocates temporary buffers (e.g. for placing mask grayscale, group masks) on every composite. At 30 FPS, this creates significant allocation churn and GC pressure, especially for large documents.

### Solution
An `ImagePool` that caches buffers by `(shape, dtype)`. Callers `acquire()` a buffer and `release()` it when done; the pool reuses buffers instead of allocating new ones.

### Location
- `photo_editor/engine/cache/image_pool.py`
- Used by: `RenderPipeline`, `Compositor`

### Implementation Details

**ImagePool:**
- `_pools: dict[(shape, dtype), deque[np.ndarray]]` — One deque per shape/dtype
- `_max_per_shape = 4` — Cap buffers per shape to avoid unbounded memory
- `_lock` — Thread-safe for worker + UI access

**acquire(shape, dtype):**
- Look up pool for (shape, dtype)
- If a buffer is available, pop and return it
- Otherwise return `np.empty(shape, dtype=dtype)`

**release(buf):**
- If pool for this shape/dtype has room, append buffer
- Otherwise let it be garbage-collected

**Compositor integration:**
- `Compositor.__init__(image_pool)` — Receives pool from `RenderPipeline`
- For standalone mask placement: `placed_gray = self._pool.acquire((height, width), dtype=np.float32)` … `self._pool.release(placed_gray)`
- For group mask placement: `placed_mask = self._pool.acquire(...)` … `self._pool.release(placed_mask)`
- If no pool provided, falls back to `np.zeros(...)` (no reuse)

**RenderPipeline:**
- Creates `ImagePool(max_buffers_per_shape=4)` and passes it to `Compositor`

### Result
Reduced allocation churn and GC pressure during interactive rendering. Common buffer sizes (e.g. document dimensions) stay "warm" in the pool.

---

## 6. Tile Processor (Parallel Filter Processing)

### Problem
Filters and adjustments (blur, brightness, etc.) process the entire image on a single thread. For large images, this can be slow and underutilizes multi-core CPUs.

### Solution
A `process_tiled()` function that splits an image into tiles (default 256×256), processes each tile in parallel via `ThreadPoolExecutor`, and reassembles the result.

### Location
- `photo_editor/core/image/tile_processor.py`

### Implementation Details

**process_tiled(image, func, tile_size=256, max_workers=None):**
- Splits image into non-overlapping tiles
- For each tile: `func(tile)` must return processed tile (no in-place modification)
- Submits all tiles to `ThreadPoolExecutor`
- As each future completes, writes the result into the correct region of the output array
- Returns the full processed image

**Design:**
- Tiles are independent; no cross-tile dependencies
- Suitable for point-wise or local operations (blur needs padding; caller must handle)
- `max_workers=None` uses default thread count

### Status
- **Implemented and tested** (`tests/test_tile_processor.py`)
- **Not yet wired** into adjustment/filter layers — infrastructure ready for when filters are refactored to use it

### Result
Ready for parallel filter execution; will reduce filter latency on multi-core systems once integrated.

---

## 7. Command System

### Problem
UI code was tightly coupled to document mutations. Undo/redo, testing, and consistent behavior across different entry points (menus, shortcuts, drag-drop) were difficult.

### Solution
A command pattern: UI emits `Command` objects; `MainWindow.execute_command()` runs them on the document and triggers refresh. Commands integrate with document history for undo/redo.

### Location
- `photo_editor/commands/` — Base and subpackages
- `photo_editor/commands/base.py` — `Command` ABC
- `photo_editor/commands/layer/` — Add, Remove, Duplicate, Merge, Move, Reorder, etc.
- `photo_editor/commands/mask/` — Add, Apply, Invert, Convert, Attach
- `photo_editor/commands/effect/` — UpdateEffect, AttachAdjustment
- `photo_editor/commands/document/` — PlaceImage, SaveDocument

### Implementation Details

**Command interface:**
```python
class Command(ABC):
    @abstractmethod
    def execute(self, document: Document) -> object: ...
```

**MainWindow.execute_command(command):**
1. `result = command.execute(self._doc)`
2. `self._pipeline.invalidate()`
3. `self._refresh()`
4. Return result

**MainWindow.execute_command_async(command, on_success, on_error):**
- Runs `command.execute(doc)` in a worker via `Worker.run_async()`
- Callbacks run on main thread for UI updates

**Controllers** (layer_ctrl, filter_ctrl, document_ctrl, drop_ctrl) create and execute commands instead of mutating the document directly.

### Result
Decoupled UI from engine; consistent undo/redo; easier testing; single code path for all mutation operations.

---

## 8. Async Save

### Problem
Saving a document involves a full composite plus disk I/O. On the UI thread, this freezes the application for large documents.

### Solution
Run the save operation in a background worker. The UI remains responsive; on success, the document is marked clean and the window title/status are updated.

### Location
- `photo_editor/commands/document/save_document.py` — `SaveDocumentCommand`
- `photo_editor/ui/controllers/document_ctrl.py` — `_save_to()` uses `execute_command_async`
- `photo_editor/utils/worker.py` — Generic `Worker` for off-thread execution

### Implementation Details

**SaveDocumentCommand:**
- `execute(document)`:
  1. `merged = self._pipeline.execute(document)` — Full composite
  2. `save_image(merged, self.path)` — Write to disk
- Takes `path` and `pipeline` in constructor (pipeline holds compositor state)

**DocumentController._save_to(path):**
- Creates `SaveDocumentCommand(path, mw._pipeline)`
- Calls `mw.execute_command_async(command, on_success=..., on_error=...)`
- `on_success`: `mark_clean()`, update window title, tab text, status bar
- `on_error`: Show `QMessageBox` with error

**Worker.run_async(fn, on_result, on_error):**
- Wraps `fn` in a `QRunnable`
- Runs in `QThreadPool.globalInstance()`
- Emits `result` or `error`; Qt delivers to main thread for callbacks

### Result
Save no longer blocks the UI. Users can continue working (or at least see a responsive interface) while a large file is being written.

---

## 9. Deferred Panel Refresh

### Problem
During interactive operations (e.g. dragging a filter slider), the layers panel, history panel, and other panels were refreshed on every change. Rebuilding panel UI dozens of times per second caused lag and visual flicker.

### Solution
Throttle panel refreshes to ~5 FPS using a single-shot timer. Multiple refresh requests coalesce into one actual refresh.

### Location
- `photo_editor/ui/main_window.py`

### Implementation Details

**State:**
- `_panel_refresh_timer` — `QTimer`, 200 ms interval, single-shot
- `_panel_refresh_pending` — Whether a refresh has been requested

**_schedule_panel_refresh():**
- If not already pending, set `_panel_refresh_pending = True` and start timer
- Called from `canvas_ctrl.on_release`, layer operations, etc.

**_do_deferred_panel_refresh():**
- Called when timer fires
- Sets `_panel_refresh_pending = False`
- Calls `_layers_panel.refresh(self._doc, thumbnails=False)` (and similar for other panels as needed)
- `thumbnails=False` skips expensive thumbnail generation during rapid updates

### Result
Panel updates are limited to ~5 FPS during interaction, reducing UI thrashing while still keeping panels reasonably up to date.

---

## 10. Render Pipeline Caching

### Problem
Repeated calls to render the same document (e.g. for panel sync, selection overlay) were recomputing the full composite and float→uint8 conversion every time.

### Solution
Cache the uint8 result. When `execute_to_uint8()` is called and nothing has been invalidated, return the cached buffer. Invalidation happens when layers, masks, or document dimensions change.

### Location
- `photo_editor/engine/render_pipeline.py`

### Implementation Details

**State:**
- `_result_uint8` — Cached uint8 RGBA output
- `_uint8_valid` — Whether cache is current
- `_uint8_buf` — Pre-allocated buffer for conversion (avoids allocating on every composite)

**execute_to_uint8(document):**
- If `_uint8_valid` and `_result_uint8` is not None, return `_result_uint8`
- Otherwise: `result = execute(document)`, convert to uint8 using `_uint8_buf`, set `_uint8_valid = True`, return

**invalidate(layer_id=None):**
- Sets `_uint8_valid = False`
- Invalidates `TileCache` (for future tile-based incremental render)

**TileCache:**
- Tracks dirty tiles for incremental re-render
- `invalidate_region()` / `invalidate_all()` mark tiles dirty
- Full tile-based execute is not yet implemented; cache helps for sync path (e.g. `_refresh` with cache hit)

### Result
Repeated reads of the same frame (e.g. overlay updates, panel thumbnails) avoid recompositing when the document hasn't changed.

---

## Summary Table

| Optimization | Target Problem | Status | Files |
|-------------|----------------|--------|-------|
| Render Worker | UI thread blocking on composite | ✅ Done | `renderer/render_worker.py` |
| Render Scheduler | Too many renders, no throttling | ✅ Done | `renderer/render_scheduler.py` |
| Live Preview Fix | No feedback during interaction | ✅ Done | `render_scheduler.py` |
| Preview Downsampling | Slow preview on large docs | ✅ Ready (disabled) | `render_worker.py` |
| Image Pool | Buffer allocation churn | ✅ Done | `cache/image_pool.py`, `compositor.py` |
| Tile Processor | Single-threaded filters | ✅ Ready (not wired) | `core/image/tile_processor.py` |
| Command System | Tight coupling, no undo consistency | ✅ Done | `commands/` |
| Async Save | Save blocks UI | ✅ Done | `commands/document/`, `document_ctrl.py` |
| Deferred Panel Refresh | Panel thrashing | ✅ Done | `main_window.py` |
| Pipeline Caching | Redundant composites | ✅ Done | `render_pipeline.py` |

---

## Testing

Run the test suite:
```bash
uv run pytest tests/ -v
```

Relevant tests:
- `tests/test_render_worker.py` — RenderWorker, RenderScheduler
- `tests/test_image_pool.py` — ImagePool acquire/release
- `tests/test_tile_processor.py` — process_tiled
- `tests/test_commands.py` — Command execution
- `tests/test_main_window_smoke.py` — MainWindow launch
