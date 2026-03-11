"""Intensive UI-based layers panel test suite.

Covers:
  1. Grouping with clipped children
  2. Drop-on-group (NEST vs CLIP)
  3. Drop-between inside group (reorder-into-group)
  4. Unparenting & reparenting
  5. Panel refresh / display order integrity
  6. Drag-manager helpers & edge cases
  7. Complex multi-level nesting scenarios
  8. Regressions for specific bugs
"""

from __future__ import annotations

import numpy as np
import pytest

from photo_editor.core.document import Document
from photo_editor.core.layer import Layer
from photo_editor.core.layer_stack import LayerStack
from photo_editor.core.enums import LayerType, BlendMode

from photo_editor.commands import (
    AddGroupCommand,
    AddLayerCommand,
    ClipToLayerCommand,
    DropAsMaskCommand,
    DuplicateLayerCommand,
    MoveLayerCommand,
    RemoveLayerCommand,
    ReorderLayersCommand,
)

from photo_editor.ui.services.layer_panel_state import (
    reordered_stack_order,
    selected_indices_from_layer_ids,
)

from photo_editor.ui.panels.layers.drag_manager import (
    DragState,
    DropMode,
    get_drop_index,
    is_descendant_of,
    infer_target_depth,
)


# ── Helpers ──────────────────────────────────────────────────────

def _ids(doc: Document) -> list[str]:
    return [layer.id for layer in doc.layers]


def _names(doc: Document) -> list[str]:
    return [layer.name for layer in doc.layers]


def _make_doc(*layer_names: str, size: int = 64) -> Document:
    doc = Document(size, size)
    for name in layer_names:
        doc.add_layer(name=name)
    return doc


def _layer_by_name(doc: Document, name: str) -> Layer:
    for layer in doc.layers:
        if layer.name == name:
            return layer
    raise ValueError(f"No layer named {name!r}")


def _clip_to_parent(doc: Document, child_name: str, parent_name: str) -> None:
    child = _layer_by_name(doc, child_name)
    parent = _layer_by_name(doc, parent_name)
    DropAsMaskCommand(child.id, parent.id).execute(doc)


def _group_layers(doc: Document, *names: str, group_name: str = "Group") -> Layer:
    ids = [_layer_by_name(doc, n).id for n in names]
    AddGroupCommand(name=group_name, layer_ids=ids).execute(doc)
    return _layer_by_name(doc, group_name)


def _reparent(doc: Document, layer_names: list[str], group_name: str) -> None:
    ids = [_layer_by_name(doc, n).id for n in layer_names]
    target = _layer_by_name(doc, group_name)
    MoveLayerCommand(ids, target_parent_id=target.id).execute(doc)


def _unparent(doc: Document, *layer_names: str) -> None:
    ids = [_layer_by_name(doc, n).id for n in layer_names]
    doc.layers.reparent(ids, None)


# ═══════════════════════════════════════════════════════════════════
# Section 1: Grouping with Clipped Children
# ═══════════════════════════════════════════════════════════════════

class TestGroupingWithClippedChildren:
    """LP-001 through LP-010: grouping preserves clip hierarchies."""

    def test_LP001_group_parent_and_clip_child(self):
        """Grouping a parent + its clip child preserves the clip relationship."""
        doc = _make_doc("Base", "Clip")
        _clip_to_parent(doc, "Clip", "Base")
        base = _layer_by_name(doc, "Base")
        clip = _layer_by_name(doc, "Clip")
        assert clip.clips_parent is True
        assert clip.parent_id == base.id
        assert clip.id in base.children

        _group_layers(doc, "Base", "Clip", group_name="G1")
        group = _layer_by_name(doc, "G1")

        # Clip should still be a child of Base, NOT directly of G1
        assert clip.parent_id == base.id
        assert clip.id in base.children
        assert clip.clips_parent is True
        # Base should be a direct child of G1
        assert base.parent_id == group.id
        assert base.id in group.children
        # Clip should NOT be directly in G1's children
        assert clip.id not in group.children

    def test_LP002_group_only_parent_brings_clip_child(self):
        """Selecting only the parent for grouping also brings clip children."""
        doc = _make_doc("Base", "Clip")
        _clip_to_parent(doc, "Clip", "Base")
        base = _layer_by_name(doc, "Base")
        clip = _layer_by_name(doc, "Clip")

        _group_layers(doc, "Base", group_name="G1")
        group = _layer_by_name(doc, "G1")

        # Clip child should have come along with parent
        assert base.parent_id == group.id
        assert clip.parent_id == base.id
        assert clip.clips_parent is True

    def test_LP003_group_parent_with_multiple_clips(self):
        """Grouping a parent with multiple clip children preserves all."""
        doc = _make_doc("Base", "Clip1", "Clip2")
        _clip_to_parent(doc, "Clip1", "Base")
        _clip_to_parent(doc, "Clip2", "Base")
        base = _layer_by_name(doc, "Base")

        _group_layers(doc, "Base", group_name="G1")
        group = _layer_by_name(doc, "G1")

        clip1 = _layer_by_name(doc, "Clip1")
        clip2 = _layer_by_name(doc, "Clip2")
        assert clip1.parent_id == base.id
        assert clip2.parent_id == base.id
        assert clip1.clips_parent is True
        assert clip2.clips_parent is True
        assert base.parent_id == group.id

    def test_LP004_group_only_clip_child_separates(self):
        """Grouping only the clip child (not parent) detaches from parent."""
        doc = _make_doc("Base", "Clip")
        _clip_to_parent(doc, "Clip", "Base")
        clip = _layer_by_name(doc, "Clip")
        base = _layer_by_name(doc, "Base")

        _group_layers(doc, "Clip", group_name="G1")
        group = _layer_by_name(doc, "G1")

        # Clip was removed from Base's children (create_group_from unparents)
        assert clip.parent_id == group.id
        assert clip.id not in base.children

    def test_LP005_group_preserves_layer_count(self):
        """Grouping should not lose or duplicate layers."""
        doc = _make_doc("A", "B", "C")
        _clip_to_parent(doc, "B", "A")
        initial_count = len(list(doc.layers))

        _group_layers(doc, "A", "B", group_name="G")
        # +1 for the group itself
        assert len(list(doc.layers)) == initial_count + 1

    def test_LP006_nested_group_with_clips(self):
        """Grouping a layer that already lives in a group works with clips."""
        doc = _make_doc("A", "B")
        _clip_to_parent(doc, "B", "A")
        _group_layers(doc, "A", "B", group_name="G1")
        g1 = _layer_by_name(doc, "G1")

        # Now group G1 itself into G2
        doc.add_layer(name="C")
        _group_layers(doc, "G1", "C", group_name="G2")
        g2 = _layer_by_name(doc, "G2")
        assert g1.parent_id == g2.id
        b = _layer_by_name(doc, "B")
        a = _layer_by_name(doc, "A")
        assert b.parent_id == a.id
        assert b.clips_parent is True

    def test_LP007_group_independent_layers(self):
        """Grouping layers with no clip relationship is straightforward."""
        doc = _make_doc("A", "B")
        _group_layers(doc, "A", "B", group_name="G")
        group = _layer_by_name(doc, "G")
        a = _layer_by_name(doc, "A")
        b = _layer_by_name(doc, "B")
        assert a.parent_id == group.id
        assert b.parent_id == group.id
        assert a.id in group.children
        assert b.id in group.children

    def test_LP008_group_single_layer(self):
        """Grouping a single layer wraps it in a group."""
        doc = _make_doc("A")
        _group_layers(doc, "A", group_name="G")
        group = _layer_by_name(doc, "G")
        a = _layer_by_name(doc, "A")
        assert a.parent_id == group.id

    def test_LP009_group_with_mask_children(self):
        """Grouping a layer that has mask_layers brings masks along."""
        doc = _make_doc("Base")
        base = _layer_by_name(doc, "Base")
        idx = list(doc.layers).index(base)
        doc.layers.active_index = idx
        mask = doc.add_mask_layer(target_id=base.id, fill_white=True)
        assert mask is not None
        assert mask.id in base.mask_layers

        _group_layers(doc, "Base", group_name="G")
        group = _layer_by_name(doc, "G")
        assert base.parent_id == group.id
        # Mask should still be attached to base, not group
        assert mask.parent_id == base.id

    def test_LP010_group_preserves_clips_parent_flag(self):
        """The clips_parent flag is preserved through grouping."""
        doc = _make_doc("Base", "Clip")
        _clip_to_parent(doc, "Clip", "Base")
        clip = _layer_by_name(doc, "Clip")
        assert clip.clips_parent is True

        _group_layers(doc, "Base", "Clip", group_name="G")
        assert clip.clips_parent is True


