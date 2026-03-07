# Refactoring History

This document is a full handoff record of the architecture and factorization work completed during this refactor session.

It is intentionally detailed. The goal is to preserve not just the final code shape, but also the reasoning, migration sequence, structural rules, and validation strategy used to get there.

## Scope

This report covers the refactors completed in this chat session only.

It does not attempt to describe every historical change in the repository. It documents the architecture work that was performed to make the application easier to maintain, easier to navigate, and cheaper to reason about in future human and AI-assisted work.

## Primary Goals

The refactor work followed four main goals:

1. Remove architecture violations and dependency leaks.
2. Reduce duplicated abstractions and repeated controller logic.
3. Move shared behavior into explicit registries, services, helpers, and context boundaries.
4. Keep behavior stable through focused regression tests after each architectural step.

## Problems Present At The Start

At the start of this session, the codebase had several structural issues that were increasing maintenance cost.

### 1. Processor lookup was in the UI layer

Adjustment and filter discovery lived in UI code, especially around `photo_editor/ui/filter_runner.py`. That made the UI the source of truth for available processors, and it also encouraged lower layers to rely on UI modules indirectly.

### 2. Three similar image-processing abstractions existed

Adjustments, filters, and effects were modeled as parallel but overlapping abstractions. They had similar responsibilities, similar parameter behavior, and similar image-processing structure, but no shared contract.

### 3. Core logic was too close to UI modules

Document restore and processor reconstruction relied on paths that should not have needed UI knowledge. This made layering weaker than it looked.

### 4. Controllers were too tightly coupled to `MainWindow`

Controllers reached directly into `MainWindow` internals for document state, render invalidation, panel refresh, tool interactions, tab state, status updates, and cross-controller calls. That produced a large implicit API surface with weak boundaries.

### 5. Cross-controller UI sync was implicit and scattered

Selection overlay refreshes, transform-box updates, panel refreshes, clone preview, duplicate-selection behavior, and brush cursor updates were coordinated by direct controller-to-controller calls or raw widget access instead of explicit signaling.

### 6. Open-document state was effectively a loose UI concern

Document tabs and open-document tracking were owned too directly by the main window rather than by an explicit session abstraction.

### 7. New helper files had no coherent home

As refactors progressed, extracted helpers initially landed at the root of `photo_editor/ui` or `photo_editor/core`. That was useful as an intermediate step, but it created flat-package clutter and needed to be cleaned up into explicit subpackages.

## Refactor Sequence

The work was done incrementally. Each step aimed to remove one kind of architectural debt without destabilizing unrelated behavior.

### Phase 1: Registry extraction for adjustments and filters

The first structural correction was moving processor lookup out of the UI layer.

#### What changed

- Added `photo_editor/registries/adjustment_registry.py`
- Added `photo_editor/registries/filter_registry.py`
- Added `photo_editor/registries/__init__.py`
- Updated `photo_editor/ui/filter_runner.py` to use registries instead of being the source of truth
- Updated `photo_editor/core/document.py` so restore paths resolve processors through registries instead of UI code

#### Why this mattered

This removed a bad dependency direction. Processor discovery became a shared non-UI concern, which allowed document restore and other lower-level logic to resolve processor classes without importing dialogs or controllers.

#### Result

Processor lookup is now centralized in `photo_editor/registries`.

### Phase 2: Shared processor contract via `ImageProcessor`

The next major change unified the image-processing model.

#### What changed

- Added `photo_editor/processors/image_processor.py`
- Added `photo_editor/processors/__init__.py`
- Updated `photo_editor/adjustments/adjustment_base.py` to inherit the shared processor contract
- Updated `photo_editor/filters/filter_base.py` to inherit the shared processor contract
- Updated `photo_editor/core/layer.py` so attached processors are typed as shared image processors rather than generic objects

#### Why this mattered

Adjustments and filters were effectively the same kind of thing at the contract level. Giving them one shared abstraction reduced duplication and made later controller and layer typing improvements possible.

#### Result

The codebase now treats adjustments and filters as the same family of processor under `photo_editor/processors/ImageProcessor`.

### Phase 3: FilterController deduplication

