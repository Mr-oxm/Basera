# Layers Panel — Architecture & Reasoning

> Living document capturing the design, data-flow, and rationale for every
> component of the layers panel.  Consult this before making changes.

---

## Table of Contents

1. [File Map](#file-map)
2. [Data Model (Layer)](#data-model)
3. [Display Order](#display-order)
4. [Panel Refresh Pipeline](#refresh-pipeline)
5. [Drag & Drop System](#drag-and-drop)
6. [Drop Commit & Signal Routing](#drop-commit)
7. [Controller & Command Wiring](#controller)
8. [Compositor Integration](#compositor)
9. [Move Tool — Pseudo-Group Transforms](#move-tool)
10. [Constants & Roles Quick-Reference](#constants)
11. [Common Pitfalls & Gotchas](#gotchas)

---

<a id="file-map"></a>
## 1. File Map

| File | Purpose |
|------|---------|
| `base.py` | Shared constants (`ROW_HEIGHT`, `INDENT_WIDTH`, `ROLE_*`), palette colours, `toolbar_btn()` helper |
| `drag_manager.py` | `DragState` dataclass (mutable ref), `DropMode` enum, pure-function helpers (`get_drop_mode`, `get_drop_index`, `infer_target_depth`, `is_descendant_of`) |
| `drag_overlay.py` | `DragOverlay(QWidget)` — transparent overlay painting all drag visuals (gap line, mode badge, drag chip).  Never re-renders the layer tree. |
| `layer_delegate.py` | `LayerItemDelegate(QStyledItemDelegate)` — paints selection highlight behind each row |
| `layer_item.py` | `LayerItemWidget(QWidget)` — single row: thumbnail, name, visibility eye, lock, collapse arrow, clipping badge.  Signals: `visibility_clicked`, `lock_clicked`, `collapse_clicked`, `rename_finished` |
| `layer_list.py` | `LayerListWidget(QListWidget)` — core pointer-driven drag & drop.  Owns `DragState`, `DragOverlay`.  Emits drop signals. |
| `panel.py` | `LayersPanel(QWidget)` — top-level panel: header (opacity/blend), list, toolbar.  Builds display order, owns refresh logic, forwards signals. |
| `thumbnails.py` | LRU-cached thumbnail generation (`make_thumbnail`, `make_group_thumbnail`).  Max 256 entries. |
| `blend_combo.py` | `BlendModeCombo(QComboBox)` — hover-preview blend mode selector |
| `icons.py` | Re-exports from `photo_editor/ui/icons/layers.py` |
| `__init__.py` | Package export: `LayersPanel` |

**External files that participate in the layers panel pipeline:**

| File | Role |
|------|------|
| `ui/controllers/layer_ctrl.py` | Wires panel signals → commands → document mutations → refresh |
| `commands/layer/*.py` | Atomic layer commands (`ReorderLayersCommand`, `MoveLayerCommand`, `DropAsMaskCommand`, etc.) |
| `core/layer.py` | `Layer` dataclass — single unit of the compositing stack |
| `core/layer_stack.py` | `LayerStack` — ordered list + hierarchy mutations (`reparent`, `reorder_by_ids`, `reposition_before`) |
| `engine/compositor.py` | Renders the layer stack to canvas; handles groups, `regular_children`, `clips_parent`, `mask_layers` |
| `tools/move/move_tool.py` | Move/resize/rotate — treats non-group parents with children as pseudo-groups |
| `tools/move/hit_test.py` | Bounding-box + handle hit-testing for transforms |

---

<a id="data-model"></a>
## 2. Data Model (`Layer`)

Key fields on `core/layer.py`:

```
name, id, width, height, layer_type: LayerType
visible, locked, opacity, blend_mode, position
parent_id: str | None          # None = root level
children: list[str]            # child layer IDs
mask_layers: list[str]         # mask-type child IDs
clipping_mask: bool            # clips to layer below (Photoshop-style)
clips_parent: bool             # child whose alpha clips the parent
ex_parent_id: str | None       # stale parent for detached mask scope
```

### Child/Parent Relationships

A child layer can be attached in **four** distinct roles:

| Role | `parent_id` | Listed in | `layer_type` | Compositor behaviour |
|------|------------|-----------|-------------|---------------------|
| **Group child** | group.id | `parent.children` | any | Rendered by `_composite_group` |
| **Mask child** | parent.id | `parent.mask_layers` | MASK | `get_combined_mask` → luminance → multiply parent alpha |
| **Regular child** (append) | parent.id | `parent.children` | RASTER, SHAPE, etc. | Alpha clipped to parent's alpha: `child.a *= parent.a` |
| **Clips-parent child** (thumbnail drop) | parent.id | `parent.children` | any (unchanged) | **Parent** alpha clipped to **child's** alpha: `parent.a *= child.a` |

### On Unparent

When reparenting to `None`:
- `clipping_mask` → `False`
- `clips_parent` → `False`
- MASK type: `ex_parent_id` → `None`

---

<a id="display-order"></a>
## 3. Display Order (`_build_display_order`)

Turns the flat `LayerStack` into a tree-ordered list of `(layer, indent)` tuples and separator markers.

**Algorithm:**
1. Pre-classify every child layer into three dicts keyed by `parent_id`:
   - `mask_children_of` — MASK type
   - `adj_children_of` — ADJUSTMENT / FILTER type
   - `children_of` — everything else (raster, shape, group, etc.)

2. For each root-level layer (top to bottom = `reversed(layers)`):
   - Emit `(layer, 0)`
   - Call `_emit_children(layer.id, indent=1, ...)`

3. `_emit_children(lid, indent, ...)` emits children in **sections**:
   - **Masks** (if `masks_collapsed` does NOT contain lid)
   - Separator
   - **Adjustment/Filter children**
   - Separator
   - **Regular children** (recurse for nested groups)

4. All three sections share the same collapse toggle (`_collapsed_masks`).

**Collapse state** is stored in two sets:
- `_collapsed_groups: set[str]` — hides group contents (the group's own children)
- `_collapsed_masks: set[str]` — hides the mask/adj/regular child sections

---

<a id="refresh-pipeline"></a>
## 4. Panel Refresh Pipeline

```
Document mutation
    ↓
LayerController calls ctx.refresh()
    ↓
LayersPanel.refresh(document, thumbnails=True)
    ↓
┌─ _build_display_order() → list[(layer, indent) | (None, indent, "sep")]
├─ Compare new_ids vs _row_layer_ids  →  structure_changed?
│
├─ IF NOT structure_changed AND NOT thumbnails:
│     _sync_row_states()  (visibility + lock icons only)
│     _sync_active()
│     return  ← FAST PATH #1
│
├─ IF NOT structure_changed AND thumbnails:
│     _sync_row_states()
│     _sync_thumbnails()  (update pixmaps in existing widgets)
│     _sync_active()
│     return  ← FAST PATH #2
│
└─ ELSE (structure changed):
      Pre-compute parent category sets (O(N) once):
        _parents_with_adj, _parents_with_mask, _parents_with_raster
      _list.clear()
      For each entry:
        Create QListWidgetItem + LayerItemWidget
        Set all ROLE_* data on item
        Generate thumbnail (cached)
        Connect signals
      _sync_active()
```

**Performance notes:**
- `has_adj_children`, `has_mask_children`, `has_raster_children` use
  pre-computed O(1) set lookups (not `any()` scans).
- Thumbnails are LRU-cached by `layer.id`.  Only regenerated on cache miss.
- `_sync_thumbnails()` updates pixmaps on existing widgets — no widget
  teardown/rebuild.
- `_sync_row_states()` only touches visibility + lock button state.

---

<a id="drag-and-drop"></a>
## 5. Drag & Drop System

### Design Principles

1. **Zero re-renders during drag** — all visual feedback is painted by
   `DragOverlay` reading from the mutable `DragState` ref.
2. **Pointer events, not Qt DnD** — `mousePressEvent`, `mouseMoveEvent`,
   `mouseReleaseEvent` on `LayerListWidget`.
3. **Signals on commit only** — the tree is never modified until mouse release.

### Lifecycle

```
mousePressEvent
  → Record start position, layer IDs, source_parent_id
  → DragState prepared but drag_started=False

mouseMoveEvent (repeated)
  → Update pointer_x/pointer_y
  → If distance > 5px threshold:
    → drag_started=True
    → viewport.grabMouse()
    → Ghost dragged rows (30% opacity)
  → _update_drop_target(px, py)
  → Schedule overlay repaint

mouseReleaseEvent
  → viewport.releaseMouse()
  → If drag_started: _commit_drop()
  → Reset DragState, clear ghost rows, hide overlay
```

### Drop Target Computation (`_update_drop_target`)

1. Find target row under pointer.
2. **Validation:**
   - Self-drop → invalid (red flash)
   - Drag onto own descendant → invalid
3. **Unparent detection** (source is nested):
   - **Trigger 1:** `infer_target_depth(px) < source_depth` (pointer dragged left of source indent)
   - **Trigger 2:** Target row is root-level (indent 0) AND pointer is in the reorder zone (top/bottom 25%)
   - Either trigger → force `REORDER` mode with `target_depth = 0`
4. **Drop mode** from `get_drop_mode()`:
   - Pointer on thumbnail → **CLIP**
   - Top/bottom 25% of row → **REORDER**
   - Middle 50% + right of indent → **NEST**

### `infer_target_depth(pointer_x)`

```python
depth = int(pointer_x / INDENT_WIDTH)   # INDENT_WIDTH = 20
return max(0, min(depth, MAX_INDENT_DEPTH))
```

---

<a id="drop-commit"></a>
## 6. Drop Commit & Signal Routing

`_commit_drop()` translates drag state into signals based on `DropMode` and
the source layer's type flags (`ROLE_IS_MASK`, `ROLE_IS_ADJ_FILTER`):

### REORDER Mode

| Source nested? | `target_depth` | Signal |
|---------------|---------------|--------|
| No | any | `layers_reordered(ids, insert_index)` |
| Yes | 0 | `layers_unparented(ids, insert_index)` |
| Yes | > 0 | `layers_reordered(ids, insert_index)` |

### NEST Mode

| Source type | Signal | Effect |
|-------------|--------|--------|
| MASK | `mask_dropped_on_layer(sid, target_id)` | Attach to `target.mask_layers` |
| ADJ/FILTER | `adj_filter_dropped_on_layer(sid, target_id)` | Reparent as adj/filter child |
| Other | `layers_dropped_in_group(ids, target_id)` | Reparent to `target.children` |

### CLIP Mode (thumbnail drop)

| Source type | Signal | Effect |
|-------------|--------|--------|
| MASK | `mask_dropped_on_layer` | Attach to mask list |
| ADJ/FILTER | `adj_filter_dropped_on_layer` | Attach as adj/filter child |
| Other | `layer_dropped_as_mask(sid, target_id)` | → `DropAsMaskCommand`: sets `clips_parent=True` on child, adds to `target.children` |

---

<a id="controller"></a>
## 7. Controller & Command Wiring (`layer_ctrl.py`)

The controller's `wire()` method connects every panel signal to a handler.

### Key Handlers

| Handler | Command / Action |
|---------|-----------------|
| `on_layers_reordered(ids, row)` | `ReorderLayersCommand(reordered_stack_order(...))` |
| `on_layers_reparented(ids, group_id)` | `MoveLayerCommand(ids, parent_id=group_id)` |
| `on_layers_unparented(ids, row)` | Atomic: `reparent(ids, None)` + `reorder_by_ids(new_order)` + snapshot |
| `on_mask_dropped_on_layer(m, t)` | `AttachMaskToLayerCommand(m, t)` |
| `on_adj_filter_dropped_on_layer(a, t)` | `AttachAdjustmentToLayerCommand(a, t)` |
| `on_layer_dropped_as_mask(l, t)` | `DropAsMaskCommand(l, t)` |
| `on_opacity(float)` | Direct mutation: `active_layer.opacity = ...` |
| `on_blend_mode(BlendMode)` | Direct mutation: `active_layer.blend_mode = ...` |

### Unparent Flow (special)

```python
def on_layers_unparented(self, layer_ids, target_visual_row):
    display_ids = self.ctx.layer_row_ids()          # snapshot BEFORE mutation
    new_stack_order = reordered_stack_order(
        display_ids, layer_ids, target_visual_row)
    doc.layers.reparent(layer_ids, None)            # detach
    doc.layers.reorder_by_ids(new_stack_order)      # place at correct position
    doc.save_snapshot("Unparent Layer")
    doc.mark_dirty()
    self.ctx.refresh()
```

Why atomic? `reparent(ids, None)` always appends layers at the end of the
stack (top).  Without `reorder_by_ids`, the unparented layer would jump to
the top instead of landing at the visual drop position.

---

<a id="compositor"></a>
## 8. Compositor Integration

### Root-level compositing loop

The compositor iterates root-level visible layers (bottom to top) and handles:

1. **`clipping_mask` layers** — clip to `prev_img` alpha (Photoshop-style clip chain)
2. **`clips_parent` children** — child alpha restricts parent visibility (reverse clip)
3. **Normal layers** — standard blend
4. **Regular children** — alpha clipped to parent: `child.a *= parent.a`

### `clips_parent` compositing path

```python
if _has_clip_child:
    parent_placed = place_pixels(parent)
    for child in regular_children[layer.id]:
        if child.clips_parent:
            c_placed = place_pixels(child)
            parent_placed[..., 3:4] *= c_placed[..., 3:4]  # parent clipped to child
    blend(canvas, parent_placed, ...)   # blend the clipped parent
    # Then composite remaining non-clip children normally
    for child in regular_children[layer.id]:
        if not child.clips_parent:
            c_placed = ...
            c_placed[..., 3:4] *= parent_placed[..., 3:4]  # child clipped to parent
            blend(canvas, c_placed, ...)
```

### Regular children (non-group parents)

Built in collection phase:
```python
regular_children: dict[str, list[Layer]] = {}
for l in layers:
    if (l.parent_id and l.visible
        and l.parent_id not in group_ids
        and l.layer_type not in (ADJ, FILTER, MASK)
        and l.id not in mask_layer_ids
        and l.id not in adj_child_ids):
        regular_children.setdefault(l.parent_id, []).append(l)
```

---

<a id="move-tool"></a>
## 9. Move Tool — Pseudo-Group Transforms

When a non-group parent has children (`layer.children` is non-empty), the
move tool treats it as a **pseudo-group**: the parent itself becomes one of
the "group children", and all transforms propagate to every member.

**Mask children** (`layer.mask_layers`) are **excluded** from `_group_children`
and collected into `_mask_children` instead.  After every group resize / rotate
frame, `_sync_mask_transforms(layer)` copies the parent's transform params
(scale, angle, position) to each mask child, keeping them pixel-aligned.

### Setup (`on_press`)

```python
if layer.children:                        # uses the list, NOT parent_id scan
    mask_child_ids = set(layer.mask_layers)
    _group_children = [layer] + [regular children — mask IDs excluded]
    _mask_children  = [mask children from layer.mask_layers]
    _group_orig_bbox = union of transformable members (skip ADJ/FILTER)
    return  # skip single-layer setup
```

### MOVE

```python
if _group_children:
    for child in _group_children:
        child.position = orig + (dx, dy)
else:
    layer.position = orig + (dx, dy)
# Mask children always follow the parent
for mc in _mask_children:
    mc.position = orig + (dx, dy)
```

> **Gotcha:** The parent is IN `_group_children`.  The old code did
> `layer.position = ...` AND iterated `_group_children`, causing double-move.
> Now the direct assignment is skipped when `_group_children` is populated.

### RESIZE / ROTATE

`_apply_group_resize` and `_apply_group_rotate` iterate `_group_children`
(which includes the parent).  After each call, `_sync_mask_transforms(layer)`
is invoked so mask children mirror the parent's updated transform.

On release, `compute_display(fast=False)` runs for both `_group_children`
(RASTER members) and `_mask_children`, and vector transforms are committed
for any SHAPE children via `_commit_group_vector_transforms`.

### Hit-Test (`hit_test.py`)

For non-group parents with children, `bbox()` returns the union of parent +
regular children positions (mask children excluded).  Hit-test uses the
axis-aligned path (no rotation transform applied to the union bbox).

---

<a id="constants"></a>
## 10. Constants & Roles Quick-Reference

### Layout Constants (`base.py`)

| Constant | Value | Used by |
|----------|-------|---------|
| `ROW_HEIGHT` | 48 | Item size hint |
| `THUMB_SIZE` | 36 | Thumbnail pixmap |
| `SEP_HEIGHT` | 6 | Separator row |
| `INDENT_WIDTH` | 20 | Indent per depth level |
| `MAX_INDENT_DEPTH` | 5 | Max visual nesting |
| `GAP_ANIM_MS` | 120 | Gap animation duration |
| `EJECT_HOLD_MS` | 400 | Eject hold-to-trigger |

### Qt Item Data Roles

| Role | Type | Set on | Read by |
|------|------|--------|---------|
| `ROLE_LAYER_ID` | `str` | panel.refresh | layer_list, drag_manager |
| `ROLE_IS_GROUP` | `bool` | panel.refresh | layer_list |
| `ROLE_INDENT` | `int` | panel.refresh | layer_list, drag_overlay |
| `ROLE_PARENT_ID` | `str` | panel.refresh | layer_list (unparent check) |
| `ROLE_IS_MASK` | `bool` | panel.refresh | layer_list (_commit_drop routing) |
| `ROLE_IS_ADJ_FILTER` | `bool` | panel.refresh | layer_list (_commit_drop routing) |
| `ROLE_IS_SEP` | `bool` | panel.refresh | layer_delegate, layer_list |
| `ROLE_IS_CLIPPED` | `bool` | panel.refresh | layer_item (badge) |

---

<a id="gotchas"></a>
## 11. Common Pitfalls & Gotchas

### Double-move in pseudo-groups
The active layer is added to `_group_children` for non-group parents.
The MOVE handler must NOT update `layer.position` directly when
`_group_children` is populated — the loop handles it.

### Mask children excluded from pseudo-group
The pseudo-group detection uses `bool(layer.children)` — NOT a
`parent_id` scan.  Mask children (`layer.mask_layers`) are excluded from
`_group_children` and collected into `_mask_children`.  If they were
included in the pseudo-group they would transform independently instead
of staying pixel-aligned with the parent.  `_sync_mask_transforms` is
called after every group resize / rotate frame to copy the parent's
transform.  The `bbox()` hit-test also excludes mask children so the
interaction zone matches the visual content.

### `reparent(ids, None)` always appends at stack top
When unparenting, the controller must compute `reordered_stack_order()`
BEFORE calling `reparent()`, then call `reorder_by_ids()` to place the
layers at the correct visual position.

### `clips_parent` vs `clipping_mask`
- `clipping_mask` — Photoshop-style: the layer clips to the layer **below** it.
- `clips_parent` — Affinity-style: the **child** layer's alpha clips the **parent**.
Both are cleared on unparent.

### Thumbnail drop → child (not mask conversion)
`DropAsMaskCommand` does NOT change `layer_type` to MASK.  It adds the
dropped layer to `target.children` with `clips_parent = True`.  The
compositor handles the clipping via `_has_clip_child` path.

### Panel rebuild performance
Avoid triggering structure-changed paths.  Use `thumbnails=False` for
lightweight refreshes.  The `_sync_row_states()` and `_sync_thumbnails()`
fast paths avoid re-creating all QListWidgetItems.

### Three child sections share one collapse toggle
`_collapsed_masks` controls visibility of ALL three child sections
(masks, adjustments, regular children) for non-group parents.  This is
intentional — prevents a non-group parent from having three separate
collapsible sections.

### `_build_display_order` separator placement
Separators are emitted between sections only when both adjacent sections
have content.  The algorithm checks `has_masks and has_adj`, etc.

### infer_target_depth threshold
`int(pointer_x / 20)` means the user must drag to x < 20 for depth 0.
This is supplemented by Trigger 2: if the pointer hovers a root-level
row in its reorder zone, unparent is also activated.

### Multi-selection bbox in hit_test
When multiple layers are selected, `hit_test()` uses `multi_bbox()` —
the axis-aligned union — skipping the rotation branch entirely.

---

*Updated: 2026-03-10*