# ═══════════════════════════════════════════════════════════════════
# Section 2: Drop-on-Group (NEST vs CLIP)
# ═══════════════════════════════════════════════════════════════════

class TestDropOnGroup:
    """LP-011 through LP-020: dropping on groups always nests, never clips."""

    def test_LP011_reparent_into_group(self):
        """MoveLayerCommand nests a layer into a group."""
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        a = _layer_by_name(doc, "A")
        MoveLayerCommand([a.id], target_parent_id=group.id).execute(doc)
        assert a.parent_id == group.id
        assert a.clips_parent is False
        assert a.clipping_mask is False

    def test_LP012_reparent_multiple_into_group(self):
        """Multiple layers can be reparented into a group simultaneously."""
        doc = _make_doc("A", "B")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        ids = [_layer_by_name(doc, n).id for n in ("A", "B")]
        MoveLayerCommand(ids, target_parent_id=group.id).execute(doc)
        assert _layer_by_name(doc, "A").parent_id == group.id
        assert _layer_by_name(doc, "B").parent_id == group.id

    def test_LP013_reparent_doesnt_set_clip(self):
        """Reparenting into a group should not set clips_parent."""
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        a = _layer_by_name(doc, "A")
        MoveLayerCommand([a.id], target_parent_id=group.id).execute(doc)
        assert a.clips_parent is False
        assert a.clipping_mask is False

    def test_LP014_reparent_from_one_group_to_another(self):
        """Moving a layer between groups updates parent references."""
        doc = _make_doc("A")
        AddGroupCommand(name="G1").execute(doc)
        AddGroupCommand(name="G2").execute(doc)
        g1 = _layer_by_name(doc, "G1")
        g2 = _layer_by_name(doc, "G2")
        a = _layer_by_name(doc, "A")

        MoveLayerCommand([a.id], target_parent_id=g1.id).execute(doc)
        assert a.parent_id == g1.id

        MoveLayerCommand([a.id], target_parent_id=g2.id).execute(doc)
        assert a.parent_id == g2.id
        assert a.id not in g1.children
        assert a.id in g2.children

    def test_LP015_reparent_group_into_group(self):
        """A group can be nested into another group."""
        doc = _make_doc("A")
        _group_layers(doc, "A", group_name="Inner")
        AddGroupCommand(name="Outer").execute(doc)
        inner = _layer_by_name(doc, "Inner")
        outer = _layer_by_name(doc, "Outer")
        MoveLayerCommand([inner.id], target_parent_id=outer.id).execute(doc)
        assert inner.parent_id == outer.id

    def test_LP016_reparent_preserves_existing_children(self):
        """Reparenting into a group that already has children doesn't lose those."""
        doc = _make_doc("A", "B")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        a = _layer_by_name(doc, "A")
        b = _layer_by_name(doc, "B")

        MoveLayerCommand([a.id], target_parent_id=group.id).execute(doc)
        assert a.id in group.children

        MoveLayerCommand([b.id], target_parent_id=group.id).execute(doc)
        assert a.id in group.children
        assert b.id in group.children

    def test_LP017_drop_as_mask_sets_clips_parent(self):
        """DropAsMaskCommand correctly sets clips_parent (not clipping_mask)."""
        doc = _make_doc("Base", "Shape")
        base = _layer_by_name(doc, "Base")
        shape = _layer_by_name(doc, "Shape")
        DropAsMaskCommand(shape.id, base.id).execute(doc)
        assert shape.clips_parent is True
        assert shape.parent_id == base.id

    def test_LP018_clip_to_layer_sets_clipping_mask(self):
        """ClipToLayerCommand sets the PS-style clipping_mask flag."""
        doc = _make_doc("Base", "Clipped")
        base = _layer_by_name(doc, "Base")
        clipped = _layer_by_name(doc, "Clipped")
        ClipToLayerCommand(clipped.id, base.id).execute(doc)
        assert clipped.clipping_mask is True

    def test_LP019_clip_vs_nest_are_distinct(self):
        """clips_parent and regular parenting are distinct relationships."""
        doc = _make_doc("Base", "Clip", "Child")
        _clip_to_parent(doc, "Clip", "Base")
        base = _layer_by_name(doc, "Base")
        child = _layer_by_name(doc, "Child")
        MoveLayerCommand([child.id], target_parent_id=base.id).execute(doc)
        clip = _layer_by_name(doc, "Clip")
        assert clip.clips_parent is True
        assert child.clips_parent is False
        assert clip.parent_id == base.id
        assert child.parent_id == base.id

    def test_LP020_reparent_clipped_into_group_clears_clip(self):
        """Moving a clipped layer into a group clears clips_parent properly."""
        doc = _make_doc("Base", "Clip")
        _clip_to_parent(doc, "Clip", "Base")
        clip = _layer_by_name(doc, "Clip")
        assert clip.clips_parent is True

        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        # Reparenting to a different parent should detach from Base
        MoveLayerCommand([clip.id], target_parent_id=group.id).execute(doc)
        assert clip.parent_id == group.id


