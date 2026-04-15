# Phase A — Critical Fixes: Implementation Report

## Overview

Phase A of the performance redesign addresses immediate architectural bugs and low-hanging
performance wins. All items target the CPU compositing path and require no new dependencies.

**Status:** Complete (all A1–A9 items implemented and tested)

---

## Changes by Item

### A1. Removed `self._pipeline.invalidate()` from `render_worker.py`

**Problem:** Every background render began by calling `invalidate()`, which destroyed the uint8
cache and all tile dirty state — making every cache and incremental mechanism useless.

**Fix:** Removed the `self._pipeline.invalidate()` call from `RenderWorker._do_render()`. The
pipeline's caches are now invalidated only by explicit UI-side calls (`ctx.invalidate()`,
`ctx.schedule_render()`), preserving tile and uint8 cache validity across renders.

**File:** `photo_editor/engine/renderer/render_worker.py`

---

### A2. Thread-safe document snapshots (`RenderSnapshot`)

**Problem:** The render worker read from the live `Document` while the UI thread could mutate it
concurrently, leading to race conditions (crashes, torn reads, stale composites).

**Fix:** Created an immutable `RenderSnapshot` dataclass that captures all compositing-relevant
layer state at enqueue time. Pixel arrays are shared by reference (zero-copy); metadata is frozen.
The scheduler creates a snapshot before submitting each job, and the worker reads exclusively from
the snapshot.

**New files:**
- `photo_editor/engine/renderer/render_snapshot.py` — `LayerSnapshot`, `RenderSnapshot`,
  `create_render_snapshot()`

**Modified files:**
- `photo_editor/engine/renderer/render_scheduler.py` — `_PendingJob` now carries a `snapshot`
  field; `enqueue_render()` and `enqueue_immediate()` create snapshots.
- `photo_editor/engine/render_pipeline.py` — `execute()` accepts an optional `snapshot` argument
  and delegates to `composite_snapshot()` when provided.
- `photo_editor/engine/compositor.py` — Added `composite_snapshot()` method and
  `_SnapshotStackAdapter` that makes a snapshot duck-type-compatible with `LayerStack`.
- `photo_editor/engine/renderer/render_worker.py` — Stores and forwards the snapshot.

---

### A3. Preview-resolution compositing

**Problem:** Interactive renders composited at full document resolution, wasting CPU on pixels the
user cannot distinguish at screen resolution.

**Fix:** Added `RenderPipeline.execute_at_scale()`. When the document exceeds the preview cap
(default 2048px), the worker computes a scale factor, downsamples each layer's pixels via
`cv2.INTER_AREA` before compositing, and upscales the final result to document size. At half-res
this reduces float32 work by roughly 4x.

**File:** `photo_editor/engine/render_pipeline.py` — `execute_at_scale()`
**File:** `photo_editor/engine/renderer/render_worker.py` — `_compute_preview_scale()` and
updated `_do_render()` to use the scaled path.

---

### A4. Restored protective copy in `_apply_filters_padded`

**Problem:** The original code unconditionally copied pixels before applying child
adjustment/filter layers, which was wasteful.

**Initial fix:** Removed the copy entirely (replaced with `pass`). This was too aggressive — when
no adjustment's `apply()` call reassigns the `pixels` variable, the subsequent
`np.clip(pixels, 0, 1, out=pixels)` would mutate the source layer's pixel array in-place.

**Final fix:** Restored the `pixels.copy()` in the no-padding branch. The copy only runs for
layers that have child adjustment/filter layers and no filter padding — a small subset. This is
the safe default; future optimization can track whether `apply()` returned a new array.

**File:** `photo_editor/engine/compositor.py` — `_apply_filters_padded()`

---

### A5. Compositor topology pre-scan

**Problem:** Six O(n) Python loops run at the top of `Compositor.composite()` on every render to
classify layers (visible, masks, adjustments, groups, etc.).

**Implementation:** Extracted the classification into a `_TopologyCache.build()` classmethod that
returns a frozen `_TopologyCache` dataclass.

**Important note on caching:** The original plan called for caching this topology and invalidating
only on structural changes. The initial implementation used a cache keyed on `(layer_ids, count)`,
but this caused a critical bug: the cache stored direct Python references to layer/snapshot
objects. On subsequent renders with different snapshots (e.g., after moving a layer), the cache
returned stale layer objects with old positions, causing the canvas to never update.

