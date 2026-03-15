# Performance Remediation Log

This document records the concrete performance fixes applied after the earlier optimization pass, why they were needed, and what remains structurally unresolved.

## Goals

- Reduce runaway memory usage during interaction.
- Make single-layer move and other interactive operations feel immediate on large documents.
- Keep document-space overlays correct while enabling cheaper preview rendering.

## Implemented Fixes

### 1. Single-flight render scheduling

Files:
- `photo_editor/engine/renderer/render_scheduler.py`

Problem:
- The scheduler debounced pending jobs, but it still allowed multiple render workers to run concurrently.
- On 4K documents, rapid drags could spawn several full renders in parallel, multiplying memory usage and making visible updates arrive late.

Fix:
- Added `_in_flight` tracking.
- While a worker is running, new requests only replace `_pending`.
- When the worker finishes or errors, the latest pending request is executed.

Effect:
- At most one render worker is active at a time.
- Intermediate drag states are dropped; the most recent state wins.

### 2. Stop invalidating the pipeline inside every worker

Files:
- `photo_editor/engine/renderer/render_worker.py`

Problem:
- The render worker invalidated the entire pipeline before every render.
- That defeated existing cached uint8 conversion behavior and prevented reuse of valid pipeline state.

Fix:
- The worker now uses `RenderPipeline.execute_to_uint8()` directly.
- Invalidation remains controlled by the UI paths that know what changed.

Effect:
- Fewer unnecessary full-path recomputes and fewer temporary conversion buffers.

### 3. Lightweight metadata-only history snapshots

Files:
- `photo_editor/core/document.py`

Problem:
- The history system deep-copied all layer pixel buffers, masks, selection mask, and non-destructive source buffers for every snapshot.
- Metadata-only operations such as plain layer translation paid the same memory cost as destructive pixel edits.

Fix:
- Added `save_metadata_snapshot(action)`.
- Added `_snapshot(..., include_pixels=False)` support.
- Metadata-only states store layer structure and geometry without copying pixels.
- Restore logic preserves current pixel buffers when replaying metadata-only states.

Effect:
- Move and alignment operations no longer clone all raster data just to preserve undo.

### 4. Move tool no longer snapshots or initializes ND state for plain translation

Files:
- `photo_editor/tools/move/move_tool.py`
- `photo_editor/tools/move/align_ops.py`

Problem:
- The move tool created a full snapshot at press time.
- It also initialized non-destructive source buffers in paths that only needed translation.

Fix:
- Plain move now saves one lightweight pre-move snapshot on the first real drag delta.
- Resize and rotate still use the full snapshot path.
- Non-destructive source initialization is now limited to resize/rotate flows.
- Alignment helpers now use metadata-only snapshots.

Effect:
- Large raster layers can be moved without immediately duplicating their pixel data in history and ND state.

### 5. Proxy preview rendering with preserved document-space mapping

Files:
- `photo_editor/ui/canvas_view.py`
- `photo_editor/ui/main_window.py`

Problem:
- Interactive rendering stayed full-resolution because the canvas used the rendered image dimensions as the document dimensions.
- Downsampling the preview would have broken hit-testing, rulers, overlays, and transform boxes.

Fix:
- `CanvasView.set_image()` now accepts an optional `document_size`.
- The displayed pixmap can be a smaller preview while canvas coordinate math still uses full document width/height.
- `MainWindow` now passes the real document size when setting the canvas image.
- Interactive scheduler preview size is enabled at `2048` px max dimension.

Effect:
- Large documents render faster during interaction while overlays remain correct in document space.

### 6. Idle full-resolution follow-up render

Files:
- `photo_editor/ui/main_window.py`

Problem:
- Proxy preview alone improves responsiveness but leaves the final on-screen image downsampled until the next action.

Fix:
- Added a short idle timer.
- Interactive refreshes schedule a full-resolution render after input activity settles.
- The full-res render goes through the same single-flight scheduler, so it cannot pile up behind multiple concurrent jobs.

Effect:
- The user sees fast preview updates during drag and a sharper final image shortly after interaction stops.

### 7. Viewport-aware preview budgeting

Files:
- `photo_editor/ui/main_window.py`
- `photo_editor/engine/renderer/render_scheduler.py`

Problem:
- A fixed preview budget still wastes work when the viewport is much smaller than the document.
- If the canvas can only display roughly 600 px on its longest side, rendering a 2048 px preview does not improve interaction quality.

Fix:
- Interactive preview budget is now derived from the canvas viewport and device pixel ratio.
- `MainWindow` updates the scheduler preview budget before interactive renders.
- The preview budget is clamped between `512` and `2048` px.

Effect:
- Zoomed-out interaction uses only as many pixels as the viewport can meaningfully show.
- This reduces preview render cost further on large documents.

### 8. Remove side-panel refreshes from the per-frame render callback

Files:
- `photo_editor/ui/main_window.py`

Problem:
- The render-ready callback refreshed `TransformPanel` and `ChannelsPanel` on every completed frame.
- `ChannelsPanel` in particular can regenerate thumbnails, adding UI-thread work during drag.

Fix:
- The render callback now updates only the canvas, overlays, scrollbars, and rulers for normal interactive frames.
- Transform and channel panels are refreshed only on full-refresh paths or through the existing deferred panel refresh timer.

Effect:
- Less UI-thread churn during rapid interaction.
- Better chance that the rendered frame is shown immediately instead of being delayed behind panel work.

### 9. Conservative dirty-tile recomposition in the render pipeline

Files:
- `photo_editor/engine/render_pipeline.py`
- `photo_editor/engine/compositor.py`
- `photo_editor/ui/main_window.py`

Problem:
- The engine still recomposited the full document even when a brush stroke only touched a small area.
- The earlier tile cache only tracked dirty tiles; it did not drive real partial recomposition.

Fix:
- Added cached float-frame storage in `RenderPipeline`.
- Added real tile invalidation consumption via `invalidate_region(...)`.
- Added a conservative `Compositor.composite_region(...)` path for simple root-level raster stacks.
- `MainWindow` now consumes `Document.consume_dirty_region()` and routes that region into the pipeline instead of blanket invalidation.
- Complex documents still fall back to full recomposition automatically.

Effect:
- Brush-like edits on simple raster documents now recompose only the dirty tiles.
- Complex layer stacks keep existing correctness because they still use full renders.

### 11. Region compositing now covers complex layer stacks

Files:
- `photo_editor/engine/compositor.py`

Problem:
- The first incremental renderer only handled flat root-level raster stacks.
- Any document using groups, masks, adjustment layers, filter layers, or clipping still fell back to full-document compositing.

Fix:
- Refactored the compositor to render against an origin-offset canvas, not only the full document origin.
- Region compositing now reuses the same composition logic for groups, standalone masks, attached masks, child adjustments/filters, `clips_parent`, and `clipping_mask` flows.
- Root-level filters get extra padding before the final crop so neighborhood-based effects remain correct at dirty-tile boundaries.

Effect:
- Dirty-region redraw is no longer limited to the trivial flat-raster case.
- Complex layer stacks can now use incremental redraw while matching full-composite output.

### 10. Tile-patch undo for destructive tools

Files:
- `photo_editor/core/document.py`
- `photo_editor/tools/tool_base.py`
- `photo_editor/tools/brush.py`
- `photo_editor/tools/eraser.py`
- `photo_editor/tools/clone_stamp.py`
- `photo_editor/tools/healing_brush.py`
- `photo_editor/tools/paint_bucket.py`
- `photo_editor/tools/gradient_tool.py`

Problem:
- Destructive tools still stored full-image snapshots for undo, which is the main remaining memory spike during painting workflows.

Fix:
- Added tile-patch capture APIs to `Document`.
- Added pending dirty-region aggregation to the document model.
- Destructive tools now capture only the tiles they are about to modify.
- Brush, eraser, clone stamp, healing brush, and bucket capture bounded regions; gradient captures the whole target layer once because its edit domain is the full surface.

Effect:
- Undo for destructive raster edits no longer duplicates the entire document state.
- Dirty regions produced during those edits feed directly into the incremental render path.

### 12. Gradient edits now capture only changed tiles

Files:
- `photo_editor/core/document.py`
- `photo_editor/tools/gradient_tool.py`

Problem:
- Gradient creation and handle edits were still treated as full-layer patch captures.
- That was especially wasteful for wide layers where only a subset of tiles actually changed between the previous and new gradient state.

Fix:
- Added `Document.capture_layer_tile_pixels(...)` so history can capture tile data from an explicit pre-edit pixel buffer.
- Gradient create/handle-edit flows now compute the final or previous gradient result first, compare tile-by-tile, and only store the tiles whose pixels actually differ.
- Full-layer patch capture on gradient press was removed.

Effect:
- Gradient history entries scale with changed tiles instead of layer size.
- Handle edits remain undoable without defaulting to whole-layer history copies.

### 13. Move, transform, and structural edits now publish exact dirty bounds

Files:
- `photo_editor/core/document.py`
- `photo_editor/tools/move/move_tool.py`
- `photo_editor/commands/layer/move_layer.py`
- `photo_editor/commands/layer/resize_layer.py`
- `photo_editor/commands/layer/rotate_layer.py`
- `photo_editor/ui/panels/transform_panel.py`
- `photo_editor/ui/main_window.py`

Problem:
- Several non-paint workflows still bypassed the dirty-region renderer.
- Move drags, transform-panel edits, and structural reparenting were still capable of forcing broader invalidation than their visible footprint required.

Fix:
- Added document-level helpers to compute visual bounds for layers and related child or mask content.
- Move, resize, and rotate flows now mark the union of their pre-edit and post-edit bounds.
- Layer reparenting, resize, rotate, and transform-panel translation or shear now emit precise dirty regions.
- `MainWindow.execute_command()` no longer pre-invalidates the whole pipeline before `_refresh()` can consume a pending dirty region.

Effect:
- Interactive transforms now stay on the incremental redraw path when their visual impact is localized.
- Structural reparenting no longer needs to default to whole-document invalidation.

### 14. Gradient fill now respects actual image shape instead of layer rectangle