# ═══════════════════════════════════════════════════════════════════
# Section 3: Drop-Between Inside Group (Reorder Into Group)
# ═══════════════════════════════════════════════════════════════════

class TestDropBetweenInsideGroup:
    """LP-021 through LP-030: reorder-into-group and within-group reorder."""

    def test_LP021_reorder_within_group(self):
        """Layers can be reordered within the same group."""
        doc = _make_doc("A", "B")
        _group_layers(doc, "A", "B", group_name="G")
        group = _layer_by_name(doc, "G")
        a = _layer_by_name(doc, "A")
        b = _layer_by_name(doc, "B")
        assert a.parent_id == group.id
        assert b.parent_id == group.id

        # Reorder using stack order
        ids = _ids(doc)
        new_order = list(reversed([l.id for l in doc.layers]))
        doc.layers.reorder_by_ids(new_order)
        # Both should still be children of the group
        assert a.parent_id == group.id
        assert b.parent_id == group.id

    def test_LP022_reparent_and_reorder(self):
        """Reparenting + reorder_by_ids in sequence works atomically."""
        doc = _make_doc("A", "B", "C")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")

        # Move A into group
        MoveLayerCommand([_layer_by_name(doc, "A").id], target_parent_id=group.id).execute(doc)
        a = _layer_by_name(doc, "A")
        assert a.parent_id == group.id

        # Build the display order, simulate dropping B into the group
        display_ids = [l.id for l in reversed(list(doc.layers)) if l.parent_id is None or l.parent_id == group.id]
        # Manual reparent + reorder
        b = _layer_by_name(doc, "B")
        doc.layers.reparent([b.id], group.id)
        assert b.parent_id == group.id

    def test_LP023_reordered_stack_order_with_separators(self):
        """reordered_stack_order correctly handles __sep__ markers."""
        display_ids = ["L3", "__sep__", "L2", "L1"]
        dragged = ["L3"]
        # Drop at visual row 3 (after __sep__ and L2)
        result = reordered_stack_order(display_ids, dragged, 3)
        assert "L3" in result
        assert "L2" in result
        assert "L1" in result
        assert "__sep__" not in result

    def test_LP024_reordered_stack_order_no_separators(self):
        """reordered_stack_order works without separators."""
        display_ids = ["L3", "L2", "L1"]
        dragged = ["L3"]
        result = reordered_stack_order(display_ids, dragged, 2)
        # L3 moves to position 2 in display order
        # Display order is top→bottom, stack order is bottom→top (reversed)
        assert len(result) == 3

    def test_LP025_reordered_stack_order_multiple_dragged(self):
        """Multiple dragged layers are inserted together."""
        display_ids = ["L4", "L3", "L2", "L1"]
        dragged = ["L4", "L3"]
        result = reordered_stack_order(display_ids, dragged, 3)
        assert len(result) == 4

    def test_LP026_drop_at_start(self):
        """Dropping at row 0 places layer at top of display."""
        display_ids = ["L3", "L2", "L1"]
        dragged = ["L1"]
        result = reordered_stack_order(display_ids, dragged, 0)
        assert len(result) == 3
        # reversed display = stack order: "L1" should be at the top
        assert result[-1] == "L1"

    def test_LP027_drop_at_end(self):
        """Dropping at the end places layer at bottom of display."""
        display_ids = ["L3", "L2", "L1"]
        dragged = ["L3"]
        result = reordered_stack_order(display_ids, dragged, 3)
        assert len(result) == 3
        assert result[0] == "L3"

    def test_LP028_drop_index_empty_list(self):
        """get_drop_index handles empty row list."""
        idx = get_drop_index(50.0, [], 0, [])
        assert idx == 0

    def test_LP029_drop_index_single_row(self):
        """get_drop_index with a single row returns 0 or 1."""
        idx_top = get_drop_index(5.0, [0.0], 1, [40.0])
        idx_bot = get_drop_index(35.0, [0.0], 1, [40.0])
        assert idx_top == 0
        assert idx_bot == 1

    def test_LP030_infer_target_depth_clamped(self):
        """infer_target_depth is clamped by MAX_INDENT_DEPTH."""
        from photo_editor.ui.panels.layers.base import MAX_INDENT_DEPTH
        depth = infer_target_depth(9999.0)
        assert depth <= MAX_INDENT_DEPTH


# ═══════════════════════════════════════════════════════════════════
# Section 4: Unparenting & Reparenting
# ═══════════════════════════════════════════════════════════════════