**Current state:** The topology is rebuilt on every `composite()` call via
`_TopologyCache.build(layers)`. The six O(n) scans total ~0.1ms for a typical 20-layer document,
which is negligible vs. the actual compositing work. The `invalidate_topology()` method is kept
as a no-op for API compatibility. A future optimization could cache only ID-based sets (not object
references) and rebuild object lists from the current layer input.

**File:** `photo_editor/engine/compositor.py` — `_TopologyCache` dataclass and `build()` method.

---

### A6. Vectorized OilPaint filter

**Problem:** The OilPaint filter used nested `for y: for x:` Python loops — a performance
disaster for anything beyond tiny images.

**Fix:** Rewrote using `cv2.boxFilter` per intensity bin and NumPy vectorized operations. The
inner loop is eliminated entirely. A 256x256 image processes in ~16ms (was hundreds of ms).

**File:** `photo_editor/filters/stylize/oil_paint.py` — `OilPaint.apply()`

---

### A7. Vector layer rasterization cache

**Problem:** Vector layers were re-rasterized on every render, even when nothing changed.

**Fix:** Added `_raster_cache` to `Layer` (a tuple of `(state_hash, pixels, position)`). Before
rasterizing, the rasterizer computes a hash of the vector layer's scene state. If the hash
matches the cache, the cached pixels and position are returned directly.

**Files:**
- `photo_editor/core/layer.py` — Added `_raster_cache` field.
- `photo_editor/vector/rasterizer.py` — Added `_compute_vector_state_hash()` and cache-check
  logic in `rasterize_vector_layer_tight()`.

---

### A8. Cancellation tokens for render jobs

**Problem:** When the user interacts rapidly (dragging, brushing), many render jobs queue up. Old
jobs run to completion even though their results will be discarded, wasting CPU time.

**Fix:** Created a `CancelToken` (thread-safe boolean with a lock) and `RenderCancelled`
exception. The scheduler cancels the previous token before starting a new job. The worker checks
the token after rendering and before emitting the result; if cancelled, it silently discards the
work.

**New file:** `photo_editor/engine/renderer/cancel_token.py` — `CancelToken`, `RenderCancelled`.

**Modified files:**
- `photo_editor/engine/renderer/render_scheduler.py` — Tracks `_active_cancel_token`; cancels
  it in `_run_worker()` before starting a new worker.
- `photo_editor/engine/renderer/render_worker.py` — Accepts and checks `cancel_token` in `run()`.

---

### A9. Alpha presence flag on Layer

**Problem:** `BlendingEngine.blend_region_inplace()` calls `np.any(over_a)` to detect fully
transparent regions — an O(N) scan on every blend call. For layers that are entirely transparent
(e.g., newly created empty layers), this is wasted work.

**Fix:** Added `Layer.has_alpha` — a lazily-computed boolean that checks whether the layer's alpha
channel contains any non-zero values. The flag is invalidated (`_has_alpha = None`) whenever
pixels are reassigned via the setter, and via `mark_alpha_dirty()` for tools that modify pixels
in-place (brush, eraser).

The compositor checks `layer.has_alpha` early in the compositing loop and skips layers with no
visible content entirely, avoiding all downstream processing (mask computation, blend calls, etc.).

**Files:**
- `photo_editor/core/layer.py` — `_has_alpha`, `has_alpha` property, `mark_alpha_dirty()`.
- `photo_editor/engine/compositor.py` — Early exit in `composite()` when `not layer.has_alpha`.
- `photo_editor/tools/brush.py` — Calls `mark_alpha_dirty()` after stamping.
- `photo_editor/tools/eraser.py` — Calls `mark_alpha_dirty()` after erasing.

---

## Bug Fix: Canvas Not Updating

After initial Phase A implementation, the canvas stopped reflecting changes (move, resize, etc.)
despite bounding boxes updating correctly.

**Root cause:** The topology cache (A5) stored direct Python references to `LayerSnapshot` objects.
When a new `RenderSnapshot` was created (with new `LayerSnapshot` objects at updated positions),
the cache key `(layer_ids, count)` still matched, so the compositor iterated over the OLD
snapshot's layer objects with stale positions and pixels.

**Fix:** Replaced the caching `_get_topology()` with a direct call to `_TopologyCache.build()`
on every composite. The topology rebuild cost is negligible (~0.1ms for 20 layers) compared to
the compositing work itself.

---

## Test Results

All 162 existing tests pass after Phase A changes. Additional manual tests verified:
- Position changes are reflected in composite output (topology no longer stale)
- Snapshot-based compositing produces correct results with changed positions
- `has_alpha` flag correctly tracks transparency state
- `CancelToken` cancellation works correctly
- OilPaint vectorized implementation matches expected output