Files:
- `photo_editor/tools/gradient_tool.py`

Problem:
- Gradient application replaced the full rectangular layer buffer.
- Non-rectangular content on transparent layers, such as circles, appeared to receive a square gradient fill because the tool ignored the existing alpha shape.

Fix:
- Gradient blending now preserves the layer's existing alpha structure.
- Gradient rendering is constrained to the content bbox derived from non-zero alpha instead of always targeting the full layer rectangle.
- Live preview marks only that content region dirty, reducing redraw cost when the visible content occupies only part of the layer buffer.

Effect:
- Transparent pixels remain transparent.
- Circular and irregularly shaped content now receives the gradient only across its actual visible shape.
- Gradient preview work is lower for sparse or tightly bounded content.

### 15. Reorder, layer-property, and layer-selection edits now use metadata-only history

Files:
- `photo_editor/core/document.py`
- `photo_editor/commands/layer/reorder_layers.py`
- `photo_editor/ui/controllers/layer_ctrl.py`
- `photo_editor/tools/move/move_tool.py`

Problem:
- Layer reorder was still writing a heavier snapshot than necessary.
- Opacity, blend mode, visibility, lock, and layer-stack selection changes were mutating live metadata without lightweight undo coverage.

Fix:
- Metadata snapshots now persist both active layer and multi-selection state.
- Reorder now records a metadata-only history entry and marks only the changed stack region dirty.
- Opacity, blend mode, visibility, lock, panel-driven selection, and move-tool canvas selection changes now create metadata-only undo entries instead of relying on full raster snapshots.

Effect:
- Common non-pixel layer-stack edits no longer need full image history copies.
- Reorder-heavy stack changes stay closer to localized invalidation when their visual footprint is bounded.

### 16. Radial and diamond gradient preview now recompute only the changed support region

Files:
- `photo_editor/tools/gradient_tool.py`

Problem:
- The earlier gradient optimization limited preview to the content bbox, but radial and diamond gradients still recomputed that entire bbox every drag step even though their changed area is spatially bounded.

Fix:
- Added support-bounds math for radial and diamond gradients.
- Preview now restores and recomputes only the union of the previous and next bounded support regions, intersected with visible content.
- Linear and conical gradients keep the existing content-bbox fallback because their influence can legitimately span the whole shape.

Effect:
- Radial and diamond gradient handle drags now touch substantially less memory and do less interpolation work.
- Dirty-region publication for those previews is tighter than simple content-bbox invalidation.

### 17. Tile-boundary invalidation bug fixed for incremental redraw

Files:
- `photo_editor/engine/tile_cache.py`

Problem:
- Dirty rectangles that crossed a tile boundary but were smaller than one full tile could fail to invalidate the far-edge tile.
- During move, resize, and rotate this left stale tile content on screen until another action happened to touch that tile.

Fix:
- Tile invalidation now expands to the aligned start and end tile coordinates before marking tiles dirty.
- Boundary-crossing dirty rects now invalidate every overlapping tile, not just the tile containing the rect origin.

Effect:
- Incremental redraw no longer leaves stale edge tiles behind when transformed content straddles tile boundaries.

### 18. Destructive tile history now stores explicit before and after payloads

Files:
- `photo_editor/core/document.py`

Problem:
- Tile-patch history only stored the pre-edit tile payload.
- Undo worked, but redo still depended on broader live-state behavior instead of an explicit tile delta.

Fix:
- Tile patch states now store both before and after tile payloads.
- Directional restore applies the correct payload for undo or redo.
- Tile-patch restores also publish their dirty region back into the renderer.

Effect:
- Destructive patch history is now a real bidirectional tile delta instead of a one-sided before-image restore.
- Paint-style undo or redo is more self-contained and better aligned with future history simplification.

### 19. Interactive resize and rotate now reuse cached fast transform proxies

Files:
- `photo_editor/core/layer.py`

Problem:
- Interactive transform previews recomputed the fast transformed raster on every call even when successive events produced the same effective preview dimensions and angle bucket.

Fix:
- Added a layer-level fast transform proxy cache keyed by effective preview dimensions and rounded angle.
- Repeated fast preview requests reuse the cached proxy instead of re-running scale and rotate every time.
- Final-quality recomputes still bypass the cache and produce a fresh result.

Effect:
- Interactive resize and rotate spend less time in repeated transform math when preview parameters have not materially changed.
- This is a first step toward a fuller transformed-output cache without changing final render fidelity.

### 20. Non-destructive source rasters now rest as uint8

Files:
- `photo_editor/core/layer.py`

Problem:
- Non-destructive transforms duplicated full float32 source rasters in `_source_pixels` and `_source_mask`.
- That multiplied memory usage during resize or rotate even before the broader active-layer storage model was changed.

Fix:
- `Layer.init_non_destructive()` now stores `_source_pixels` and `_source_mask` as uint8-at-rest payloads.
- `Layer.compute_display()` materializes float working arrays only when transform math actually runs.
- Public source accessors return float working data so existing transform code remains compatible.

Effect:
- One of the highest-value duplicate raster stores now uses compact uint8 backing.
- This is an incremental start to the wider uint8-at-rest migration without forcing immediate changes across every paint path.

### 21. Inactive display rasters can now compact to uint8 backing

Files:
- `photo_editor/core/layer.py`
- `photo_editor/ui/main_window.py`
- `photo_editor/masks/mask_manager.py`
- `photo_editor/core/layer_stack.py`
- `photo_editor/core/services/document_resize.py`
- `photo_editor/tools/text_tool.py`
- `photo_editor/vector/rasterizer.py`

Problem:
- Even after moving non-destructive source rasters to uint8, the active display buffer for every layer still stayed resident as float32.
- That limited memory savings because idle, already-rendered layers continued to occupy full float storage.

Fix:
- Added compact display backing in `Layer` using lazy uint8 storage plus float materialization through `pixels` and `ensure_pixels_float()`.
- Patched direct pixel mutation sites to request a float working buffer explicitly instead of assuming `_pixels` is always resident.
- `MainWindow` now compacts non-active layers after render completion so idle layers can actually move back to uint8-at-rest storage.

Effect:
- Non-active rendered layers no longer have to keep float display buffers resident indefinitely.
- The editor still materializes float working data automatically when a layer is edited or rendered again.

### 22. Incremental compositor can decode only the overlapping ROI from compacted layers

Files:
- `photo_editor/core/layer.py`
- `photo_editor/engine/compositor.py`
- `photo_editor/engine/render_pipeline.py`
- `photo_editor/masks/mask_manager.py`
- `photo_editor/ui/main_window.py`

Problem:
- After inactive layers were compacted to uint8 backing, incremental region renders could still force a full float materialization.
- The obvious hot path was compositor input fetch, but bounds and mask bookkeeping also still had full-buffer assumptions.
- Without additional cache handling, compaction could also leave the cached displayed frame and later tile recomposition operating at slightly different quantization states.

Fix:
- Added `Layer.decode_display_roi(...)` so a compacted raster layer can decode only the overlapping document-space slice needed for a region render.
- Added compositor-side `_layer_pixels_for_canvas(...)` so root and grouped raster branches use ROI decode whenever styles and scoped child filters do not require a full buffer.
- Removed remaining unconditional full-buffer shape reads from incremental bounds and unmasked-mask lookup paths.
- Added `RenderPipeline.sync_cached_output_from_uint8(...)` and `rebase_cached_output_to_uint8()` so cached incremental frames can be rebased to quantized display output after compaction.

Effect:
- Incremental redraw can touch compacted raster layers without eagerly materializing their entire float display buffer.
- Dirty-tile recomposition stays localized for simple compacted-layer participation.
- The displayed frame remains visually coherent after compaction instead of mixing pre-compaction cached tiles with newly decoded quantized tiles.

### 23. Large compacted display rasters now use tiled uint8 backing

Files:
- `photo_editor/core/uint8_tile_store.py`
- `photo_editor/core/layer.py`

Problem:
- The first uint8 display-compaction pass still stored one monolithic `_pixels_u8` array per layer.
- That reduced memory versus float32, but it still meant every compacted layer behaved like one large blob rather than a tiled storage unit.

Fix:
- Added `Uint8TileStore` for fixed-size tiled RGBA storage.
- Large compacted display rasters now store their uint8 payload in tile-backed form instead of a single contiguous array.
- `Layer.decode_display_roi(...)` can now pull only the overlapping tiles needed for a region render.

Effect:
- Compact-at-rest storage now moves closer to the intended tiled model instead of remaining a full-frame blob.
- ROI decode work for large layers now touches only overlapping tiles on the compact backing path.

### 24. ROI decode now reaches region-safe style and child-adjustment stacks

Files:
- `photo_editor/processors/image_processor.py`
- `photo_editor/adjustments/adjustment_base.py`
- `photo_editor/styles/style_base.py`
- `photo_editor/styles/style_engine.py`
- `photo_editor/styles/color_overlay.py`
- `photo_editor/styles/gradient_overlay.py`
- `photo_editor/styles/pattern_overlay.py`
- `photo_editor/engine/compositor.py`

Problem:
- The initial ROI decode path only activated when a layer had no styles and no scoped child processing.
- That forced unnecessary full decode fallbacks for common non-expanding effects such as color or gradient overlays and child adjustment layers.

Fix:
- Added explicit region-rendering capability contracts for processors and styles instead of relying on structural heuristics.
- Adjustments now advertise that they can safely run on an ROI.
- Added region-aware style application for `ColorOverlay`, `GradientOverlay`, and `PatternOverlay`, including full-layer coordinate normalization for ROI gradient rendering.
- Updated the compositor helper to keep using ROI decode when all active styles and child processors in the stack are region-safe.

Effect:
- More styled and adjustment-driven layer stacks stay on the compacted ROI path.
- Full-layer materialization now happens less often for common non-expanding visual effects.

### 25. Preview and final rendering now use separate pipeline caches

Files:
- `photo_editor/engine/renderer/render_scheduler.py`
- `photo_editor/engine/renderer/render_worker.py`
- `photo_editor/engine/render_pipeline.py`
- `photo_editor/ui/main_window.py`
- `photo_editor/ui/controllers/base.py`