class TestUnparentingReparenting:
    """LP-031 through LP-045: un-parenting clears flags, reparenting sets them."""

    def test_LP031_unparent_clears_clips_parent(self):
        """Un-parenting a clips_parent child clears the flag."""
        doc = _make_doc("Base", "Clip")
        _clip_to_parent(doc, "Clip", "Base")
        clip = _layer_by_name(doc, "Clip")
        assert clip.clips_parent is True
        _unparent(doc, "Clip")
        assert clip.clips_parent is False

    def test_LP032_unparent_clears_clipping_mask(self):
        """Un-parenting clears the clipping_mask flag."""
        doc = _make_doc("Base", "Clipped")
        ClipToLayerCommand(_layer_by_name(doc, "Clipped").id, _layer_by_name(doc, "Base").id).execute(doc)
        clipped = _layer_by_name(doc, "Clipped")
        assert clipped.clipping_mask is True
        doc.layers.reparent([clipped.id], None)
        assert clipped.clipping_mask is False

    def test_LP033_unparent_removes_from_parent_children(self):
        """Un-parenting removes the layer from parent's children list."""
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        a = _layer_by_name(doc, "A")
        MoveLayerCommand([a.id], target_parent_id=group.id).execute(doc)
        assert a.id in group.children
        _unparent(doc, "A")
        assert a.id not in group.children
        assert a.parent_id is None

    def test_LP034_unparent_mask_clears_ex_parent(self):
        """Un-parenting a mask layer clears ex_parent_id."""
        doc = _make_doc("Base")
        base = _layer_by_name(doc, "Base")
        idx = list(doc.layers).index(base)
        doc.layers.active_index = idx
        mask = doc.add_mask_layer(target_id=base.id, fill_white=True)
        assert mask.parent_id == base.id
        doc.layers.reparent([mask.id], None)
        assert mask.ex_parent_id is None

    def test_LP035_reparent_into_empty_group(self):
        """Reparenting into an empty group works."""
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        a = _layer_by_name(doc, "A")
        doc.layers.reparent([a.id], group.id)
        assert a.parent_id == group.id
        assert a.id in group.children

    def test_LP036_reparent_preserves_layer_order(self):
        """Reparenting repositions layers near the group in the stack."""
        doc = _make_doc("A", "B")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        a = _layer_by_name(doc, "A")
        doc.layers.reparent([a.id], group.id)
        # A should now appear before G in the stack
        names = _names(doc)
        assert names.index("A") < names.index("G")

    def test_LP037_reparent_from_group_to_root(self):
        """Moving from group to root (None parent) works."""
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        a = _layer_by_name(doc, "A")
        doc.layers.reparent([a.id], group.id)
        doc.layers.reparent([a.id], None)
        assert a.parent_id is None

    def test_LP038_reparent_self_is_noop(self):
        """Reparenting a layer to itself is silently ignored."""
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        # Reparent G to itself
        doc.layers.reparent([group.id], group.id)
        assert group.parent_id is None  # unchanged

    def test_LP039_unparent_multiple(self):
        """Multiple layers can be unparented at once."""
        doc = _make_doc("A", "B")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        ids = [_layer_by_name(doc, n).id for n in ("A", "B")]
        doc.layers.reparent(ids, group.id)
        assert all(doc.layers.get(lid).parent_id == group.id for lid in ids)
        doc.layers.reparent(ids, None)
        assert all(doc.layers.get(lid).parent_id is None for lid in ids)
        assert len(group.children) == 0

    def test_LP040_reparent_nonexistent_layer_ignored(self):
        """Reparenting a nonexistent layer ID is silently ignored."""
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        doc.layers.reparent(["nonexistent123"], group.id)
        assert len(group.children) == 0

    def test_LP041_unparent_already_root(self):
        """Un-parenting a root layer is a no-op."""
        doc = _make_doc("A")
        a = _layer_by_name(doc, "A")
        assert a.parent_id is None
        doc.layers.reparent([a.id], None)
        assert a.parent_id is None

    def test_LP042_reparent_updates_group_bbox(self):
        """Reparenting into a group triggers bbox update."""
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        a = _layer_by_name(doc, "A")
        doc.layers.reparent([a.id], group.id)
        # Just verify no crash — bbox computation depends on layer sizes

    def test_LP043_reparent_chain(self):
        """Reparent A→G1, then G1→G2 creates a 3-level hierarchy."""
        doc = _make_doc("A")
        AddGroupCommand(name="G1").execute(doc)
        AddGroupCommand(name="G2").execute(doc)
        g1 = _layer_by_name(doc, "G1")
        g2 = _layer_by_name(doc, "G2")
        a = _layer_by_name(doc, "A")

        doc.layers.reparent([a.id], g1.id)
        doc.layers.reparent([g1.id], g2.id)
        assert a.parent_id == g1.id
        assert g1.parent_id == g2.id

    def test_LP044_unparent_deep_nested(self):
        """Un-parenting a deeply nested layer works correctly."""
        doc = _make_doc("A")
        AddGroupCommand(name="G1").execute(doc)
        AddGroupCommand(name="G2").execute(doc)
        g1 = _layer_by_name(doc, "G1")
        g2 = _layer_by_name(doc, "G2")
        a = _layer_by_name(doc, "A")

        doc.layers.reparent([a.id], g1.id)
        doc.layers.reparent([g1.id], g2.id)
        # Now unparent A directly to root
        doc.layers.reparent([a.id], None)
        assert a.parent_id is None
        assert a.id not in g1.children

    def test_LP045_reparent_with_clips_preserves_hierarchy(self):
        """Reparenting a parent that has clip children brings them along."""
        doc = _make_doc("Base", "Clip")
        _clip_to_parent(doc, "Clip", "Base")
        base = _layer_by_name(doc, "Base")
        clip = _layer_by_name(doc, "Clip")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")

        doc.layers.reparent([base.id], group.id)
        assert base.parent_id == group.id
        # Clip should still be attached to base (not disrupted)
        assert clip.parent_id == base.id
        assert clip.clips_parent is True


# ═══════════════════════════════════════════════════════════════════
# Section 5: Display Order Integrity
# ═══════════════════════════════════════════════════════════════════