After the processor contract existed, duplicated add/edit logic inside `FilterController` was consolidated.

#### What changed

- Updated `photo_editor/ui/controllers/filter_ctrl.py`
- Introduced shared internal helpers for adding and editing processor-backed layers

#### Why this mattered

Before this change, adjustment-layer and filter-layer operations had parallel code paths with near-identical layer creation and editing behavior. The controller became smaller and more predictable once that duplication was removed.

#### Result

`FilterController` now uses one processor-layer flow for both adjustments and filters.

### Phase 4: ControllerBase and ControllerContext

The controller layer then got its first explicit boundary.

#### What changed

- Added `photo_editor/ui/controllers/base.py`
- Added exports for the base infrastructure in `photo_editor/ui/controllers/__init__.py`
- Migrated controllers onto `ControllerBase` incrementally

#### Why this mattered

Controllers were heavily dependent on `MainWindow`, but the worst part was not the existence of access itself. The worst part was the lack of any narrow, repeatable boundary for shared operations. `ControllerContext` created a smaller surface for common document, render, panel, and command flows.

#### Result

Controllers now prefer `ControllerContext` for shared operations like refresh, invalidate, panel refresh, command execution, zoom-to-fit, status messages, async execution, and layer-panel basics.

### Phase 5: Document session extraction

Open-document and tab state was moved out of ad hoc main-window tracking.

#### What changed

- Added `photo_editor/ui/document_session.py`
- Updated `photo_editor/ui/main_window.py`
- Updated `photo_editor/ui/controllers/document_ctrl.py`
- Updated `photo_editor/ui/controllers/drop_ctrl.py`
- Updated `photo_editor/ui/file_tab_bar.py`

#### Why this mattered

Multi-document state is real application state. It should not be hidden as loose lists and incidental tab bookkeeping on `MainWindow`.

#### Result

`DocumentSession` is now the owner of open-document tab/session state.

### Phase 6: App-level UI signals

Cross-controller coordination was then moved toward an explicit event model.

#### What changed

- Added `photo_editor/ui/app_signals.py`
- Updated `photo_editor/ui/main_window.py` to wire signal handlers centrally
- Updated `CanvasController`, `LayerController`, `SelectionController`, `ToolController`, `ViewController`, `ColorController`, and `ShortcutController` to use signals where appropriate

#### Behaviors moved toward signals

- Selection overlay refresh
- Transform box refresh
- Properties panel refresh
- Vector boolean toolbar refresh
- History refresh
- Canvas update requests
- Brush cursor refresh
- Transform panel refresh
- Channels panel refresh
- Duplicate-selection dispatch
- Clone preview dispatch
- Layer-panel processor actions
- Text overlay and text hover dispatch
- Text-editing shortcut toggling
- Tool selection handoff from controller logic

#### Why this mattered

Controllers were previously coordinating by reaching into each other or into widgets directly. App-level signals made these coordination paths explicit and easier to evolve.

#### Result

Cross-controller UI sync now has an explicit coordination mechanism instead of relying entirely on hidden direct calls.

### Phase 7: Controller migration completion

The remaining feature controllers were moved onto the same base contract.

#### Controllers fully on `ControllerBase` by the end of this session

- `DocumentController`
- `FilterController`
- `DropController`
- `LayerController`
- `CanvasController`
- `SelectionController`
- `ToolController`
- `ViewController`
- `ColorController`
- `ShortcutController`
- `CropController`
- `GradientController`
- `TextController`
- `TransformController`
- `VectorController`

#### Why this mattered

The mixed model was itself a maintenance problem. Once every controller used the same base/context boundary, future cleanup could focus on behavior and dependencies instead of inconsistent controller structure.

#### Result

The controller layer now has one shared structural model.

### Phase 8: Effects moved onto the shared processor contract

After adjustments and filters were unified, effects were brought under the same processor abstraction.

#### What changed

- Updated `photo_editor/effects/effect_base.py`
- Added `tests/test_effects.py`

#### Why this mattered

Effects were the last major parallel abstraction that still looked like an image processor but did not share the common contract.

#### Result