Problem:
- Interactive preview and full-resolution rendering still shared one pipeline cache.
- That blurred the contract between preview-time cache state and final-image cache state and made post-compaction cache rebasing especially fragile.

Fix:
- `MainWindow` now owns separate interactive and final `RenderPipeline` instances.
- `RenderScheduler` chooses the interactive or final pipeline based on the render command while keeping one shared generation stream for stale-result suppression.
- Cache invalidation now hits both pipelines, while compaction rebase happens on the pipeline that actually rendered the current frame.

Effect:
- Preview and final render caches are now structurally separated even though they still use the same compositor implementation.
- This is the first real pipeline split and gives later interactive-vs-final divergence a cleaner place to land.

### 26. Bounded filters and inner or outer style effects now expose explicit ROI padding metadata

Files:
- `photo_editor/processors/image_processor.py`
- `photo_editor/filters/filter_base.py`
- `photo_editor/filters/blur/gaussian_blur.py`
- `photo_editor/filters/blur/motion_blur.py`
- `photo_editor/styles/style_base.py`
- `photo_editor/styles/style_engine.py`
- `photo_editor/styles/inner_glow.py`
- `photo_editor/styles/inner_shadow.py`
- `photo_editor/styles/outer_glow.py`
- `photo_editor/styles/drop_shadow.py`

Problem:
- The first ROI decode pass only knew whether an effect stack was region-safe or not.
- It did not encode how much neighborhood padding a bounded blur, glow, or shadow needed to stay correct at tile edges.

Fix:
- Added explicit padding metadata on processors and styles.
- Added bounded-region capability metadata for Gaussian blur, motion blur, inner glow, inner shadow, outer glow, and drop shadow.
- `StyleEngine` can now aggregate style-region padding across an enabled stack.

Effect:
- The compositor can request a larger source ROI when a bounded effect stack needs context from neighboring pixels.
- The engine no longer has to treat all blur or glow style stacks as immediate full-buffer fallbacks.

### 27. Active brush and eraser mutations can now stay tile-local on compacted display backing

Files:
- `photo_editor/core/uint8_tile_store.py`
- `photo_editor/core/layer.py`
- `photo_editor/core/document.py`
- `photo_editor/tools/tool_base.py`
- `photo_editor/tools/brush.py`
- `photo_editor/tools/eraser.py`

Problem:
- Even after tiled uint8 compaction existed, destructive paint editing still assumed a fully materialized float display buffer.
- That meant selecting a compacted layer and painting on it could immediately blow it back into a full float raster.

Fix:
- Added tile-store ROI write support plus `Layer.read_display_region_float(...)` and `Layer.write_display_region_float(...)`.
- Added `Layer.can_mutate_display_region_locally()` so tools can detect when bounded local edits can stay on compacted backing.
- Brush and eraser strokes now decode only their bounded stroke ROI, mutate a local float working buffer, and write the result back into tiled uint8 storage.
- Tile-patch history capture now uses bounded layer-region reads instead of full `layer.pixels` materialization.

Effect:
- The first active raster mutation paths now operate over tile-local float working sets on top of tiled uint8 backing.
- Compacted layers no longer have to fully materialize just because of a bounded brush or eraser stroke.

### 28. Preview compositor now uses padded ROI execution for bounded effect stacks

Files:
- `photo_editor/engine/compositor.py`
- `photo_editor/engine/render_pipeline.py`
- `photo_editor/ui/main_window.py`

Problem:
- Preview and final pipelines were separated structurally, but they still executed the same compositor logic for bounded effects.
- That limited the practical value of the split because preview still dropped to the exact full-buffer path for too many compacted layers.

Fix:
- `RenderPipeline` now carries a `quality_mode` and constructs a compositor with matching preview or final behavior.
- Preview mode uses padded ROI decode for bounded region-safe effect stacks when they do not expand bounds.
- Final mode keeps the exact full-buffer path, so the preview pipeline can diverge conservatively without weakening the correctness contract of the final pipeline.

Effect:
- Preview rendering now gets the first real compositor-level behavior difference from final rendering.
- More compacted layers with bounded blur, glow, or shadow-style effects can stay on the preview ROI path without changing final-image correctness.

### 29. Clone, heal, bucket, and gradient now use bounded write-back on compacted backing

Files:
- `photo_editor/tools/tool_base.py`
- `photo_editor/tools/clone_stamp.py`
- `photo_editor/tools/healing_brush.py`
- `photo_editor/tools/paint_bucket.py`
- `photo_editor/tools/gradient_tool.py`

Problem:
- Brush and eraser already edited compacted tiled display storage through bounded float ROIs.
- Clone stamp, healing brush, bucket, and gradient still reached for whole-layer `layer.pixels` access, which could silently re-materialize large float buffers.

Fix:
- Added a shared bounded local-mutation helper in `Tool`.
- Clone stamp and healing brush now decode a union of source and destination bounds, mutate only that working set, and write it back through `Layer.write_display_region_float(...)`.
- Bucket computes its fill from a temporary layer decode and writes back only the changed bounding box.
- Gradient preview, commit, cancel, and handle-edit paths now restore and write through display-region APIs instead of assigning through `layer.pixels[:]`.

Effect:
- More destructive tools stay on the tiled uint8 backing path during editing.
- Large compacted layers avoid accidental whole-surface float resurrection during common paint operations.

### 30. Preview ROI decode now returns the exact padded request canvas

Files:
- `photo_editor/core/layer.py`
- `photo_editor/engine/compositor.py`

Problem:
- Preview ROI rendering previously decoded only the overlapping compacted slice.
- Bounded effects such as stroke, glow, and blur need transparent padding outside the overlap to stay spatially correct near ROI edges.

Fix:
- Added `Layer.decode_display_roi_padded(...)` to return the exact requested preview canvas with zero fill outside the overlapped compacted pixels.
- Preview-mode compositor paths now request padded ROIs from the layer instead of clipped overlap-only slices.

Effect:
- Preview ROI rendering has the spatial context needed for bounded expanding effects without materializing full layers.

### 31. ROI padding contracts now cover stroke and more blur-like filters

Files:
- `photo_editor/styles/stroke.py`
- `photo_editor/filters/sharpen/sharpen.py`
- `photo_editor/filters/sharpen/unsharp_mask.py`
- `photo_editor/filters/blur/surface_blur.py`
- `photo_editor/engine/compositor.py`

Problem:
- Only the initial blur, glow, and shadow set exposed enough metadata for reduced-cost preview ROI execution.
- Stroke and additional neighborhood filters still forced broader fallback behavior than necessary.

Fix:
- Added ROI capability and padding contracts for `Stroke`, `Sharpen`, `UnsharpMask`, and `SurfaceBlur`.
- Preview compositing now trusts bounded processor padding metadata even when the effect alters alpha support, as long as the request is serviced through padded ROI decode.

Effect:
- The preview pipeline can keep more styled and filtered compacted layers on the reduced-cost ROI path.
- The interactive/final pipeline split now benefits a wider portion of real effect stacks.

### 32. Clone and heal local mutation now write back only destination bounds

Files:
- `photo_editor/tools/tool_base.py`
- `photo_editor/tools/clone_stamp.py`
- `photo_editor/tools/healing_brush.py`

Problem:
- Clone stamp and healing brush already decoded only a bounded union of source and destination space on compacted backing.
- They still wrote that full union back to tiled storage even though only the destination footprint changed.

Fix:
- Extended the shared local-mutation helper so tools can decode one working region but restrict writeback to a smaller destination bbox.
- Clone stamp and healing brush now write back only the destination stroke bounds while keeping the larger sampled source area read-only.

Effect:
- Clone and heal reduce tile-store write traffic and avoid rewriting untouched sampled source tiles.
- The compacted local-mutation path is now closer to true destination-only destructive editing.

### 33. Bounded-effect preview ROI is now regression-checked against final output, and Surface Blur was fixed

Files:
- `photo_editor/filters/blur/surface_blur.py`
- `tests/test_render_worker.py`

Problem:
- Some preview ROI tests only checked that compacted layers stayed on the cheaper path, not that preview output actually matched the final renderer.
- While expanding that coverage, `SurfaceBlur` was found to fail outright because OpenCV collapsed the blurred alpha plane to 2D before channel recombination.

Fix:
- Strengthened preview ROI tests for `OuterGlow`, `MotionBlur`, `Stroke`, `UnsharpMask`, and `SurfaceBlur` so preview incremental output must exactly match full final rendering.
- Fixed `SurfaceBlur.apply(...)` to restore the singleton alpha dimension when OpenCV returns a 2D blurred alpha array.

Effect:
- The reduced-cost preview path is now guarded by direct image-equivalence tests, not only structural assertions.
- Surface Blur now executes correctly and is covered as another bounded ROI-safe filter case.

### 34. Preview compositor now actually uses padded ROI decode for positioned and mixed bounded stacks

Files:
- `photo_editor/engine/compositor.py`
- `tests/test_render_worker.py`

Problem:
- The layer API already had `decode_display_roi_padded(...)`, but the preview compositor branch was still calling clipped `decode_display_roi(...)` in its mixed style and child-filter path.
- That meant smaller positioned layers with expanding bounded styles could still lose effect pixels at ROI edges even though the padded decode contract existed.

Fix:
- Switched the preview compositor ROI path to use `decode_display_roi_padded(...)`.
- Removed the remaining processor-bounds gate so bounded child filters can rely on the padded request canvas too.
- Added regression coverage for a positioned compacted outer-glow layer and for a compacted mixed `Stroke + UnsharpMask` stack, both checked against final full rendering.

Effect:
- Preview ROI rendering now matches the intended padded-canvas design in real compositor execution, not just in the layer helper.
- Positioned compacted layers and mixed bounded stacks stay on the cheaper preview path without clipping their effect support at ROI boundaries.

### 35. Transformed display results now compact back to uint8 or tiled uint8 immediately after recompute

Files:
- `photo_editor/core/layer.py`