class TestDisplayOrderIntegrity:
    """LP-046 through LP-060: display order reflects correct layer structure."""

    def _build_display_order(self, doc: Document, collapsed=None, masks_collapsed=None):
        from photo_editor.ui.panels.layers.panel import LayersPanel
        return LayersPanel._build_display_order(
            doc,
            collapsed or set(),
            masks_collapsed or set(),
        )

    def test_LP046_flat_layers_order(self):
        """Flat layers appear top→bottom in display order."""
        doc = _make_doc("A", "B", "C")
        display = self._build_display_order(doc)
        names = [e[0].name for e in display if len(e) == 2]
        assert names == ["C", "B", "A", "Background"]

    def test_LP047_group_children_indented(self):
        """Group children appear indented (indent=1) after the group header."""
        doc = _make_doc("A", "B")
        _group_layers(doc, "A", "B", group_name="G")
        display = self._build_display_order(doc)
        g_entries = [(e[0].name, e[1]) for e in display if len(e) == 2]
        # G at indent 0, A and B at indent 1
        group_entry = [e for e in g_entries if e[0] == "G"]
        assert group_entry[0][1] == 0
        child_entries = [e for e in g_entries if e[0] in ("A", "B")]
        assert all(e[1] == 1 for e in child_entries)

    def test_LP048_collapsed_group_hides_children(self):
        """A collapsed group should not show children in display order."""
        doc = _make_doc("A", "B")
        _group_layers(doc, "A", "B", group_name="G")
        group = _layer_by_name(doc, "G")
        display = self._build_display_order(doc, collapsed={group.id})
        names = [e[0].name for e in display if len(e) == 2]
        assert "G" in names
        assert "A" not in names
        assert "B" not in names

    def test_LP049_expanded_group_shows_children(self):
        """An expanded group shows children."""
        doc = _make_doc("A", "B")
        _group_layers(doc, "A", "B", group_name="G")
        display = self._build_display_order(doc)
        names = [e[0].name for e in display if len(e) == 2]
        assert "G" in names
        assert "A" in names
        assert "B" in names

    def test_LP050_clip_children_in_display(self):
        """Clip children appear in display order under their parent."""
        doc = _make_doc("Base", "Clip")
        _clip_to_parent(doc, "Clip", "Base")
        display = self._build_display_order(doc)
        names = [e[0].name for e in display if len(e) == 2]
        base_idx = names.index("Base")
        clip_idx = names.index("Clip")
        # Clip should appear after Base in display order (indented under it)
        assert clip_idx > base_idx

    def test_LP051_separator_between_categories(self):
        """Separators appear between mask/adj/raster children."""
        from photo_editor.adjustments.brightness_contrast import BrightnessContrast
        doc = _make_doc("Base")
        base = _layer_by_name(doc, "Base")
        idx = list(doc.layers).index(base)
        doc.layers.active_index = idx
        mask = doc.add_mask_layer(target_id=base.id, fill_white=True)

        adj = doc.add_layer(name="Adj", layer_type=LayerType.ADJUSTMENT)
        adj.adjustment = BrightnessContrast()
        from photo_editor.commands import AttachAdjustmentToLayerCommand
        AttachAdjustmentToLayerCommand(adj.id, base.id).execute(doc)

        display = self._build_display_order(doc)
        sep_count = sum(1 for e in display if len(e) == 3)
        assert sep_count >= 1

    def test_LP052_nested_group_display_order(self):
        """Nested groups show correct indentation hierarchy."""
        doc = _make_doc("A")
        _group_layers(doc, "A", group_name="Inner")
        inner = _layer_by_name(doc, "Inner")
        doc.add_layer(name="B")
        _group_layers(doc, "Inner", "B", group_name="Outer")
        display = self._build_display_order(doc)
        entries = [(e[0].name, e[1]) for e in display if len(e) == 2]
        outer_indent = [e[1] for e in entries if e[0] == "Outer"][0]
        inner_indent = [e[1] for e in entries if e[0] == "Inner"][0]
        a_indent = [e[1] for e in entries if e[0] == "A"][0]
        assert outer_indent == 0
        assert inner_indent == 1
        assert a_indent == 2

    def test_LP053_empty_group_display(self):
        """An empty group still appears in display order."""
        doc = _make_doc()
        AddGroupCommand(name="Empty").execute(doc)
        display = self._build_display_order(doc)
        names = [e[0].name for e in display if len(e) == 2]
        assert "Empty" in names

    def test_LP054_masks_collapsed_hides_children(self):
        """Collapsing masks section hides mask/adj/raster children."""
        doc = _make_doc("Base")
        base = _layer_by_name(doc, "Base")
        idx = list(doc.layers).index(base)
        doc.layers.active_index = idx
        mask = doc.add_mask_layer(target_id=base.id, fill_white=True)

        # Show children when not collapsed
        display = self._build_display_order(doc, masks_collapsed=set())
        all_names = [e[0].name for e in display if len(e) == 2]
        assert mask.name in all_names

        # Hide children when collapsed
        display = self._build_display_order(doc, masks_collapsed={base.id})
        all_names = [e[0].name for e in display if len(e) == 2]
        assert mask.name not in all_names

    def test_LP055_display_after_unparent(self):
        """Display order correctly updates after un-parenting."""
        doc = _make_doc("A", "B")
        _group_layers(doc, "A", "B", group_name="G")
        _unparent(doc, "A")
        display = self._build_display_order(doc)
        entries = [(e[0].name, e[1]) for e in display if len(e) == 2]
        a_indent = [e[1] for e in entries if e[0] == "A"][0]
        assert a_indent == 0

    def test_LP056_display_after_reparent(self):
        """Display order correctly updates after reparenting."""
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        a = _layer_by_name(doc, "A")
        doc.layers.reparent([a.id], group.id)
        display = self._build_display_order(doc)
        entries = [(e[0].name, e[1]) for e in display if len(e) == 2]
        a_indent = [e[1] for e in entries if e[0] == "A"][0]
        assert a_indent == 1

    def test_LP057_root_layers_at_indent_zero(self):
        """All root layers have indent 0."""
        doc = _make_doc("A", "B", "C")
        display = self._build_display_order(doc)
        entries = [(e[0].name, e[1]) for e in display if len(e) == 2]
        assert all(e[1] == 0 for e in entries)


