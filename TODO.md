# TODO

## Current State

- The app is materially faster after the render, cache, ROI, history, and hybrid GPU compositor work.
- The next focus area is interactive layer transforms: move, scale, and rotate on large raster layers still feel heavy.

## Carry-Over GPU Backend Cleanup

- Narrow the remaining broad unions in the GPU graph/pixmap helpers so prefix and segment rendering consume more specific typed inputs.
- Keep shrinking shared helper contracts where graph consumers still accept wider node families than they really need.
- Extend structural GPU tests as those helper boundaries get tighter, so the staged graph model stays explicit and regression-resistant.

## Transform Hotspot Findings

- Interactive resize and rotate still call `layer.compute_display(fast=True)` on every drag step.
- The current hotspot lives in:
  - `photo_editor/tools/move/resize_ops.py`
  - `photo_editor/tools/move/rotate_ops.py`
  - `photo_editor/core/layer.py`
  - `photo_editor/transforms/transform_engine.py`
- `Layer.compute_display(...)` still performs full CPU source resample + rotation through OpenCV for each intermediate drag state.
- The current Qt GPU backend accelerates document compositing only after transformed layer pixels already exist, so it does not remove the expensive per-frame transform recompute.

## Transform Acceleration Direction

- Implemented now:
  - single-layer top-level raster move / scale / rotate preview on the GPU-backed canvas path
  - geometry-only drag updates during preview
  - exact CPU recompute kept as the release-time commit path
  - automatic fallback to the existing CPU live path for unsupported cases

### Goal

- Use the GPU for interactive transform preview.
- Keep the CPU path as the source of truth for final committed pixels.
- Fall back cleanly to CPU when GPU preview is unavailable or unsupported.

### Phase 1. Add an interactive transform preview model

- Introduce a transient transform-preview state owned by the UI/render layer, not the `Layer` display buffer.
- Store:
  - affected layer ids
  - preview affine transform or per-layer transform params
  - source revision keys
  - session generation id
  - mode: move / scale / rotate / group / multi-select
- Keep the committed document state unchanged during drag except for lightweight geometry needed by overlays and hit-testing.

### Phase 2. Render active transforms on the GPU instead of recomputing layer pixels

- Reuse the existing GPU canvas/document renderer hook as the insertion point for transform preview.
- During drag:
  - draw the committed background from the last stable document state
  - draw the active layer or selection as a transient transformed texture on top
  - apply translation / scale / rotation through Qt painter transforms or an OpenGL-backed path
- For move, avoid re-rendering the layer pixels entirely and only update the draw matrix.
- For scale and rotate, sample directly from the stored source texture instead of calling `compute_display(fast=True)` every mouse move.

### Phase 3. Commit through the CPU exact path on release

- On mouse release, compute the exact committed transform through the existing CPU path:
  - `layer.compute_display(fast=False)` for the final raster result
  - existing metadata/history save flow remains authoritative
- After commit:
  - invalidate the relevant GPU/document caches
  - drop the transient preview session
  - redraw from the committed document state

### Phase 4. CPU rollback and fallback rules

- If GPU preview is unavailable, unsupported, or fails mid-session, continue with the current CPU live-transform path.
- If a preview session becomes stale because the layer source revision changes, discard the preview and rebuild or fall back.
- Unsupported cases should stay on CPU until explicitly supported:
  - complex groups with unsupported child semantics
  - layers whose preview source cannot be represented safely as a single texture
  - edge cases where masks, clips, or root effects would make preview semantics ambiguous
- The rollback rule is simple:
  - GPU is preview-only
  - CPU owns commit
  - CPU also remains the safety fallback for every preview frame

### Phase 5. Start with the highest-value subset

- Single raster layer move preview on GPU.
- Single raster layer scale preview on GPU.
- Single raster layer rotate preview on GPU.
- Then expand to:
  - mask-linked parent layers
  - multi-selection
  - groups
  - clipping chains

### Phase 6. Testing

- Add focused tests for transform preview session lifecycle:
  - session starts on drag
  - preview invalidates only the needed layers
  - session clears on commit or cancel
  - stale preview state falls back to CPU
- Add parity checks ensuring CPU final output after commit matches the current authoritative transform result.
- Keep existing move / render worker / main-window smoke tests in the focused regression pack.

## Immediate Next Tasks For The Transform Track

- Expand preview coverage beyond the current safe subset to include mask-linked parent layers where preview semantics can still be kept exact.
- Add preview support for multi-selection and real groups without reintroducing per-frame CPU raster recompute.
- Profile move-only interactions separately to determine whether the next bottleneck is base document redraw, invalidation breadth, or transform-box/UI churn.
- Reduce preview-frame render cost further for 5K transforms by tightening exclusion/invalidation and reusing more cached background state.
- Validate the new path against more real-world large-layer stacks, not only isolated raster transforms.