Problem:
- Non-destructive source rasters had already moved to uint8-at-rest, but every `compute_display()` call still left the transformed display result resident as a full float32 buffer.
- That meant interactive transform workflows kept rebuilding the right data model and then immediately falling back to the old memory-heavy display storage.

Fix:
- `Layer.compute_display()` now compacts its transformed result back into `_pixels_u8` or `Uint8TileStore` instead of leaving `_pixels` resident.
- Float display materialization is now lazy again after transform recompute, just like other compacted display paths.
- `Layer.init_non_destructive()` can capture source data directly from compacted display storage without first inflating it to float.

Effect:
- Transformed raster layers now return to uint8-at-rest storage immediately after recompute.
- The remaining float32 display buffers are much more limited to true working-state callers instead of every transformed layer.

### 36. Transform output caching now covers both fast preview and final-quality recomputes

Files:
- `photo_editor/core/layer.py`
- `photo_editor/tools/transform_tool.py`
- `photo_editor/tools/move/auto_select.py`
- `photo_editor/tools/eyedropper.py`

Problem:
- The earlier transform cache only covered one fast preview proxy key.
- Repeated full-quality recomputes with unchanged transform parameters still reran scale and rotate, and point-read interaction paths such as auto-select and eyedropper could still inflate compacted layers unnecessarily.

Fix:
- Replaced the single fast cache with a transform-result cache keyed by source revision, quality mode, scaled dimensions, and transform parameters.
- Cached transform outputs now store compacted uint8 or tiled uint8 payloads rather than float32 buffers.
- Added compacted point-sample reads in `Layer`, and moved auto-select, eyedropper, and transform-center setup away from `layer.pixels` shape or point access.

Effect:
- Repeated fast and final transform recomputes now reuse cached transformed outputs when nothing materially changed.
- Common interactive point-sample workflows no longer defeat uint8-at-rest storage just to read one alpha or color value.

### 37. Added a real GPU interactive compositor backend with conservative CPU fallback

Files:
- `photo_editor/engine/gpu_backend.py`
- `photo_editor/ui/canvas_view.py`
- `photo_editor/ui/main_window.py`
- `photo_editor/core/layer.py`

Problem:
- The editor had fixed the data model and incremental CPU renderer, but interactive canvas compositing still depended entirely on CPU-generated flattened frames.
- That meant large flat raster stacks could not benefit from the GPU even when the canvas was already hosted in a `QOpenGLWidget`.

Fix:
- Added `QtGpuCompositorBackend`, an optional interactive compositor that renders supported flat raster-like layer stacks directly through Qt's GPU-accelerated painting path.
- The backend is intentionally conservative: unsupported documents with groups, masks, styles, child filters, clipping, unsupported blend modes, or dirty transform state automatically fall back to the existing CPU pipeline.
- Added compact uint8 export from `Layer` for backend texture upload and integrated backend selection into `MainWindow` and `CanvasView`.
- Automatic enablement is gated to real GL-backed UI sessions; offscreen and minimal test or headless platforms stay on CPU.

Effect:
- Simple large layer stacks can now bypass CPU flattening for interactive canvas feedback and render directly through the GPU-backed widget path.
- Complex documents keep the exact CPU compositor, so the new backend adds acceleration without weakening correctness or fallback safety.

### 39. GPU backend now supports top-level independent styled and child-filtered layers

Files:
- `photo_editor/engine/gpu_backend.py`
- `photo_editor/ui/main_window.py`
- `tests/test_gpu_backend.py`

Problem:
- The first GPU backend slice only accelerated flat top-level raw layers.
- Documents with top-level styles or child adjustment/filter processors still dropped entirely to the CPU compositor even when each layer subtree was independently flattenable.

Fix:
- Expanded the backend to flatten top-level independent layers with styles and directly parented adjustment/filter children into cached GPU textures.
- Cache entries now track the effective blend position as well as texture size, so filter padding and style expansion remain spatially correct.
- GPU invalidation now walks changed layers up to their top-level owner before evicting cached textures, preventing stale parent textures when child processors change.
- Added regression coverage for styled and child-filtered top-level documents, while keeping groups as an explicit CPU fallback case.

Effect:
- The GPU path now accelerates a materially broader class of real editing documents, not just raw flat stacks.
- Unsupported structural cases still fall back cleanly, so the support expansion does not weaken the conservative correctness boundary.

### 40. GPU backend now supports top-level groups via cached CPU-flattened subtree textures

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- Even after supporting top-level styled and child-filtered layers, grouped documents still fell back completely to the CPU compositor.
- That left a large class of practical multi-layer documents unable to benefit from GPU final compositing.

Fix:
- Added top-level group support by flattening the full group subtree through the existing CPU compositor into a cached texture, then compositing that texture through the GPU backend.
- Group textures are rendered top-level only, so child layers are not double-composited after their parent group texture is drawn.
- Added regression coverage that checks top-level group rendering against the CPU compositor, while preserving clipping-mask fallback coverage.

Effect:
- Grouped documents can now benefit from the hybrid GPU path without reimplementing fragile group semantics in GPU code.
- The backend stays architecturally clean: CPU computes exact subtree textures, GPU composites those textures efficiently.

### 41. GPU backend now supports top-level attached and legacy masks on flattenable layers

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- The hybrid GPU path already handled group masks during subtree flattening, but top-level raster-like layers with attached MASK children still failed the capability gate.
- Top-level layers using the legacy per-layer mask could pass the gate, but their cached GPU texture did not apply that mask, which risked silent CPU-vs-GPU drift.

Fix:
- Expanded the GPU support gate to allow attached MASK children on otherwise flattenable top-level raster, text, and shape layers.
- Added a shared effective-mask application path so both legacy masks and attached mask layers are baked into the cached subtree texture before GPU compositing.
- Added regression coverage for both legacy masked layers and child-mask-layer documents, validated against the CPU compositor.

Effect:
- The GPU backend now covers another common real-world document shape without changing compositing semantics.
- Masked top-level layers stay on the fast hybrid path, while clipping-mask chains and other structurally harder cases still fall back cleanly to CPU.

### 42. GPU backend now supports top-level clipping chains via cached chain textures

Files:
- `photo_editor/engine/gpu_backend.py`
- `photo_editor/ui/main_window.py`
- `tests/test_gpu_backend.py`

Problem:
- The hybrid GPU path still rejected Photoshop-style top-level clipping chains even when the chain was structurally isolated and exact semantics were already implemented in the CPU compositor.
- That forced a full CPU fallback for another common document shape and left cache invalidation incomplete for clipped sibling updates.

Fix:
- Added top-level clipping-chain support by treating each contiguous root clipping run as one render unit keyed by the unclipped base layer.
- Each chain member is flattened through the existing per-layer CPU subtree path, then the chain is composited into one cached texture using the same previous-alpha clipping contract as the root CPU compositor.
- GPU invalidation now maps top-level clipping-mask siblings back to their unclipped base layer so cached chain textures cannot go stale when only the clipped follower changes.
- Added regression coverage for supported top-level clipping chains and kept orphan clipping-mask layers on the CPU fallback path.

Effect:
- Another practical class of layered documents now stays on the hybrid GPU path without moving fragile clipping semantics into ad hoc GPU code.
- The backend remains conservative: valid clipping runs are accelerated, while malformed or structurally ambiguous clipping cases still fall back safely.

### 43. GPU backend now supports channel-disabled top-level layers and groups

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- The GPU capability gate still rejected any top-level layer or group with channel visibility toggles disabled.
- The simple non-group flatten fast path could also bypass channel baking entirely, which meant the backend had no safe way to match CPU output for channel-filtered documents.

Fix:
- Removed the blanket channel-toggle rejection from the support gate.
- Updated non-group flattening so channel visibility is baked into the cached texture before GPU compositing, instead of only being applied in group and CPU-only paths.
- Added regression coverage for both a channel-filtered top-level layer and a channel-filtered group, validated exactly against the CPU compositor.

Effect:
- Another common document variant now stays on the hybrid GPU path without needing any new compositing rules.
- Channel visibility semantics remain CPU-exact because the cached texture already contains the filtered result before the GPU draw step.

### 44. GPU backend now supports standalone root masks through framebuffer masking passes

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- Standalone top-level MASK layers were still forcing a full CPU fallback even though their semantics are simple and already explicit in the CPU compositor: attenuate everything composited so far by the mask grayscale.
- A naive GPU mask pass only attenuated alpha, which did not match the CPU compositor because the CPU path multiplies both RGB and alpha for global standalone masks.

Fix:
- Added support for standalone top-level mask layers whose `ex_parent_id` is `None`.
- The GPU backend now applies standalone root masks directly to the already-painted framebuffer in two passes: a `Multiply` pass to attenuate RGB by the grayscale mask, followed by a `DestinationIn` pass to attenuate alpha by that same grayscale.
- Added regression coverage for supported standalone root masks.

Effect:
- Documents using global standalone masks now stay on the hybrid GPU path without needing prefix-texture CPU flattening.
- Detached root masks are handled separately through the later CPU-prefix barrier model rather than through the standalone framebuffer-mask path.

### 45. GPU backend now supports top-level root adjustment and filter layers via cached CPU prefix textures

Files:
- `photo_editor/engine/gpu_backend.py`
- `photo_editor/ui/main_window.py`
- `tests/test_gpu_backend.py`

Problem:
- Top-level adjustment and filter layers still forced a full CPU fallback even though their semantics were already explicit in the CPU compositor.
- These root effects act on the accumulated canvas, not on one layer subtree, so treating them like ordinary GPU-drawable layers would have introduced incorrect semantics or a premature shader pipeline.

Fix:
- Added a hybrid prefix-texture path for documents with root adjustment or filter layers.
- The backend now finds the last visible top-level root effect, composites the exact CPU result of the full prefix up to and including that effect into one cached texture, draws that texture once, and then continues rendering the remaining suffix through the existing GPU path.
- GPU invalidation is conservative for documents containing root effects: any change clears the GPU cache so the prefix texture cannot go stale.
- Added regression coverage for both root adjustment and root filter documents with layers above the effect, validated against the CPU compositor with a tight tolerance appropriate for the extra cached-texture quantization boundary.