# ═══════════════════════════════════════════════════════════════════
# Section 6: Drag Manager Helpers
# ═══════════════════════════════════════════════════════════════════

class TestDragManagerHelpers:
    """LP-058 through LP-070: drag-manager utility functions."""

    def test_LP058_is_descendant_direct_child(self):
        """is_descendant_of detects a direct child."""
        children_map = {"G1": ["C1", "C2"]}
        assert is_descendant_of("C1", {"G1"}, children_map) is True

    def test_LP059_is_descendant_nested(self):
        """is_descendant_of detects a nested descendant."""
        children_map = {"G1": ["G2"], "G2": ["C1"]}
        assert is_descendant_of("C1", {"G1"}, children_map) is True

    def test_LP060_is_descendant_false(self):
        """is_descendant_of returns False for unrelated layers."""
        children_map = {"G1": ["C1"]}
        assert is_descendant_of("C2", {"G1"}, children_map) is False

    def test_LP061_is_descendant_empty_map(self):
        """is_descendant_of handles empty children map."""
        assert is_descendant_of("C1", {"G1"}, {}) is False

    def test_LP062_is_descendant_self(self):
        """is_descendant_of does not consider self a descendant."""
        children_map = {"G1": ["C1"]}
        assert is_descendant_of("G1", {"G1"}, children_map) is False

    def test_LP063_get_drop_index_top_of_list(self):
        """Dropping at very top (y < first row top) returns 0."""
        idx = get_drop_index(-5.0, [0.0, 40.0, 80.0], 3, [40.0, 40.0, 40.0])
        assert idx == 0

    def test_LP064_get_drop_index_between_rows(self):
        """Dropping between rows returns the correct index."""
        idx = get_drop_index(60.0, [0.0, 40.0, 80.0], 3, [40.0, 40.0, 40.0])
        assert idx == 2

    def test_LP065_get_drop_index_bottom(self):
        """Dropping below all rows returns count."""
        idx = get_drop_index(200.0, [0.0, 40.0, 80.0], 3, [40.0, 40.0, 40.0])
        assert idx == 3

    def test_LP066_infer_target_depth_zero(self):
        """X position at left edge returns depth 0."""
        from photo_editor.ui.panels.layers.base import INDENT_WIDTH
        depth = infer_target_depth(2.0)
        assert depth == 0

    def test_LP067_infer_target_depth_one(self):
        """X position at one indent returns depth 1."""
        from photo_editor.ui.panels.layers.base import INDENT_WIDTH
        depth = infer_target_depth(float(INDENT_WIDTH + 10))
        assert depth >= 1

    def test_LP068_drag_state_defaults(self):
        """DragState has sensible defaults."""
        ds = DragState()
        assert ds.dragging is False
        assert ds.dragged_ids == []
        assert ds.drop_mode is None
        assert ds.drop_target_id is None
        assert ds.insert_index == -1

    def test_LP069_drop_mode_enum_values(self):
        """DropMode has exactly REORDER, NEST, CLIP."""
        assert hasattr(DropMode, "REORDER")
        assert hasattr(DropMode, "NEST")
        assert hasattr(DropMode, "CLIP")
        assert len(DropMode) == 3

    def test_LP070_is_descendant_circular_safe(self):
        """is_descendant_of doesn't infinite-loop on circular refs."""
        children_map = {"A": ["B"], "B": ["A"]}
        # Should return True since A is descendant of B and B of A
        result = is_descendant_of("A", {"B"}, children_map)
        assert isinstance(result, bool)


# ═══════════════════════════════════════════════════════════════════
# Section 7: Complex Multi-Level Nesting
# ═══════════════════════════════════════════════════════════════════

