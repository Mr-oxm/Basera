# TODO

## Current State

- The app is materially faster after the render, cache, ROI, history, and hybrid GPU compositor work.
- GPU transform preview now covers single layers, groups, pseudo-groups, masked layers, styled layers, and clipping chains.
- Interactive resize, rotate, and **move** on large documents skip per-frame CPU pixel recompute during drag and commit through the exact CPU path on release.
- Preview session is live-synced on every move-tool drag frame, cached preview source is protected from invalidation, and compound textures are pre-captured before transforms modify children.
- Steady-state drag frames run at ~3ms (4K) / ~5ms (5K) — well under 16ms for 60fps.

## Carry-Over GPU Backend Cleanup

- Narrow the remaining broad unions in the GPU graph/pixmap helpers so prefix and segment rendering consume more specific typed inputs.
- Keep shrinking shared helper contracts where graph consumers still accept wider node families than they really need.
- Extend structural GPU tests as those helper boundaries get tighter, so the staged graph model stays explicit and regression-resistant.

## Transform Acceleration — Implemented

### Single-layer GPU preview (Phase 1, implemented)
- Single top-level raster layer move / scale / rotate preview on the GPU-backed canvas path.
- Geometry-only drag updates during preview.
- Exact CPU recompute kept as the release-time commit path.
- Automatic fallback to the existing CPU live path for unsupported cases.

### Compound source GPU preview (Phase 2, implemented)
- Groups: the full group subtree is captured as one composite texture at session start; during drag the composite is drawn with the group-level transform applied through Qt painter transforms.
- Pseudo-groups (parent with children): same as groups — parent + non-mask children are composited once and transformed as a unit.
- Clipping chains: chain members are composited through `_composite_chain_tight` into one texture; all chain members are excluded from the background render.
- Masked layers: legacy mask and attached mask children are baked into the flattened layer texture via `_flatten_layer_pixels`.
- Styled / child-filtered layers: styles and child processors are baked into the flattened texture.
- Group composite caching: existing layer/group pixmaps from normal rendering are reused for first-frame preview when available.

### Live session sync and cache protection (Phase 3, implemented)
- Preview session is synced on every `canvas_ctrl.on_move` for the MOVE tool, so single-layer moves benefit from GPU preview.
- Active preview source is protected from `invalidate_layer` and `invalidate_all` during drag.
- Compound preview textures are pre-captured in `pre_capture_transform_source` during `on_press`, before any transforms modify children state.
- GPU backend invalidation is skipped entirely during active preview sessions (background layers are unchanged).
- Dirty-region calculation is skipped during preview drag frames.
- Drawing uses a unified QPainter transform chain (translate → rotate → scale) for both single and compound sources.

### Architecture
- `_TransformPreviewSession` now supports `source_kind` (single, group, chain, flattened) and `chain_layer_ids`.
- `_draw_transform_preview` uses QPainter's transform chain with document-space offset for compound sources.
- Move tool tracks group-level transform state (`_group_preview_center`, `_group_preview_sx/sy`, `_group_preview_angle`).
- `MainWindow` routes group/multi sessions to `build_compound_transform_preview_session`.
- Group/multi resize and rotate accept `preview_only` to skip `compute_display(fast=True)`.

## Immediate Next Tasks

- Add multi-selection preview support for cases where each selected layer is independently flattenable.
- Reduce the first-frame capture cost (200-400ms) for 4K/5K by incremental or async compositing.
- Investigate whether the release-time CPU commit can be made asynchronous to reduce the post-drag freeze on 5K documents.
- Profile overlay and transform-box work during move so the remaining UI-thread cost is separated from renderer cost.
- Validate the new compound preview path against more real-world large-layer stacks with complex styles, masks, and clipping.