Effect:
- Documents with canvas-wide top-level effects can now stay partially on the hybrid GPU path without reimplementing root-effect semantics in GPU code.
- The design remains clean: CPU remains the source of truth for the effect-bearing prefix, GPU still accelerates the suffix and final presentation.

### 46. GPU backend orchestration is now expressed as explicit render steps

Files:
- `photo_editor/engine/gpu_backend.py`

Problem:
- The GPU backend had grown by accretion: flat layers, chain textures, standalone masks, prefix textures, and other hybrid cases were each wired directly into one long render loop.
- That shape was still working, but it was starting to make future extensions harder to reason about and easier to break.

Fix:
- Refactored the backend to build an explicit internal render plan made of staged steps such as prefix-texture draws, chain draws, and framebuffer mask passes.
- `can_render_document(...)` now validates by building that plan instead of duplicating structural rules separately from execution.
- This render-step architecture became the basis for later promoting detached root masks through CPU-prefix barriers instead of forcing them through an inaccurate framebuffer-only path.

Effect:
- The backend now has a cleaner architectural seam for future canvas-wide operations instead of accumulating more one-off branches.
- Later support expansions can be expressed as new barrier or step types instead of one-off render-loop branches.

### 47. GPU cache invalidation is now segment-aware for root-effect documents

Files:
- `photo_editor/engine/gpu_backend.py`
- `photo_editor/ui/main_window.py`
- `tests/test_gpu_backend.py`

Problem:
- Root-effect documents had moved onto the hybrid GPU path, but cache invalidation was still overly blunt: any layer change in a document containing a top-level root effect cleared the entire GPU cache.
- That was correct but wasteful, especially when an edit only affected a suffix layer that should not force re-rasterization of the cached CPU prefix texture.

Fix:
- Added document-aware invalidation in the GPU backend so it can map a changed layer to the cache entry for the affected render segment.
- Changes inside the root-effect prefix now invalidate only the cached prefix texture keyed by the last root effect, while suffix changes invalidate only the affected top-level layer or chain texture.
- `MainWindow` now delegates GPU invalidation to this document-aware backend helper instead of forcing full-cache clears for all root-effect documents.
- Added regression coverage proving that prefix edits and suffix edits evict different cache entries in a root-effect stack.

Effect:
- Interactive edits on documents with root effects no longer default to full GPU-cache eviction.
- The staged render-plan architecture now carries through into the invalidation model instead of only the draw path.

### 48. Root-effect prefix caching now reuses earlier effect prefixes instead of recomputing from document start

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- The first root-effect prefix implementation cached only the final effect-bearing prefix.
- That was already useful, but on documents with multiple top-level root effects it still recomputed each later prefix from the document start, which wasted work and limited the benefit of segment-aware invalidation.

Fix:
- Updated prefix-texture generation so a later root-effect prefix can be built from the previous cached effect prefix plus only the intervening top-level segment and the current effect.
- Prefix cache entries now retain their cropped uint8 payload so the backend can reconstruct a full-canvas synthetic base layer for the next effect segment without rereading from the GPU pixmap.
- Document-aware invalidation now evicts only the downstream root-effect caches affected by a changed top-level layer, preserving earlier effect caches when they remain valid.
- Added regression coverage for a document with two top-level root effects, including output parity and downstream-only cache eviction behavior.

Effect:
- Multi-effect documents now get real chained cache reuse rather than only a single cached final prefix.
- The hybrid GPU path is moving from one-off acceleration toward a genuine staged caching model across the top-level stack.

### 49. Detached root masks now run through the CPU-prefix barrier path instead of falling back entirely

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- Detached root masks could not be expressed faithfully as a pure framebuffer mask pass in the Qt GPU path because the CPU compositor preserves hidden RGB while attenuating only alpha.
- That kept them on full CPU fallback even after the render-plan and chained-prefix infrastructure existed.

Fix:
- Generalized the cached-prefix model from “root effects only” to broader CPU-prefix barriers.
- Detached top-level masks with `ex_parent_id` now act as prefix barriers, so the exact CPU result up to and including the detached mask is cached as a prefix texture and later suffix layers continue through the GPU path.
- Barrier invalidation and recursive prefix reuse were updated so detached-mask barriers participate in the same staged cache model as root effects.
- Added regression coverage that validates detached root-mask documents against the CPU compositor.

Effect:
- Detached root masks no longer force a full CPU fallback.
- The top-level staged cache model now covers both canvas-wide root effects and alpha-only detached-mask barriers under one architectural rule.

### 50. GPU planning, cache reuse, and invalidation now share an explicit top-level barrier-segment model

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- The backend had already evolved from one cached prefix into a staged barrier model, but the implementation still derived key decisions from ad hoc “last barrier” or “scan for later effects” logic in multiple places.
- That made the behavior harder to reason about once detached mask barriers and multiple root effects were both in play.

Fix:
- Added an explicit internal top-level barrier-segment model that records the stack ranges ending at each CPU-prefix barrier.
- Render planning, recursive prefix reuse, and document-aware invalidation now all derive from that same segment list instead of separate bespoke scans.
- Added regression coverage for a mixed-barrier document where a detached mask barrier feeds a later root effect, including parity and downstream-only invalidation behavior.

Effect:
- The GPU backend now has a single internal representation for top-level staged dependencies instead of multiple near-duplicate heuristics.
- This is the cleanest foundation so far for moving from a barrier-aware prefix cache toward a fuller top-level segment graph.

### 51. Non-barrier top-level segments between barriers are now cached independently

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- Even after barrier segmentation was explicit, later barrier prefixes still had to recomposite the full intervening non-barrier run every time they were rebuilt.
- That meant the backend understood the segment graph structurally, but it still cached only the barrier-ended prefixes rather than the non-barrier segments between them.

Fix:
- Added cached inter-barrier segment textures keyed per barrier.
- Later barrier prefixes can now reuse both the previous cached barrier prefix and the cached non-barrier segment immediately preceding the current barrier.
- Document-aware invalidation now evicts an inter-barrier segment cache independently when a changed layer belongs to that free segment, while still evicting the downstream barrier prefixes that depend on it.
- Added regression coverage proving that the inter-barrier segment cache exists and is invalidated independently from upstream barrier caches.

Effect:
- The backend now caches both barrier-ended prefixes and the non-barrier top-level segments between them.
- This is the first real step from a prefix-centric hybrid model toward a fuller cached top-level segment graph.

### 52. The post-barrier tail is now a cached suffix segment instead of a live-only special case

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- Even after inter-barrier segments were cached, the final post-barrier portion of the top-level stack was still treated differently from every other segment.
- That meant planning and invalidation still had a lingering “live suffix” exception even though the rest of the staged cache model had already moved to explicit segments.

Fix:
- Promoted the post-barrier tail into explicit cached suffix segments, split around standalone top-level masks that still need framebuffer mask passes.
- Render planning now emits cached suffix-segment steps instead of per-layer live suffix draws for barrier-bearing documents.
- Document-aware invalidation now maps edits in the post-barrier tail to the corresponding suffix-segment cache key instead of falling back to uncached per-layer invalidation.
- Updated GPU regression coverage so root-effect and mixed-barrier invalidation tests assert suffix-segment keys rather than individual tail-layer cache entries.

Effect:
- The backend no longer treats the post-barrier tail as a one-off live path; it now participates in the same cache and invalidation model as other top-level segments.
- The staged GPU architecture is now materially closer to a full top-level segment graph than to the original prefix-plus-suffix approximation.

### 53. GPU planning and invalidation now consume one explicit top-level segment graph

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- The backend had reached the point where barrier prefixes, inter-barrier runs, suffix runs, masks, and clipping chains were all structurally meaningful, but planning and invalidation still reconstructed that structure through separate logic.
- That duplication was manageable for the current feature set, but it would become technical debt as the staged GPU model widened further.

Fix:
- Added an explicit internal top-level graph that records cache-only prefix and non-barrier run segments alongside the visible draw sequence.
- Render-plan construction now translates that graph into concrete render steps instead of rescanning the top-level stack directly.
- Document-aware invalidation now resolves affected cache keys from the same graph, so cache dependencies and draw order are described in one place.
- Added a regression test that asserts the graph shape for a mixed detached-mask plus root-adjustment document.

Effect:
- The GPU backend now has one canonical structural model for top-level execution instead of parallel heuristics.
- Future support expansions can add graph segment kinds without having to duplicate planning and invalidation rules.

### 54. Prefix cache reuse now follows explicit graph dependencies instead of rescanning prefix layer slices

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- The explicit top-level graph removed the duplication between planning and invalidation, but prefix-cache reconstruction itself was still walking sliced prefix layer lists and rediscovering earlier barriers indirectly.
- That meant the backend still had one important execution path that was structurally aware in practice but not yet graph-driven by design.

Fix:
- Added explicit upstream cache dependencies to top-level graph segments.
- Prefix cache segments now declare exactly which earlier cached prefix and non-barrier run caches they depend on.
- Prefix reconstruction now resolves those dependencies directly from the graph and rebuilds the synthetic CPU prefix from dependency entries plus the current barrier layer.
- Document-aware invalidation now uses dependency-closure traversal over those explicit edges, so downstream cache eviction follows the same graph model as cache reuse.
- Added regression coverage that asserts both the graph dependency edges and the invalidation closure for mixed-barrier documents.

Effect:
- Prefix-cache reuse is no longer a special recursive path with its own structural scan logic.
- The GPU backend now has an explicit cache-dependency model that is safer to extend when more top-level segment types start participating in staged reuse.

### 55. Ordinary top-level draw units now participate in the same cache graph as barrier segments

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- The graph and dependency work already covered barrier prefixes, inter-barrier runs, and cached suffix segments, but ordinary top-level draw units were still treated as a separate cache class.
- Plain top-level layers and clipping chains were described in the graph for planning, yet their cache ownership was still resolved outside the graph during invalidation.

Fix:
- Promoted top-level `chain` draw segments into explicit cache-bearing graph nodes keyed by their unclipped base layer.
- Single top-level layers now ride through that same chain-segment path as one-layer cache-bearing graph nodes.
- Document-aware invalidation now resolves clipping-chain and ordinary top-level draw cache keys through the graph's primary cache lookup instead of a separate clipping fallback.
- Added regression coverage that asserts clipping chains appear as cache-bearing graph nodes and that invalidation of either the base or clipped follower resolves to the shared chain cache key.