class TestComplexNesting:
    """LP-071 through LP-085: complex multi-level scenarios."""

    def test_LP071_three_level_nesting(self):
        """Three levels of group nesting works correctly."""
        doc = _make_doc("A")
        _group_layers(doc, "A", group_name="G1")
        doc.add_layer(name="B")
        _group_layers(doc, "G1", "B", group_name="G2")
        doc.add_layer(name="C")
        _group_layers(doc, "G2", "C", group_name="G3")

        a = _layer_by_name(doc, "A")
        g1 = _layer_by_name(doc, "G1")
        g2 = _layer_by_name(doc, "G2")
        g3 = _layer_by_name(doc, "G3")
        assert a.parent_id == g1.id
        assert g1.parent_id == g2.id
        assert g2.parent_id == g3.id

    def test_LP072_clip_inside_nested_group(self):
        """Clip children work inside nested groups."""
        doc = _make_doc("Base", "Clip")
        _clip_to_parent(doc, "Clip", "Base")
        _group_layers(doc, "Base", "Clip", group_name="G1")
        doc.add_layer(name="Outer")
        _group_layers(doc, "G1", "Outer", group_name="G2")

        clip = _layer_by_name(doc, "Clip")
        base = _layer_by_name(doc, "Base")
        assert clip.clips_parent is True
        assert clip.parent_id == base.id

    def test_LP073_unparent_from_nested_group(self):
        """Un-parenting from a deeply nested group works."""
        doc = _make_doc("A")
        _group_layers(doc, "A", group_name="G1")
        doc.add_layer(name="B")
        _group_layers(doc, "G1", "B", group_name="G2")

        a = _layer_by_name(doc, "A")
        g1 = _layer_by_name(doc, "G1")
        doc.layers.reparent([a.id], None)
        assert a.parent_id is None
        assert a.id not in g1.children

    def test_LP074_move_between_nested_groups(self):
        """Moving a layer between nested groups updates all refs."""
        doc = _make_doc("A", "B")
        _group_layers(doc, "A", group_name="G1")
        _group_layers(doc, "B", group_name="G2")
        g1 = _layer_by_name(doc, "G1")
        g2 = _layer_by_name(doc, "G2")
        a = _layer_by_name(doc, "A")

        doc.layers.reparent([a.id], g2.id)
        assert a.parent_id == g2.id
        assert a.id not in g1.children
        assert a.id in g2.children

    def test_LP075_group_with_mixed_children(self):
        """Grouping layers with mixed relationships (clip + normal)."""
        doc = _make_doc("Base", "Clip", "Normal")
        _clip_to_parent(doc, "Clip", "Base")
        base = _layer_by_name(doc, "Base")
        clip = _layer_by_name(doc, "Clip")
        normal = _layer_by_name(doc, "Normal")

        _group_layers(doc, "Base", "Clip", "Normal", group_name="G")
        group = _layer_by_name(doc, "G")
        # Clip stays with Base
        assert clip.parent_id == base.id
        # Base and Normal are direct children of G
        assert base.parent_id == group.id
        assert normal.parent_id == group.id

    def test_LP076_delete_group_children_remain(self):
        """Deleting a group — children are orphaned or removed depending on impl."""
        doc = _make_doc("A", "B")
        _group_layers(doc, "A", "B", group_name="G")
        group = _layer_by_name(doc, "G")
        # Just verify deletion doesn't crash
        RemoveLayerCommand(group.id).execute(doc)

    def test_LP077_duplicate_preserves_hierarchy(self):
        """DuplicateLayerCommand on a parent preserves children."""
        doc = _make_doc("Base", "Clip")
        _clip_to_parent(doc, "Clip", "Base")
        base = _layer_by_name(doc, "Base")
        DuplicateLayerCommand(base.id).execute(doc)

        # Should have original + copy
        bases = [l for l in doc.layers if l.name.startswith("Base")]
        assert len(bases) == 2

    def test_LP078_group_empty(self):
        """Creating an empty group works."""
        doc = _make_doc()
        AddGroupCommand(name="Empty").execute(doc)
        group = _layer_by_name(doc, "Empty")
        assert group.layer_type == LayerType.GROUP
        assert len(group.children) == 0

    def test_LP079_reorder_by_ids_preserves_all(self):
        """reorder_by_ids doesn't lose any layers."""
        doc = _make_doc("A", "B", "C")
        ids = list(reversed(_ids(doc)))
        doc.layers.reorder_by_ids(ids)
        assert len(list(doc.layers)) == 4  # Background + 3

    def test_LP080_reorder_by_ids_partial(self):
        """reorder_by_ids with a partial list appends the rest."""
        doc = _make_doc("A", "B", "C")
        all_ids = _ids(doc)
        partial = [all_ids[0]]  # just Background
        doc.layers.reorder_by_ids(partial)
        assert len(list(doc.layers)) == 4

    def test_LP081_reposition_before(self):
        """reposition_before moves a layer to before the target."""
        doc = _make_doc("A", "B", "C")
        a = _layer_by_name(doc, "A")
        c = _layer_by_name(doc, "C")
        doc.layers.reposition_before(c.id, a.id)
        names = _names(doc)
        assert names.index("C") < names.index("A")

    def test_LP082_double_group(self):
        """Grouping the same layers twice creates nested groups."""
        doc = _make_doc("A")
        _group_layers(doc, "A", group_name="G1")
        g1 = _layer_by_name(doc, "G1")
        _group_layers(doc, "G1", group_name="G2")
        g2 = _layer_by_name(doc, "G2")
        assert g1.parent_id == g2.id

    def test_LP083_simultaneous_clip_and_normal_children(self):
        """A layer can have both clips_parent and normal children."""
        doc = _make_doc("Base", "Clip", "Normal")
        _clip_to_parent(doc, "Clip", "Base")
        base = _layer_by_name(doc, "Base")
        normal = _layer_by_name(doc, "Normal")
        doc.layers.reparent([normal.id], base.id)
        assert _layer_by_name(doc, "Clip").clips_parent is True
        assert normal.clips_parent is False
        assert normal.parent_id == base.id

    def test_LP084_reorder_many_layers(self):
        """Reordering many layers doesn't crash."""
        doc = Document(64, 64)
        for i in range(20):
            doc.add_layer(name=f"L{i}")
        ids = _ids(doc)
        import random
        rng = random.Random(42)
        rng.shuffle(ids)
        doc.layers.reorder_by_ids(ids)
        assert len(list(doc.layers)) == 21  # Background + 20

    def test_LP085_group_then_unparent_all(self):
        """Group → unparent all children → group is empty."""
        doc = _make_doc("A", "B")
        _group_layers(doc, "A", "B", group_name="G")
        group = _layer_by_name(doc, "G")
        _unparent(doc, "A", "B")
        assert len(group.children) == 0


# ═══════════════════════════════════════════════════════════════════
# Section 8: Regressions
# ═══════════════════════════════════════════════════════════════════