Effects now share `ImageProcessor` semantics for parameters and apply behavior.

### Phase 9: Effects pipeline clarified as a separate runtime boundary

After contract unification, the architecture still needed to answer a separate question: should effects be merged conceptually with layer-owned processors or remain a distinct runtime chain?

#### Decision made in this session

Effects remain a separate runtime post-process pipeline.

#### What changed

- Updated `photo_editor/effects/effects_pipeline.py`
- Updated `photo_editor/effects/__init__.py`
- Added `tests/test_effects_pipeline.py`
- Updated `ARCHITECTURE.md`

#### Why this mattered

The contract is shared, but the ownership model is different.

- Adjustment/filter layers are part of document structure.
- `EffectsPipeline` is an ordered enable/disable post-process chain.

Treating them as identical would have created conceptual confusion even after the contract was unified.

#### Result

The repository now explicitly distinguishes between shared processor contract and runtime ownership model.

### Phase 10: Rasterize guard extraction

Rasterization prompts for painting onto text layers were moved out of controller-to-controller coupling.

#### What changed

- Extracted shared rasterization policy into a dedicated helper module
- Updated `CanvasController` and `LayerController` to use it
- Added `tests/test_rasterize_guard.py`

#### Why this mattered

CanvasController had been calling into LayerController just to ask whether a rasterization warning should be shown. That was a poor dependency shape for something that is really shared UI policy.

#### Result

Rasterization checks became shared policy instead of controller-local behavior being reused by another controller.

### Phase 11: Vector UI-state extraction

Vector preview and pick-segment state coordination was removed from controller internals and placed behind a helper boundary.

#### What changed

- Added vector UI-state helpers
- Updated `photo_editor/ui/controllers/vector_ctrl.py`
- Added `tests/test_vector_ui_state.py`

#### Why this mattered

VectorController had direct private canvas mutations for boolean previews and pick-segments mode. Extracting that behavior reduced inline widget-private state handling.

#### Result

Vector-specific canvas/property state coordination now lives behind explicit helper functions.

### Phase 12: Selection and guide UI-state extraction

Repeated panel/canvas state sync was extracted into dedicated helpers.

#### What changed

- Added selection overlay helper module
- Added guide propagation helper module
- Updated `SelectionController` and `ViewController`
- Added `tests/test_selection_ui_state.py`
- Added `tests/test_guide_ui_state.py`

#### Why this mattered

Repeated UI sync should not be scattered across controller bodies. It becomes harder to reason about and easier to duplicate incorrectly.

#### Result

Selection overlay and guide propagation are now explicit shared UI-state behavior.

### Phase 13: Layer-panel helper extraction

LayerController was still one of the largest remaining controller hotspots. The next step was pulling its panel-specific state logic out.

#### What changed

- Added layer-panel helper module
- Moved panel-selection sync logic there
- Moved panel-to-stack selection mapping there
- Moved reorder math there
- Added `tests/test_layer_panel_state.py`

#### Why this mattered

LayerController was mixing command orchestration with layers-panel synchronization and reorder translation logic. Those are not the same concern.

#### Result

LayerController is smaller, and panel-specific state logic is no longer buried inside it.

### Phase 14: Blend-preview state localization

Temporary blend-mode hover preview state was moved off `MainWindow`.

#### What changed

- Removed `MainWindow._blend_preview_original`
- Moved the temporary state into `LayerController`

#### Why this mattered

Temporary interaction state should stay local to the owning controller unless it is truly shared application state.

#### Result

`MainWindow` now owns less incidental controller state.

### Phase 15: Resize logic extraction

LayerController had dialog-triggered resize logic that mixed UI input collection with document mutation details.

#### What changed

- Added `photo_editor/core/services/document_resize.py`
- Updated `LayerController` to call the resize service instead of embedding mutation logic
- Added `tests/test_document_resize.py`

#### Why this mattered

Canvas resize and image resize are document operations. Controllers should gather parameters and trigger refresh, not implement resizing details inline.

#### Result

Resize mutation logic now lives in a focused core service.

### Phase 16: Package structure cleanup into `services`