Effect:
- The graph now describes not only staged barrier caches but also ordinary top-level cache ownership.
- This reduces one more class of side logic and makes future cache-bearing draw-unit types easier to add without introducing another invalidation path.

### 56. Standalone top-level masks are now represented with explicit execution edges in the graph

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- Standalone top-level masks were already supported correctly at execution time, but they still existed in the graph only as isolated step descriptors.
- The graph knew about cache ownership and some staged dependencies, yet it still did not explicitly encode the visible ordering relationship between ordinary draw units, standalone mask passes, and later draw units.

Fix:
- Added explicit graph-level execution dependencies to top-level graph segments.
- Cache-bearing prefix nodes now record both cache dependencies and the graph-node indices those dependencies correspond to.
- Ordinary draw-unit segments and standalone mask segments now record the immediately preceding visible graph node they depend on for execution order.
- Added regression coverage for a base-layer, overlay, standalone-mask, and post-mask top-layer document, asserting the exact graph shape and dependency edges.

Effect:
- The graph now describes both cache reuse structure and visible execution ordering.
- Standalone mask passes are no longer just an execution-only branch; they participate in the same explicit top-level model as the rest of the hybrid GPU pipeline.

### 57. The render plan is now scheduled from graph dependencies instead of relying on graph list order

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- The graph already carried explicit execution dependencies, but render-plan construction still consumed graph nodes by list order and only used those dependencies as a validation check.
- That meant the backend had the right structural model on paper while still depending on insertion order in practice.

Fix:
- Added a graph-derived render scheduler that walks explicit graph dependencies and produces the visible render-node order from the graph itself.
- Cache-only nodes remain part of the dependency traversal but do not emit draw steps directly.
- Render-plan construction now consumes that derived schedule instead of iterating the graph linearly.
- Added regression coverage that asserts the scheduled visible graph indices for both mixed-barrier and standalone-mask documents.

Effect:
- The render plan now follows the graph's declared dependencies rather than implicit list position.
- This is a cleaner base for future work where graph construction and scheduling may diverge from a simple append-only build order.

### 58. Top-level graph assembly now goes through an explicit builder layer

Files:
- `photo_editor/engine/gpu_backend.py`

Problem:
- By this point the graph encoded cache nodes, visible draw nodes, cache dependencies, and execution dependencies, but graph construction still lived in one backend method that directly manipulated all of that state.
- The architecture had improved, but graph assembly logic was still too concentrated for the next round of segment-type expansion.

Fix:
- Extracted top-level graph assembly into a dedicated internal builder object.
- The builder now owns node creation, cache-key indexing, cache-dependency wiring, and visible-order dependency wiring.
- `_build_top_level_graph(...)` now orchestrates barrier and suffix discovery while delegating actual node assembly to that builder.

Effect:
- Cache nodes and visible execution nodes are now constructed through one explicit internal layer instead of ad hoc state mutation inside the backend.
- This gives the GPU backend a cleaner place to add future graph node kinds without making the main backend method harder to reason about.

### 59. The top-level graph now uses explicit cache-node and visible-node roles

Files:
- `photo_editor/engine/gpu_backend.py`

Problem:
- Even after extracting graph assembly into a builder, all graph nodes still shared one catch-all dataclass.
- Cache-only nodes and visible execution nodes were carrying overlapping optional fields, which made the model less explicit than the underlying architecture had become.

Fix:
- Split the generic top-level graph node into an explicit base node plus separate cache-node and visible-node roles.
- Cache-only nodes now represent non-emitting graph structure such as run caches, while visible nodes represent scheduled execution units such as prefixes, draw segments, chains, and masks.
- Updated the scheduler and graph helpers to distinguish cache-only nodes from visible emission nodes directly through those roles.

Effect:
- The graph model is now closer to the actual execution architecture instead of encoding everything through one permissive shape.
- This makes future node-type growth safer because cache-only structure and visible render units no longer look identical to the rest of the backend.

### 60. Graph dispatch now keys off explicit node subclasses instead of `kind` strings

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- Even after splitting cache-only and visible node roles, the backend still used `kind` string checks in several important paths such as render-step creation, cache lookup, and primary cache ownership resolution.
- That left the architecture more explicit in data shape than in control flow.

Fix:
- Added explicit node subclasses for `run-cache`, `prefix-cache`, `prefix`, `segment`, `mask`, and `chain` roles.
- Updated scheduling, cache ownership, prefix reconstruction, and render-step creation to dispatch primarily through those node subclasses instead of string matching.
- Added regression coverage that asserts the concrete node subclass sequence for a mixed-barrier document.

Effect:
- The graph model is now reflected in control flow as well as data shape.
- Future graph expansions can introduce new node roles by adding new classes and targeted handlers rather than extending another layer of string-based branching.

### 61. Render-step construction and execution now use explicit step subclasses

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- The graph model had moved onto explicit node roles, but render-plan construction still collapsed those nodes into one generic `_RenderStep` payload and execution still branched on `step.kind`.
- That left the execution layer behind the rest of the architectural cleanup.

Fix:
- Split the generic render step into explicit prefix, segment, mask, and chain step subclasses.
- Render-plan construction now emits those concrete step types directly from the graph-derived schedule.
- Render execution now dispatches on step subclasses rather than string kinds.
- Added regression coverage that asserts the concrete render-step class sequence for a mixed-barrier document.

Effect:
- The execution layer now matches the graph layer in using explicit structural types instead of permissive tagged payloads.
- Future render-step variations can be added with narrower handlers and less string-driven branching in the main execution path.

### 62. The graph no longer carries redundant `kind` tags where the node class already defines the role

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- After moving the graph and execution layers onto explicit node and step subclasses, top-level graph nodes were still carrying a `kind` string alongside their concrete class.
- That duplication no longer added real information and left one more nominal tag in the architecture after most control flow had already moved away from it.

Fix:
- Removed the redundant `kind` field from top-level graph nodes.
- Updated graph construction to choose node roles directly by class, including prefix versus prefix-cache selection.
- Updated GPU graph assertions to validate explicit node-class sequences instead of relying on `kind` strings.

Effect:
- The graph model now represents node roles through one mechanism instead of two.
- This removes another small source of drift between the architecture the backend encodes and the runtime state it actually needs.

### 63. Explicit render steps now carry only step-specific payload instead of leftover shared fields

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- After splitting the execution layer into explicit step subclasses, some subclasses were still carrying payload that was no longer actually needed because the graph already provided the authoritative context.
- That left a small amount of overlap between step-local state and graph-index-based lookup.

Fix:
- Removed the redundant prefix-step cache payload and kept the prefix step keyed only by its scheduled graph index.
- Added regression coverage asserting that the mixed-barrier prefix step instance now carries only shared scheduling state.

Effect:
- Render-step instances are now closer to minimal command objects rather than partially denormalized graph snapshots.
- This reduces one more source of stale or duplicated execution metadata as the GPU backend becomes more graph-driven.

### 64. Visible graph nodes now keep only node-specific payload, with derived views where needed

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- Even after removing redundant kind tags and shared step payload, some visible graph nodes still carried overlapping fields inherited from a broader shared shape.
- In particular, mask and chain nodes were still conceptually exposing both singular and plural layer views even though one was derivable from the other.

Fix:
- Reduced the visible-node base to structural dependencies only.
- Moved cache keys, cache dependencies, singular layers, and plural layer collections down onto the specific node subclasses that actually use them.
- Kept compatibility where useful through derived views, such as `MaskNode.layers` and `ChainNode.layer`.
- Updated GPU graph assertions to validate the slimmer node shape without assuming every node exposes every optional field.

Effect:
- Graph nodes now look more like precise domain objects and less like partially empty records.
- This keeps the top-level GPU model tighter as new node roles are added and reduces the chance of stale duplicated state living on the wrong node type.

### 65. Cache-only graph nodes now keep only truly shared cache payload

Files:
- `photo_editor/engine/gpu_backend.py`
- `tests/test_gpu_backend.py`

Problem:
- After minimizing visible-node payloads, the cache-only side still had a slightly broader shared base than the current node set really needed.
- In practice, `run-cache` was the only true cache-only node and it was carrying some of its own payload through the shared cache-node base.

Fix:
- Reduced the shared cache-node base to the cache key alone.
- Moved the run-cache layer payload onto `RunCacheNode` itself.
- Added regression coverage asserting the concrete stored payload shape of the first run-cache node in the mixed-barrier graph.

Effect:
- Cache-only nodes now mirror the same precision principle already applied to visible nodes and render steps.
- This keeps the graph model narrower and makes future cache-node additions easier to reason about without inheriting unnecessary shared fields.

### 66. Graph cache traversal now uses typed helpers instead of dynamic payload access

Files:
- `photo_editor/engine/gpu_backend.py`

Problem:
- The graph had already moved to explicit node subclasses, but cache traversal still probed nodes dynamically for `cache_key` and `cache_dependencies`.
- That left part of invalidation and cache lookup structurally looser than the rest of the GPU backend.

Fix:
- Added typed helper functions that expose cache keys only for node classes that actually own them.
- Added a matching helper for cache dependencies and routed cache lookup, descendant traversal, and primary-key resolution through those helpers.

Effect:
- Graph cache traversal now matches the explicit node-role architecture instead of depending on optional-field probing.
- Future node-shape cleanup can stay local because graph consumers no longer assume cache payload exists on arbitrary nodes.

### 67. Render-plan construction and step execution now route through typed helper methods

Files:
- `photo_editor/engine/gpu_backend.py`

Problem:
- The graph model and render-step model were explicit, but render-plan construction and render-step execution still embedded large subtype-switch blocks inline.
- That left planning and execution readable only by scanning long mixed-instance chains instead of following a clear typed flow.

Fix:
- Extracted visible-node to render-step conversion into typed helper methods per node role.
- Extracted render-step execution into typed helper methods per step role while preserving the existing step classes and behavior.