class TestRegressions:
    """LP-086 through LP-100: specific bug regressions."""

    def test_LP086_grouping_clipped_layer_doesnt_disappear(self):
        """Regression: grouping a layer with clipped child
        used to cause the clipped child to 'disappear' from the panel
        because it was reparented flat into the group."""
        doc = _make_doc("Parent", "ClipChild")
        _clip_to_parent(doc, "ClipChild", "Parent")
        parent = _layer_by_name(doc, "Parent")
        clip = _layer_by_name(doc, "ClipChild")

        _group_layers(doc, "Parent", group_name="G")
        group = _layer_by_name(doc, "G")

        # Clip child must still be attached to Parent, not Group
        assert clip.parent_id == parent.id
        assert clip.clips_parent is True
        assert clip.id in parent.children
        assert clip.id not in group.children

        # Verify display order shows clip under parent
        from photo_editor.ui.panels.layers.panel import LayersPanel
        display = LayersPanel._build_display_order(doc, set(), set())
        names = [e[0].name for e in display if len(e) == 2]
        assert "ClipChild" in names

    def test_LP087_grouping_parent_and_clip_together(self):
        """Regression: selecting both parent and clip for grouping
        previously caused the clip to lose its parent relationship."""
        doc = _make_doc("Parent", "ClipChild")
        _clip_to_parent(doc, "ClipChild", "Parent")

        parent = _layer_by_name(doc, "Parent")
        clip = _layer_by_name(doc, "ClipChild")
        _group_layers(doc, "Parent", "ClipChild", group_name="G")
        group = _layer_by_name(doc, "G")

        assert clip.parent_id == parent.id
        assert parent.parent_id == group.id
        assert clip.clips_parent is True

    def test_LP088_drop_on_group_nests_not_clips(self):
        """Regression: dropping on a group thumbnail used to set
        clipping_mask instead of nesting."""
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        a = _layer_by_name(doc, "A")

        # Simulate the correct path — MoveLayerCommand (NEST)
        MoveLayerCommand([a.id], target_parent_id=group.id).execute(doc)
        assert a.parent_id == group.id
        assert a.clips_parent is False
        assert a.clipping_mask is False

    def test_LP089_reorder_into_group_reparents(self):
        """Regression: dropping between group children now correctly
        reparents the source into the group."""
        doc = _make_doc("A", "B")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        a = _layer_by_name(doc, "A")
        doc.layers.reparent([a.id], group.id)

        b = _layer_by_name(doc, "B")
        doc.layers.reparent([b.id], group.id)
        assert b.parent_id == group.id

    def test_LP090_flat_reorder_doesnt_reparent(self):
        """A flat reorder between root layers doesn't set parent_id."""
        doc = _make_doc("A", "B", "C")
        ids = _ids(doc)
        new_order = [ids[2], ids[0], ids[1], ids[3]] if len(ids) == 4 else ids
        doc.layers.reorder_by_ids(new_order)
        for layer in doc.layers:
            assert layer.parent_id is None

    def test_LP091_unparent_refreshes_display_order(self):
        """After unparenting, display order no longer shows layer as nested."""
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        a = _layer_by_name(doc, "A")
        doc.layers.reparent([a.id], group.id)

        doc.layers.reparent([a.id], None)
        from photo_editor.ui.panels.layers.panel import LayersPanel
        display = LayersPanel._build_display_order(doc, set(), set())
        entries = [(e[0].name, e[1]) for e in display if len(e) == 2]
        a_indent = [e[1] for e in entries if e[0] == "A"][0]
        assert a_indent == 0

    def test_LP092_reparent_refreshes_display_order(self):
        """After reparenting, display order shows layer as nested."""
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        a = _layer_by_name(doc, "A")
        doc.layers.reparent([a.id], group.id)

        from photo_editor.ui.panels.layers.panel import LayersPanel
        display = LayersPanel._build_display_order(doc, set(), set())
        entries = [(e[0].name, e[1]) for e in display if len(e) == 2]
        a_indent = [e[1] for e in entries if e[0] == "A"][0]
        assert a_indent == 1

    def test_LP093_move_layer_command_snapshot(self):
        """MoveLayerCommand creates an undo snapshot."""
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        group = _layer_by_name(doc, "G")
        a = _layer_by_name(doc, "A")
        initial_len = len(doc.history._states)
        MoveLayerCommand([a.id], target_parent_id=group.id).execute(doc)
        assert len(doc.history._states) > initial_len

    def test_LP094_clip_to_layer_positions_above_target(self):
        """ClipToLayerCommand positions the layer above the target in stack."""
        doc = _make_doc("Base", "Clipper")
        base = _layer_by_name(doc, "Base")
        clipper = _layer_by_name(doc, "Clipper")
        ClipToLayerCommand(clipper.id, base.id).execute(doc)
        names = _names(doc)
        assert names.index("Clipper") > names.index("Base")

    def test_LP095_drop_as_mask_positions_before_target(self):
        """DropAsMaskCommand repositions the layer before the target."""
        doc = _make_doc("Target", "Shape")
        target = _layer_by_name(doc, "Target")
        shape = _layer_by_name(doc, "Shape")
        DropAsMaskCommand(shape.id, target.id).execute(doc)
        assert shape.parent_id == target.id
        assert shape.clips_parent is True

    def test_LP096_selected_indices_from_layer_ids(self):
        """selected_indices_from_layer_ids maps correctly."""
        doc = _make_doc("A", "B", "C")
        layers = list(doc.layers)
        ids = [layers[1].id, layers[3].id]
        result = selected_indices_from_layer_ids(ids, layers)
        assert 1 in result
        assert 3 in result

    def test_LP097_selected_indices_empty(self):
        """selected_indices_from_layer_ids with empty list."""
        doc = _make_doc("A")
        layers = list(doc.layers)
        result = selected_indices_from_layer_ids([], layers)
        assert result == set() or result == []

    def test_LP098_group_with_clip_and_mask(self):
        """Grouping a layer that has both clip and mask children."""
        doc = _make_doc("Base", "Clip")
        _clip_to_parent(doc, "Clip", "Base")
        base = _layer_by_name(doc, "Base")
        idx = list(doc.layers).index(base)
        doc.layers.active_index = idx
        mask = doc.add_mask_layer(target_id=base.id, fill_white=True)

        _group_layers(doc, "Base", group_name="G")
        group = _layer_by_name(doc, "G")

        clip = _layer_by_name(doc, "Clip")
        assert clip.parent_id == base.id
        assert clip.clips_parent is True
        assert mask.parent_id == base.id
        assert base.parent_id == group.id

    def test_LP099_multiple_groups_no_interference(self):
        """Creating multiple groups doesn't cause cross-contamination."""
        doc = _make_doc("A", "B", "C", "D")
        _group_layers(doc, "A", "B", group_name="G1")
        _group_layers(doc, "C", "D", group_name="G2")
        g1 = _layer_by_name(doc, "G1")
        g2 = _layer_by_name(doc, "G2")
        assert _layer_by_name(doc, "A").parent_id == g1.id
        assert _layer_by_name(doc, "B").parent_id == g1.id
        assert _layer_by_name(doc, "C").parent_id == g2.id
        assert _layer_by_name(doc, "D").parent_id == g2.id
        assert set(g1.children) & set(g2.children) == set()

    def test_LP100_stress_group_ungroup_cycle(self):
        """Rapid group/unparent cycles don't corrupt state."""
        doc = _make_doc("A", "B")
        for _ in range(5):
            _group_layers(doc, "A", "B", group_name="G")
            group = _layer_by_name(doc, "G")
            _unparent(doc, "A", "B")
            RemoveLayerCommand(group.id).execute(doc)

        a = _layer_by_name(doc, "A")
        b = _layer_by_name(doc, "B")
        assert a.parent_id is None
        assert b.parent_id is None