Several extracted helpers had initially landed at the root of `photo_editor/ui` and `photo_editor/core`. That was an acceptable intermediate step but not a good long-term structure.

#### What changed

Created:

- `photo_editor/ui/services/`
- `photo_editor/core/services/`

Moved UI helper modules into `photo_editor/ui/services/`:

- `guide_ui_state.py`
- `layer_panel_state.py`
- `rasterize_guard.py`
- `selection_ui_state.py`
- `vector_ui_state.py`

Moved the resize service into `photo_editor/core/services/`:

- `document_resize.py`

Updated package exports:

- `photo_editor/ui/services/__init__.py`
- `photo_editor/core/services/__init__.py`

Updated imports across controllers and tests.

Updated package docs:

- `photo_editor/ui/__init__.py`
- `photo_editor/core/__init__.py`
- `ARCHITECTURE.md`

#### Why this mattered

The original complaint here was valid: new files were being dumped in place. A flat package root full of extracted helpers is only slightly better than having controller bloat. Services needed a real package home.

#### Result

Shared UI support is now grouped under `photo_editor/ui/services`, and extracted document operations are grouped under `photo_editor/core/services`.

## Important Files Added Or Introduced During This Session

The following additions or structural extractions were the key architecture artifacts from this session.

### New or newly central packages

- `photo_editor/registries/`
- `photo_editor/processors/`
- `photo_editor/ui/services/`
- `photo_editor/core/services/`

### Key modules added or introduced as architecture anchors

- `photo_editor/processors/image_processor.py`
- `photo_editor/ui/controllers/base.py`
- `photo_editor/ui/document_session.py`
- `photo_editor/ui/app_signals.py`
- `photo_editor/ui/services/rasterize_guard.py`
- `photo_editor/ui/services/vector_ui_state.py`
- `photo_editor/ui/services/selection_ui_state.py`
- `photo_editor/ui/services/guide_ui_state.py`
- `photo_editor/ui/services/layer_panel_state.py`
- `photo_editor/core/services/document_resize.py`

## Files Significantly Changed

This is not every file touched, but it captures the most important ones.

### Core and processor model

- `photo_editor/core/document.py`
- `photo_editor/core/layer.py`
- `photo_editor/adjustments/adjustment_base.py`
- `photo_editor/filters/filter_base.py`
- `photo_editor/effects/effect_base.py`
- `photo_editor/effects/effects_pipeline.py`

### UI architecture

- `photo_editor/ui/main_window.py`
- `photo_editor/ui/filter_runner.py`
- `photo_editor/ui/controllers/document_ctrl.py`
- `photo_editor/ui/controllers/filter_ctrl.py`
- `photo_editor/ui/controllers/layer_ctrl.py`
- `photo_editor/ui/controllers/canvas_ctrl.py`
- `photo_editor/ui/controllers/selection_ctrl.py`
- `photo_editor/ui/controllers/tool_ctrl.py`
- `photo_editor/ui/controllers/view_ctrl.py`
- `photo_editor/ui/controllers/color_ctrl.py`
- `photo_editor/ui/controllers/shortcut_ctrl.py`
- `photo_editor/ui/controllers/text_ctrl.py`
- `photo_editor/ui/controllers/vector_ctrl.py`
- `photo_editor/ui/controllers/crop_ctrl.py`
- `photo_editor/ui/controllers/gradient_ctrl.py`
- `photo_editor/ui/controllers/transform_ctrl.py`
- `photo_editor/ui/controllers/drop_ctrl.py`

### Documentation

- `ARCHITECTURE.md`
- `photo_editor/ui/__init__.py`
- `photo_editor/core/__init__.py`

## Validation Strategy

This session used focused regression testing after structural milestones instead of broad untargeted test runs after every small edit.

### Focused suites added during the session

- `tests/test_registries.py`
- `tests/test_processors.py`
- `tests/test_controller_base.py`
- `tests/test_document_session.py`
- `tests/test_app_signals.py`
- `tests/test_effects.py`
- `tests/test_effects_pipeline.py`
- `tests/test_rasterize_guard.py`
- `tests/test_vector_ui_state.py`
- `tests/test_selection_ui_state.py`
- `tests/test_guide_ui_state.py`
- `tests/test_layer_panel_state.py`
- `tests/test_document_resize.py`