Effect:
- The GPU backend now reads more cleanly as graph scheduling, typed plan construction, and typed step execution.
- Future node or step role changes can stay localized without growing two large central branching blocks.

### 68. Prefix cache nodes now follow the cache-only graph role explicitly

Files:
- `photo_editor/engine/gpu_backend.py`

Problem:
- `PrefixCacheNode` was already treated as cache-only by scheduling, but its class still inherited from the visible-node base.
- That made the node-role model slightly misleading because one cache-only prefix node still appeared under the visible branch of the graph type hierarchy.

Fix:
- Moved `PrefixCacheNode` onto the cache-node base while keeping its prefix-specific payload and behavior unchanged.
- Simplified cache-key helper logic so cache-only prefix nodes are covered through the cache-node role instead of a separate special case.

Effect:
- The graph type hierarchy now matches runtime behavior more closely: renderable prefix nodes are visible, cached prefix nodes are cache-only.
- This reduces another small role mismatch in the staged GPU backend model.

### 69. Single-layer raster transforms now use GPU preview with CPU commit fallback

Files:
- `photo_editor/core/layer.py`
- `photo_editor/tools/move/move_tool.py`
- `photo_editor/tools/move/resize_ops.py`
- `photo_editor/tools/move/rotate_ops.py`
- `photo_editor/engine/gpu_backend.py`
- `photo_editor/ui/main_window.py`
- `tests/test_bb_move_tool.py`
- `tests/test_gpu_backend.py`

Problem:
- Interactive resize and rotate still called `compute_display(fast=True)` on every drag step.
- On 4K and 5K raster layers that meant every mouse move still paid a full CPU source resample and rotation through the non-destructive transform path.
- The existing Qt GPU backend only accelerated document compositing after transformed layer pixels already existed, so it did not remove the main transform bottleneck.

Fix:
- Added a geometry-only transform preview update on `Layer` so width, height, and transform bounds can track live drag state without rebuilding raster pixels.
- Added an opt-in live transform preview path to `MoveTool` for the safe subset: single top-level raster layers with no masks, clips, styles, or child semantics that would change preview correctness.
- Added transient transform preview support to the Qt GPU backend so the committed background is rendered without the active layer and the active layer is redrawn as a transformed preview texture on top.
- Kept the CPU exact path as the commit stage on release: the final raster result is still produced once through `compute_display(fast=False)` and then cached normally.
- Unsupported cases stay on the previous CPU live-transform behavior automatically.

Effect:
- Supported single-layer raster transforms no longer do per-frame CPU pixel recompute during drag.
- CPU remains authoritative for the committed result and acts as the rollback path for every unsupported or unavailable preview case.

Measured 4K / 5K results on this workspace:
- 4K (`3840x2160`) resize drag step: CPU live recompute about `345.77 ms`; GPU preview path about `0.12 ms` for the drag update plus about `19.60 ms` to render the preview frame; final CPU commit on release about `814.73 ms`.
- 4K (`3840x2160`) rotate drag step: CPU live recompute about `310.94 ms`; GPU preview path about `0.11 ms` for the drag update plus about `23.09 ms` to render the preview frame; final CPU commit on release about `733.19 ms`.
- 5K (`5120x2880`) resize drag step: CPU live recompute about `606.50 ms`; GPU preview path about `0.10 ms` for the drag update plus about `29.28 ms` to render the preview frame; final CPU commit on release about `1449.97 ms`.
- 5K (`5120x2880`) rotate drag step: CPU live recompute about `548.79 ms`; GPU preview path about `0.16 ms` for the drag update plus about `41.80 ms` to render the preview frame; final CPU commit on release about `1302.35 ms`.
- Additional move-only measurement on the same large raster documents showed near-identical full-frame render cost with and without the preview session (`4K`: about `199.40 ms` baseline vs about `207.53 ms` preview, `5K`: about `353.17 ms` baseline vs about `354.09 ms` preview), which indicates the remaining move heaviness is now dominated by background redraw/compositing cost rather than transform math itself.

### 70. GPU transform preview now covers groups, pseudo-groups, masked layers, styled layers, and clipping chains

Files:
- `photo_editor/engine/gpu_backend.py`
- `photo_editor/tools/move/move_tool.py`
- `photo_editor/tools/move/resize_ops.py`
- `photo_editor/tools/move/rotate_ops.py`
- `photo_editor/ui/main_window.py`

Problem:
- The GPU transform preview only covered single top-level raster layers with no masks, styles, children, or clipping.
- Groups, pseudo-groups (parent with children), clipping chains, and masked/styled layers all fell back to per-frame `compute_display(fast=True)` on every drag step.
- On 4K/5K raster layers that meant every mouse move still paid full CPU source resample and rotation for every child in the group.

Fix:
- Extended `_TransformPreviewSession` with `source_kind` (single, group, chain, flattened) and `chain_layer_ids` for compound preview sources.
- Extended `_supports_transform_preview_layer` to accept groups (`LayerType.GROUP`), layers with masks (legacy or child), layers with styles or child processors, and clipping chain base layers.
- Added `_clipping_chain_for_base` to discover contiguous clipping runs from a base layer.
- Added `_compute_preview_source` that routes to `_flatten_group_pixels`, `_composite_chain_tight`, or `_flatten_layer_pixels` based on source kind.
- Added `build_compound_transform_preview_session` for groups/pseudo-groups where transform params come from the move tool rather than from the layer.
- Updated `_draw_transform_preview` to handle compound sources where the blend position is not `(0, 0)`.
- Added `preview_only` parameter to `_apply_group_resize`, `_apply_group_rotate`, `_apply_multi_resize`, `_apply_multi_rotate`, and `_sync_mask_transforms` so group transforms skip `compute_display(fast=True)` during drag and only update geometry.
- Added group preview state tracking on the move tool (`_group_preview_center`, `_group_preview_sx`, `_group_preview_sy`, `_group_preview_angle`) so the GPU session builder can read the current group transform.
- Updated `MainWindow._current_transform_preview_session` to build compound sessions for groups and pseudo-groups using the move tool's preview state.
- Added first-frame preview cost reduction: compound preview sources reuse existing layer/group pixmaps from normal rendering when available, and all computed preview sources are cached with `rgba_u8` for later frames.

Effect:
- Groups, pseudo-groups, masked layers, styled layers, and clipping chain base layers now skip per-frame CPU pixel recompute during interactive drag.
- CPU remains authoritative for the committed result on release.
- Unsupported cases fall back automatically to the existing CPU live-transform path.

Measured 4K / 5K group results on this workspace:
- 4K (`3840x2160`) group resize drag step: CPU live recompute about `312.89 ms` per frame; GPU preview path about `0.08 ms` per frame; final CPU commit on release about `642.6 ms`.
- 5K (`5120x2880`) group resize drag step: CPU live recompute about `550.98 ms` per frame; GPU preview path about `0.08 ms` per frame; final CPU commit on release about `1138.1 ms`.
- 4K (`3840x2160`) group rotate drag step: CPU live recompute about `342.75 ms` per frame; GPU preview path about `0.15 ms` per frame; final CPU commit on release about `732.6 ms`.
- 5K (`5120x2880`) group rotate drag step: CPU live recompute about `586.48 ms` per frame; GPU preview path about `0.09 ms` per frame; final CPU commit on release about `1232.8 ms`.
- 4K (`3840x2160`) masked-layer resize drag step: CPU live recompute about `382.56 ms` per frame; GPU preview path about `0.03 ms` per frame; final CPU commit on release about `805.7 ms`.
- 5K (`5120x2880`) masked-layer resize drag step: CPU live recompute about `664.03 ms` per frame; GPU preview path about `0.03 ms` per frame; final CPU commit on release about `1420.7 ms`.

### 71. GPU preview session is now live-synced, cache-protected, and pre-captured for artifact-free 60fps drag

Files:
- `photo_editor/engine/gpu_backend.py`
- `photo_editor/ui/main_window.py`
- `photo_editor/ui/controllers/canvas_ctrl.py`
- `photo_editor/tools/move/move_tool.py`

Problem:
- The compound preview drawing code had wrong coordinate math (manual offset/scale instead of QPainter transform chain), producing visual artifacts and mispositioned textures during group/chain transforms.
- The preview source cache was invalidated every frame by `_invalidate_gpu_backend`, forcing expensive recomposition of the group composite from children whose positions/geometry had already been modified by the move tool — producing garbage output from inconsistent state.
- The preview session was never synced during move-tool drag frames (`canvas_ctrl.on_move` only emitted `canvas_update_requested`, skipping `_sync_transform_preview_session`), so single-layer moves never activated GPU preview at all.
- Dirty-region calculation (`layers_visual_bounds` + `mark_region_pair_dirty`) ran on every drag frame even during GPU preview, iterating all affected layers for no benefit.