### Progression of validation size during the session

The focused architecture suite grew over time as more boundaries were extracted.

- 17 tests passing after effects and signal work
- 20 tests passing after rasterize helper and more UI-state extraction
- 21 tests passing after full controller-base adoption
- 26 tests passing after effects-pipeline and vector UI-state additions
- 30 tests passing after selection and guide helper extraction
- 33 tests passing after layer-panel helper extraction
- 35 tests passing after document-resize extraction and service reorganization

### Focused command used by the end of the session

`e:/OXM/Projects/PhotoEditor/.venv/Scripts/python.exe -m pytest tests/test_adjustments.py tests/test_registries.py tests/test_processors.py tests/test_controller_base.py tests/test_document_session.py tests/test_app_signals.py tests/test_effects.py tests/test_effects_pipeline.py tests/test_rasterize_guard.py tests/test_vector_ui_state.py tests/test_selection_ui_state.py tests/test_guide_ui_state.py tests/test_layer_panel_state.py tests/test_document_resize.py`

## Resulting Structure After This Session

The codebase now has the following architecture shape.

### Processor and restoration boundaries

- Processor lookup is registry-based.
- Document restore does not depend on UI modules.
- Adjustments, filters, and effects share a processor contract.
- Effects remain a separate runtime pipeline even though they share that contract.

### Controller boundaries

- All controllers use `ControllerBase`.
- Shared controller behavior goes through `ControllerContext` where practical.
- Cross-controller UI coordination prefers `AppSignals`.
- Temporary interaction state is kept local to controllers rather than stored globally on `MainWindow`.

### UI helper boundaries

- Shared controller-support helpers live under `photo_editor/ui/services/`.
- Shared document operations extracted from controllers live under `photo_editor/core/services/`.
- Repeated panel/canvas state sync is no longer scattered inline in as many controllers.

## What Was Not Fully Solved Yet

This refactor session improved the architecture substantially, but it did not finish every possible cleanup.

### Remaining hotspots

1. `LayerController` is still one of the largest controllers and still mixes several concerns, especially layer-style dialog orchestration and some node-tool coordination.
2. Some controllers still reach into `MainWindow` widgets directly for behaviors that may later deserve more context helpers or service boundaries.
3. `EffectsPipeline` is now conceptually clarified, but a larger future decision remains: where its runtime owner should live if it becomes a first-class feature.
4. Panel and menu definitions are still relatively broad and could eventually be broken into smaller feature-local registration modules.

## Rules Established By This Session

These rules are now implicit architecture policy unless a future refactor deliberately changes them.

1. Do not put processor lookup back into UI modules.
2. Do not store temporary controller interaction state on `MainWindow` unless it is truly shared application state.
3. Do not add new shared controller-support helpers at the root of `photo_editor/ui`; put them under `photo_editor/ui/services/`.
4. Do not add new shared document operations at the root of `photo_editor/core`; put them under `photo_editor/core/services/` when they are truly cross-feature services.
5. Prefer extracting shared behavior behind small helper or service modules before attempting broad controller rewrites.
6. Keep architectural refactors behavior-preserving and verify them with targeted regression tests.

## Quick Summary

The most important net effect of this session was not a single feature. It was the replacement of implicit structure with explicit structure.

Before this session:

- lookup lived in UI code
- processors were split into parallel abstractions
- controllers had no common boundary
- UI synchronization was scattered
- session state was too loose
- extracted helpers had no home

After this session:

- registries own processor lookup
- `ImageProcessor` defines the shared processor contract
- all controllers share `ControllerBase`
- `ControllerContext` defines a narrower shared controller surface
- `DocumentSession` owns open-document tab/session state
- `AppSignals` owns more cross-controller UI coordination
- `ui/services` and `core/services` provide structured homes for extracted support logic
- the focused architecture regression suite documents and protects the new boundaries

## Related Documents

- `ARCHITECTURE.md` — current architecture baseline and future direction
- `REFACTORING_HISTORY.md` — this session-level detailed factorization history