Fix:
- Rewrote `_draw_transform_preview` to use a unified QPainter transform chain (translate → rotate → scale) for both single and compound sources, using document-space offset from session center to texture origin for compound sources.
- Protected active preview source from cache invalidation: `invalidate_layer` and `invalidate_all` now preserve the entry keyed by the active session's `source_cache_key`.
- Added `pre_capture_transform_source` to eagerly capture compound preview textures (group/chain/flattened) while children are in their original state, called from `_supports_move_tool_transform_preview` during `on_press`.
- Skipped `_invalidate_gpu_backend` entirely during active preview sessions (background layers don't change during drag).
- Added `mw._sync_transform_preview_session()` call in `canvas_ctrl.on_move` for the MOVE tool so the session updates every frame.
- Skipped dirty-region computation (`layers_visual_bounds` and `mark_region_pair_dirty`) during active preview by early-returning from `_mark_transform_dirty`.
- Cleared `_use_live_transform_preview` before `_mark_transform_dirty` in `on_release` so the final dirty region propagates correctly to the CPU pipeline.

Effect:
- No more visual artifacts during group/chain/masked-layer transforms.
- Drag frames now run at ~3ms for 4K and ~5ms for 5K (well under the 16ms budget for 60fps).
- Single-layer moves are now GPU-accelerated (previously fell back to full CPU re-render).
- Background layers are rendered once at drag start and reused for all subsequent frames.

Measured results:
- 4K single-layer move: 210ms/frame (no preview) → 2.9ms/frame (preview) — **72x speedup**
- 4K group (3L) move: 210ms first frame → 3.0ms/frame steady state — **72x speedup**
- 5K single-layer move: 365ms/frame → 5.1ms/frame — **71x speedup**
- 5K group (3L) move: 395ms first frame → 5.5ms/frame steady state — **72x speedup**
- 5K resize: 365ms/frame → 4.9ms/frame — **75x speedup**
- 5K rotate: 365ms/frame → 4.9ms/frame — **75x speedup**

### 38. Uint8 conversion is now hardened against NaN and infinity payloads

Files:
- `photo_editor/core/layer.py`

Problem:
- Some edge-case pipelines could feed invalid float values into `_float_to_u8`, producing runtime warnings during compaction and cache storage.

Fix:
- Added `nan_to_num` normalization before rounding and casting to uint8.

Effect:
- Display compaction and cache storage are now more robust against malformed intermediate pixel payloads.

## Tests Added

- `tests/test_history_optimizations.py`
- `tests/test_canvas_view.py` extended with proxy-dimension coverage.
- `tests/test_render_worker.py` extended with preview downsampling coverage.
- `tests/test_main_window_smoke.py` extended with viewport preview-budget coverage.
- `tests/test_history_optimizations.py` extended with tile-patch restore coverage.
- `tests/test_history_optimizations.py` extended with gradient changed-tile history coverage.
- `tests/test_history_optimizations.py` extended with move dirty-region, structural dirty-region, and alpha-respecting gradient coverage.
- `tests/test_history_optimizations.py` extended with metadata-only reorder, selection restore, and radial gradient support-region coverage.
- `tests/test_history_optimizations.py` extended with directional before/after tile-patch undo-redo coverage and fast transform proxy cache coverage.
- `tests/test_history_optimizations.py` extended with uint8-at-rest source storage coverage.
- `tests/test_history_optimizations.py` extended with compact-display lazy materialization coverage.
- `tests/test_history_optimizations.py` extended with tiled compact-display storage coverage.
- `tests/test_history_optimizations.py` extended with tile-local brush mutation coverage on compacted backing.
- `tests/test_render_worker.py` extended with incremental dirty-tile recomposition coverage.
- `tests/test_render_worker.py` extended with tile-boundary invalidation coverage.
- `tests/test_render_worker.py` extended with complex-stack and root-filter region redraw equivalence coverage.
- `tests/test_render_worker.py` extended with compacted-layer ROI decode and cache-preservation coverage.
- `tests/test_render_worker.py` extended with region-safe styled ROI decode coverage.
- `tests/test_render_worker.py` extended with region-safe child-adjustment ROI decode coverage.
- `tests/test_render_worker.py` extended with preview-only bounded outer-glow ROI coverage.
- `tests/test_render_worker.py` extended with preview-only bounded motion-blur ROI coverage.
- `tests/test_history_optimizations.py` extended with compacted bucket and compacted gradient local-mutation coverage.
- `tests/test_history_optimizations.py` extended with compacted clone-stamp and healing-brush local-mutation coverage.
- `tests/test_render_worker.py` extended with preview-only compacted stroke and unsharp-mask ROI coverage.
- `tests/test_render_worker.py` now also asserts preview incremental output matches final full rendering for compacted stroke and unsharp-mask stacks.
- `tests/test_render_worker.py` now also asserts preview incremental output matches final full rendering for compacted outer-glow, motion-blur, and surface-blur stacks.
- `tests/test_render_worker.py` now also asserts preview incremental output matches final full rendering for positioned compacted outer-glow layers and compacted mixed style-plus-filter stacks.
- `tests/test_history_optimizations.py` extended with final-quality transform-cache reuse coverage.
- `tests/test_history_optimizations.py` extended with transformed-display compaction, compacted ND-source capture, and point-read no-materialization coverage.
- `tests/test_gpu_backend.py` added to validate GPU-backend rendering against the CPU compositor for supported flat stacks and to verify conservative fallback on unsupported documents.
- `tests/test_gpu_backend.py` extended to validate styled and child-filtered top-level GPU rendering against the CPU compositor and to keep grouped documents on the fallback path.
- `tests/test_gpu_backend.py` extended to validate top-level group rendering against the CPU compositor and to keep clipping-mask documents on the fallback path.
- `tests/test_gpu_backend.py` extended to validate top-level legacy-mask and attached-mask-layer GPU rendering against the CPU compositor.
- `tests/test_gpu_backend.py` extended to validate top-level clipping-chain GPU rendering against the CPU compositor and to keep orphan clipping-mask documents on the fallback path.
- `tests/test_gpu_backend.py` extended to validate channel-filtered top-level layer and group GPU rendering against the CPU compositor.
- `tests/test_gpu_backend.py` extended to validate standalone and detached root-mask GPU rendering against the CPU compositor.
- `tests/test_gpu_backend.py` extended to validate root adjustment and root filter GPU-prefix rendering against the CPU compositor.
- `tests/test_gpu_backend.py` extended with segment-aware root-effect invalidation coverage.
- `tests/test_gpu_backend.py` extended with multi-root-effect prefix-reuse and downstream-effect invalidation coverage.
- `tests/test_gpu_backend.py` extended with mixed detached-mask plus root-effect barrier-segment coverage.
- `tests/test_gpu_backend.py` extended with inter-barrier segment-cache and independent invalidation coverage.
- `tests/test_gpu_backend.py` updated to validate cached suffix-segment invalidation behavior in root-effect and mixed-barrier documents.
- `tests/test_gpu_backend.py` extended with explicit top-level GPU segment-graph coverage for mixed-barrier documents.
- `tests/test_gpu_backend.py` extended with explicit graph-dependency and dependency-closure invalidation coverage for mixed-barrier documents.
- `tests/test_gpu_backend.py` extended with cache-bearing clipping-chain graph coverage and graph-based chain invalidation coverage.
- `tests/test_gpu_backend.py` extended with standalone-mask execution-edge graph coverage.
- `tests/test_gpu_backend.py` extended with direct graph-derived render-schedule coverage.
- `tests/test_main_window_smoke.py` re-run after the preview/final pipeline split.
- `tests/test_gpu_backend.py` extended with group preview session building, compound session building, chain-aware preview, styled-layer preview, group composite caching, and existing-pixmap reuse coverage.
- `tests/test_bb_move_tool.py` extended with group resize/rotate GPU preview skip, pseudo-group resize GPU preview skip, group move center tracking, and group preview state reset coverage.

Focused validation run after the changes:

```bash
e:/OXM/Projects/PhotoEditor/.venv/Scripts/python.exe -m pytest tests/test_history_optimizations.py tests/test_bb_move_tool.py tests/test_main_window_smoke.py tests/test_render_worker.py tests/test_commands.py tests/test_canvas_view.py -q
```

## What Still Remains Heavy

These fixes improve responsiveness and reduce avoidable memory spikes, but they do not change the fundamental storage and compositing model.

### 1. Raster buffers are still full-frame float32

- A 4K RGBA float32 image is about 126.6 MiB.
- Large documents still accumulate memory quickly because canonical layer storage remains float32.

### 2. Background is still a full raster layer

- New documents still start with a full-sized white raster background.
- Opened images also still live inside the same full-frame raster model.

### 3. Incremental invalidation is still conservative for some structure changes

- Paint-style tools now feed dirty regions directly into the renderer.
- Move, resize, rotate, reparent, and reorder operations now also publish explicit dirty bounds.
- Some broader graph edits and layer-tree mutations still over-invalidate when the affected relationship set is hard to bound cheaply.

### 4. Gradient preview redraw is still broad for some gradient types

- Gradient history capture is now tile-diff based.
- Radial and diamond previews now recompute only their changed support region.
- Linear and conical previews still redraw the visible content bbox because their influence can span the whole shape.

## Recommended Next Steps

1. Extend precise invalidation to harder layer-graph mutations where affected overlap sets are still computed conservatively.
2. Push more gradient cases beyond content-bbox fallback where mathematically safe, especially for commit-time and additional handle-edit scenarios.
3. Push more styles and bounded filters onto explicit ROI-safe execution with padding metadata where mathematically valid.
4. Move more destructive tools and pixel processors from full-layer float assumptions onto tile-local working sets.
5. Move canonical raster storage from float32 to fully tiled uint8 backing and convert to float only in processing paths.
6. Replace the default raster background with a procedural/document fill model.

## Summary

The current remediation pass fixes the biggest avoidable runtime costs without rewriting the full engine:

- only one render worker at a time
- faster downsampled interactive previews
- automatic full-res recovery after idle
- cheaper undo for metadata-only operations
- dirty-tile recomposition for both simple and complex compositing stacks
- tile-patch undo for destructive paint tools
- gradient history that stores only changed tiles
- exact dirty bounds for move, transform, and structural reparent edits
- metadata-only undo for reorder, layer-property, and layer-selection edits
- bounded support-region preview recomputation for radial and diamond gradients
- fixed tile-boundary invalidation that could leave stale transform artifacts on screen
- bidirectional before/after tile delta payloads for destructive patch history
- cached fast transform proxies for interactive resize and rotate
- uint8-at-rest storage for non-destructive source rasters
- compact uint8 backing for inactive display rasters with lazy float decode
- tiled uint8 backing for large compacted display rasters
- ROI-only decode for compacted raster layers during incremental compositing
- ROI-safe style and child-adjustment execution on compacted layers
- separate interactive and final render pipeline caches behind one scheduler
- explicit ROI padding metadata for bounded blur, glow, and shadow effect stacks
- tile-local brush and eraser mutation on compacted tiled backing
- preview-only padded ROI compositor behavior for bounded non-expanding effect stacks
- gradient fills that preserve the actual visible shape instead of filling transparent square bounds
- plain move no longer duplicates large raster buffers unnecessarily

These changes should materially improve perceived responsiveness on large images, especially for move/drag interactions, while setting up the renderer for deeper structural work later.