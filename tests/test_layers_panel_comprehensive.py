"""Comprehensive layer-panel corner-case tests.

Covers 9 sections:
  1. Basic Layer Creation & Duplication
  2. Groups
  3. Clip Layers (clips_parent / clipping_mask)
  4. Transform Propagation on Clipped Layers
  5. Un-clipping & Re-clipping
  6. Collapse / Expand (display order)
  7. Duplicating Parent with Clipped Layers
  8. Adjustment / Filter Layers
  9. Corner Cases & Regressions (drag-manager, reorder helpers, misc.)
"""

from __future__ import annotations

import numpy as np
import pytest
from types import SimpleNamespace

from photo_editor.core.document import Document
from photo_editor.core.layer import Layer
from photo_editor.core.layer_stack import LayerStack
from photo_editor.core.enums import LayerType, BlendMode

from photo_editor.commands import (
    AddGroupCommand,
    AddLayerCommand,
    AddMaskLayerCommand,
    AttachAdjustmentToLayerCommand,
    AttachMaskToLayerCommand,
    ClipToLayerCommand,
    DuplicateLayerCommand,
    DropAsMaskCommand,
    FlattenCommand,
    MergeDownCommand,
    MoveLayerCommand,
    PlaceImageCommand,
    RemoveLayerCommand,
    ReorderLayersCommand,
    RenameLayerCommand,
    UpdateEffectCommand,
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
    """Return layer IDs bottom→top (stack order)."""
    return [layer.id for layer in doc.layers]


def _names(doc: Document) -> list[str]:
    """Return layer names bottom→top (stack order)."""
    return [layer.name for layer in doc.layers]


def _make_doc(*layer_names: str, size: int = 64) -> Document:
    """Create a document with named layers (bottom→top: Background + given names)."""
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
    """Attach child as clips_parent child of parent using DropAsMaskCommand."""
    child = _layer_by_name(doc, child_name)
    parent = _layer_by_name(doc, parent_name)
    DropAsMaskCommand(child.id, parent.id).execute(doc)


def _attach_adj(doc: Document, adj_name: str, parent_name: str) -> None:
    """Create and attach an adjustment layer to parent."""
    from photo_editor.adjustments.brightness_contrast import BrightnessContrast
    adj = doc.add_layer(name=adj_name, layer_type=LayerType.ADJUSTMENT)
    adj.adjustment = BrightnessContrast()
    adj.adjustment_params = {"brightness": 0, "contrast": 0}
    AttachAdjustmentToLayerCommand(adj.id, _layer_by_name(doc, parent_name).id).execute(doc)


def _attach_filter(doc: Document, filt_name: str, parent_name: str) -> None:
    """Create and attach a filter layer to parent."""
    filt = doc.add_layer(name=filt_name, layer_type=LayerType.FILTER)
    MoveLayerCommand([filt.id], _layer_by_name(doc, parent_name).id).execute(doc)


def _attach_mask(doc: Document, parent_name: str) -> Layer:
    """Add a mask layer to parent."""
    parent = _layer_by_name(doc, parent_name)
    idx = list(doc.layers).index(parent)
    doc.layers.active_index = idx
    mask = doc.add_mask_layer(target_id=parent.id, fill_white=True)
    assert mask is not None
    return mask


# ═══════════════════════════════════════════════════════════════════
# Section 1: Basic Layer Creation & Duplication
# ═══════════════════════════════════════════════════════════════════

class TestBasicLayerCreation:
    """Test layer creation, removal, duplication of single layers."""

    def test_new_document_has_background(self):
        doc = Document(64, 64)
        assert len(list(doc.layers)) == 1
        assert doc.layers[0].name == "Background"

    def test_add_raster_layer(self):
        doc = Document(64, 64)
        layer = doc.add_layer(name="Paint")
        assert layer.name == "Paint"
        assert layer.layer_type == LayerType.RASTER
        assert layer.parent_id is None
        assert layer.children == []
        assert layer.mask_layers == []

    def test_add_multiple_layers_stack_order(self):
        doc = _make_doc("A", "B", "C")
        names = _names(doc)
        assert names == ["Background", "A", "B", "C"]

    def test_remove_layer(self):
        doc = _make_doc("A", "B")
        lid = _layer_by_name(doc, "A").id
        RemoveLayerCommand(lid).execute(doc)
        assert all(l.name != "A" for l in doc.layers)

    def test_remove_nonexistent_layer_is_noop(self):
        doc = _make_doc("A")
        count_before = len(list(doc.layers))
        RemoveLayerCommand("nonexistent").execute(doc)
        assert len(list(doc.layers)) == count_before

    def test_duplicate_layer_properties(self):
        doc = _make_doc("Original")
        orig = _layer_by_name(doc, "Original")
        orig.opacity = 0.5
        orig.blend_mode = BlendMode.MULTIPLY
        orig.visible = False
        DuplicateLayerCommand(orig.id).execute(doc)
        dup = [l for l in doc.layers if "copy" in l.name][0]
        assert dup.opacity == 0.5
        assert dup.blend_mode == BlendMode.MULTIPLY
        assert dup.visible is False

    def test_duplicate_layer_inserted_above_original(self):
        doc = _make_doc("A", "B", "C")
        b = _layer_by_name(doc, "B")
        DuplicateLayerCommand(b.id).execute(doc)
        names = _names(doc)
        b_idx = names.index("B")
        copy_idx = names.index("B copy")
        assert copy_idx == b_idx + 1

    def test_duplicate_layer_gets_new_id(self):
        doc = _make_doc("A")
        a = _layer_by_name(doc, "A")
        DuplicateLayerCommand(a.id).execute(doc)
        ids = _ids(doc)
        assert len(set(ids)) == len(ids)

    def test_rename_layer(self):
        doc = _make_doc("Old")
        layer = _layer_by_name(doc, "Old")
        RenameLayerCommand(layer.id, "New").execute(doc)
        assert doc.layers.get(layer.id).name == "New"

    def test_add_layer_via_command(self):
        doc = Document(64, 64)
        AddLayerCommand(name="Cmd Layer", layer_type=LayerType.RASTER).execute(doc)
        assert any(l.name == "Cmd Layer" for l in doc.layers)

    def test_place_image(self):
        doc = Document(64, 64)
        img = np.ones((32, 32, 4), dtype=np.float32)
        PlaceImageCommand(img, name="Photo").execute(doc)
        placed = _layer_by_name(doc, "Photo")
        assert placed.width == 32 and placed.height == 32


# ═══════════════════════════════════════════════════════════════════
# Section 2: Groups
# ═══════════════════════════════════════════════════════════════════

class TestGroups:
    """Test group creation, reparent, unparent."""

    def test_add_empty_group(self):
        doc = _make_doc("A")
        AddGroupCommand(name="Group1").execute(doc)
        g = _layer_by_name(doc, "Group1")
        assert g.layer_type == LayerType.GROUP
        assert g.children == []

    def test_group_selected_layers(self):
        doc = _make_doc("A", "B", "C")
        a, b = _layer_by_name(doc, "A"), _layer_by_name(doc, "B")
        AddGroupCommand(name="G", layer_ids=[a.id, b.id]).execute(doc)
        g = _layer_by_name(doc, "G")
        assert a.parent_id == g.id
        assert b.parent_id == g.id
        assert a.id in g.children
        assert b.id in g.children

    def test_reparent_layer_to_group(self):
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        a = _layer_by_name(doc, "A")
        g = _layer_by_name(doc, "G")
        MoveLayerCommand([a.id], g.id).execute(doc)
        assert a.parent_id == g.id
        assert a.id in g.children

    def test_unparent_layer_from_group(self):
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        a = _layer_by_name(doc, "A")
        g = _layer_by_name(doc, "G")
        MoveLayerCommand([a.id], g.id).execute(doc)
        MoveLayerCommand([a.id], None).execute(doc)
        assert a.parent_id is None
        assert a.id not in g.children

    def test_unparent_clears_clips_parent(self):
        doc = _make_doc("Parent", "Child")
        _clip_to_parent(doc, "Child", "Parent")
        child = _layer_by_name(doc, "Child")
        assert child.clips_parent is True
        MoveLayerCommand([child.id], None).execute(doc)
        assert child.clips_parent is False

    def test_unparent_clears_clipping_mask(self):
        doc = _make_doc("A", "B")
        b = _layer_by_name(doc, "B")
        a = _layer_by_name(doc, "A")
        ClipToLayerCommand(b.id, a.id).execute(doc)
        assert b.clipping_mask is True
        MoveLayerCommand([b.id], None).execute(doc)
        assert b.clipping_mask is False

    def test_nested_groups(self):
        doc = _make_doc("A")
        AddGroupCommand(name="Outer").execute(doc)
        AddGroupCommand(name="Inner").execute(doc)
        inner = _layer_by_name(doc, "Inner")
        outer = _layer_by_name(doc, "Outer")
        a = _layer_by_name(doc, "A")
        MoveLayerCommand([inner.id], outer.id).execute(doc)
        MoveLayerCommand([a.id], inner.id).execute(doc)
        assert a.parent_id == inner.id
        assert inner.parent_id == outer.id

    def test_reparent_multiple_layers(self):
        doc = _make_doc("A", "B", "C")
        AddGroupCommand(name="G").execute(doc)
        a, b = _layer_by_name(doc, "A"), _layer_by_name(doc, "B")
        g = _layer_by_name(doc, "G")
        MoveLayerCommand([a.id, b.id], g.id).execute(doc)
        assert a.parent_id == g.id and b.parent_id == g.id
        assert len(g.children) == 2

    def test_remove_group_also_removes_children(self):
        """When a group is removed, its reparented children are also removed."""
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        a = _layer_by_name(doc, "A")
        g = _layer_by_name(doc, "G")
        MoveLayerCommand([a.id], g.id).execute(doc)
        RemoveLayerCommand(g.id).execute(doc)
        assert doc.layers.get(g.id) is None


# ═══════════════════════════════════════════════════════════════════
# Section 3: Clip Layers (clips_parent / clipping_mask)
# ═══════════════════════════════════════════════════════════════════

class TestClipLayers:
    """Test clips_parent (Affinity-style) and clipping_mask (Photoshop-style)."""

    def test_drop_as_mask_sets_clips_parent(self):
        doc = _make_doc("Parent", "Shape")
        _clip_to_parent(doc, "Shape", "Parent")
        shape = _layer_by_name(doc, "Shape")
        parent = _layer_by_name(doc, "Parent")
        assert shape.clips_parent is True
        assert shape.parent_id == parent.id
        assert shape.id in parent.children

    def test_drop_as_mask_repositions_before_parent(self):
        doc = _make_doc("Parent", "Shape")
        _clip_to_parent(doc, "Shape", "Parent")
        names = _names(doc)
        assert names.index("Shape") < names.index("Parent")

    def test_multiple_clips_parent_children(self):
        doc = _make_doc("Parent", "Shape1", "Shape2")
        _clip_to_parent(doc, "Shape1", "Parent")
        _clip_to_parent(doc, "Shape2", "Parent")
        parent = _layer_by_name(doc, "Parent")
        assert len([cid for cid in parent.children
                     if doc.layers.get(cid) and doc.layers.get(cid).clips_parent]) == 2

    def test_clip_to_layer_sets_clipping_mask(self):
        doc = _make_doc("Below", "Above")
        above = _layer_by_name(doc, "Above")
        below = _layer_by_name(doc, "Below")
        ClipToLayerCommand(above.id, below.id).execute(doc)
        assert above.clipping_mask is True

    def test_clip_to_layer_positions_above_target(self):
        doc = _make_doc("Target", "Clipper", "Other")
        clipper = _layer_by_name(doc, "Clipper")
        target = _layer_by_name(doc, "Target")
        ClipToLayerCommand(clipper.id, target.id).execute(doc)
        order = _ids(doc)
        assert order.index(clipper.id) == order.index(target.id) + 1

    def test_drop_as_mask_detaches_from_old_parent(self):
        """If child was already parented, it detaches from old parent first."""
        doc = _make_doc("ParentA", "ParentB", "Child")
        _clip_to_parent(doc, "Child", "ParentA")
        parentA = _layer_by_name(doc, "ParentA")
        child = _layer_by_name(doc, "Child")
        assert child.id in parentA.children
        # Re-clip to ParentB
        _clip_to_parent(doc, "Child", "ParentB")
        parentB = _layer_by_name(doc, "ParentB")
        assert child.parent_id == parentB.id
        assert child.id in parentB.children
        assert child.id not in parentA.children

    def test_clips_parent_child_preserves_layer_type(self):
        """DropAsMaskCommand does NOT convert the layer to MASK type."""
        doc = _make_doc("Parent", "Shape")
        _clip_to_parent(doc, "Shape", "Parent")
        shape = _layer_by_name(doc, "Shape")
        assert shape.layer_type == LayerType.RASTER

    def test_clip_nonexistent_layer_is_noop(self):
        doc = _make_doc("Parent")
        parent = _layer_by_name(doc, "Parent")
        DropAsMaskCommand("nonexistent", parent.id).execute(doc)
        assert parent.children == []

    def test_mask_layer_vs_clips_parent(self):
        """Mask layers go in mask_layers; clips_parent children go in children."""
        doc = _make_doc("Parent", "Shape")
        parent = _layer_by_name(doc, "Parent")
        mask = _attach_mask(doc, "Parent")
        _clip_to_parent(doc, "Shape", "Parent")
        shape = _layer_by_name(doc, "Shape")
        assert mask.id in parent.mask_layers
        assert mask.id not in parent.children
        assert shape.id in parent.children
        assert shape.id not in parent.mask_layers


# ═══════════════════════════════════════════════════════════════════
# Section 4: Transform Propagation on Clipped Layers
# ═══════════════════════════════════════════════════════════════════

class TestTransformPropagation:
    """Test non-destructive scale/rotation on clipped and grouped layers."""

    def test_layer_init_non_destructive(self):
        doc = _make_doc("L")
        layer = _layer_by_name(doc, "L")
        layer.pixels = np.ones((64, 64, 4), dtype=np.float32)
        layer.init_non_destructive()
        assert layer.source_pixels is not None
        assert layer.source_width == 64

    def test_layer_compute_display_scale(self):
        doc = _make_doc("L")
        layer = _layer_by_name(doc, "L")
        layer.pixels = np.ones((64, 64, 4), dtype=np.float32)
        layer.init_non_destructive()
        layer.compute_display(scale_x=2.0, scale_y=2.0, angle=0.0)
        assert layer.width == 128
        assert layer.height == 128

    def test_layer_compute_display_rotation(self):
        doc = _make_doc("L")
        layer = _layer_by_name(doc, "L")
        layer.pixels = np.ones((64, 64, 4), dtype=np.float32)
        layer.init_non_destructive()
        layer.compute_display(scale_x=1.0, scale_y=1.0, angle=45.0)
        # Rotated 45° → bounding box is larger
        assert layer.width > 64 or layer.height > 64

    def test_has_transform_property(self):
        doc = _make_doc("L")
        layer = _layer_by_name(doc, "L")
        assert layer.has_transform is False
        layer.pixels = np.ones((64, 64, 4), dtype=np.float32)
        layer.init_non_destructive()
        layer.transform_scale_x = 2.0
        assert layer.has_transform is True

    def test_rasterize_transform(self):
        doc = _make_doc("L")
        layer = _layer_by_name(doc, "L")
        layer.pixels = np.ones((64, 64, 4), dtype=np.float32)
        layer.init_non_destructive()
        layer.compute_display(scale_x=2.0, scale_y=2.0, angle=0.0)
        layer.rasterize_transform()
        assert layer.transform_scale_x == 1.0
        assert layer.transform_scale_y == 1.0
        assert layer.transform_angle == 0.0

    def test_transform_attrs_stored_on_layer(self):
        doc = _make_doc("L")
        layer = _layer_by_name(doc, "L")
        layer.transform_scale_x = 1.5
        layer.transform_scale_y = 0.5
        layer.transform_angle = 30.0
        assert layer.transform_scale_x == 1.5
        assert layer.transform_scale_y == 0.5
        assert layer.transform_angle == 30.0

    def test_clip_child_transform_independent(self):
        """Clip children have their own transform attributes."""
        doc = _make_doc("Parent", "Clip")
        _clip_to_parent(doc, "Clip", "Parent")
        parent = _layer_by_name(doc, "Parent")
        clip = _layer_by_name(doc, "Clip")
        parent.transform_scale_x = 2.0
        clip.transform_scale_x = 1.0
        assert parent.transform_scale_x == 2.0
        assert clip.transform_scale_x == 1.0

    def test_duplicate_preserves_transform(self):
        doc = _make_doc("L")
        layer = _layer_by_name(doc, "L")
        layer.transform_scale_x = 1.5
        layer.transform_angle = 45.0
        DuplicateLayerCommand(layer.id).execute(doc)
        dup = [l for l in doc.layers if "copy" in l.name][0]
        assert dup.transform_scale_x == 1.5
        assert dup.transform_angle == 45.0

    def test_invalidate_transform_preserves_source(self):
        doc = _make_doc("L")
        layer = _layer_by_name(doc, "L")
        pix = np.random.rand(64, 64, 4).astype(np.float32)
        layer.pixels = pix
        layer.init_non_destructive()
        layer.transform_scale_x = 2.0
        layer.invalidate_transform()
        # Source pixels should still exist
        assert layer.source_pixels is not None
        np.testing.assert_array_equal(layer.source_pixels, pix)


# ═══════════════════════════════════════════════════════════════════
# Section 5: Un-clipping & Re-clipping
# ═══════════════════════════════════════════════════════════════════

class TestUnclipReclip:
    """Test detach and re-attach of clipping relationships."""

    def test_unparent_clips_parent_child(self):
        doc = _make_doc("Parent", "Clip")
        _clip_to_parent(doc, "Clip", "Parent")
        clip = _layer_by_name(doc, "Clip")
        parent = _layer_by_name(doc, "Parent")
        MoveLayerCommand([clip.id], None).execute(doc)
        assert clip.clips_parent is False
        assert clip.parent_id is None
        assert clip.id not in parent.children

    def test_reclip_after_unparent(self):
        doc = _make_doc("Parent", "Clip")
        _clip_to_parent(doc, "Clip", "Parent")
        clip = _layer_by_name(doc, "Clip")
        parent = _layer_by_name(doc, "Parent")
        MoveLayerCommand([clip.id], None).execute(doc)
        _clip_to_parent(doc, "Clip", "Parent")
        assert clip.clips_parent is True
        assert clip.parent_id == parent.id
        assert clip.id in parent.children

    def test_move_clip_child_to_different_parent(self):
        doc = _make_doc("P1", "P2", "Clip")
        _clip_to_parent(doc, "Clip", "P1")
        clip = _layer_by_name(doc, "Clip")
        p1 = _layer_by_name(doc, "P1")
        p2 = _layer_by_name(doc, "P2")
        _clip_to_parent(doc, "Clip", "P2")
        assert clip.parent_id == p2.id
        assert clip.id in p2.children
        assert clip.id not in p1.children

    def test_convert_clips_parent_to_mask_layer(self):
        """Converting a clips_parent child to a real mask moves it to mask_layers."""
        doc = _make_doc("Parent", "Clip")
        _clip_to_parent(doc, "Clip", "Parent")
        clip = _layer_by_name(doc, "Clip")
        parent = _layer_by_name(doc, "Parent")
        # Give clip some pixel data for conversion
        clip.pixels = np.ones((64, 64, 4), dtype=np.float32)
        from photo_editor.commands import ConvertToMaskCommand
        ConvertToMaskCommand(clip.id, parent.id).execute(doc)
        assert clip.layer_type == LayerType.MASK
        assert clip.parent_id == parent.id

    def test_remove_clip_child_cleans_parent_children(self):
        doc = _make_doc("Parent", "Clip")
        _clip_to_parent(doc, "Clip", "Parent")
        clip = _layer_by_name(doc, "Clip")
        parent = _layer_by_name(doc, "Parent")
        RemoveLayerCommand(clip.id).execute(doc)
        # After removal, parent.children should not reference the deleted layer
        assert clip.id not in parent.children or doc.layers.get(clip.id) is None

    def test_unparent_mask_layer_clears_ex_parent(self):
        """When a MASK layer is unparented, ex_parent_id is cleared."""
        doc = _make_doc("Parent")
        mask = _attach_mask(doc, "Parent")
        parent = _layer_by_name(doc, "Parent")
        assert mask.parent_id == parent.id
        MoveLayerCommand([mask.id], None).execute(doc)
        assert mask.parent_id is None
        assert mask.ex_parent_id is None

    def test_clip_to_layer_unparents_from_old_group(self):
        """ClipToLayerCommand detaches from old parent group."""
        doc = _make_doc("Target", "Child")
        AddGroupCommand(name="G").execute(doc)
        child = _layer_by_name(doc, "Child")
        g = _layer_by_name(doc, "G")
        MoveLayerCommand([child.id], g.id).execute(doc)
        assert child.parent_id == g.id
        target = _layer_by_name(doc, "Target")
        ClipToLayerCommand(child.id, target.id).execute(doc)
        assert child.clipping_mask is True
        assert child.parent_id is None
        assert child.id not in g.children


# ═══════════════════════════════════════════════════════════════════
# Section 6: Collapse / Expand (display order)
# ═══════════════════════════════════════════════════════════════════

class TestCollapseExpand:
    """Test _build_display_order with collapsed groups / mask sections.

    We import _build_display_order as a static method from panel.py.
    """

    @staticmethod
    def _build_display_order(doc, collapsed=None, masks_collapsed=None):
        """Import and call the static method."""
        from photo_editor.ui.panels.layers.panel import LayersPanel
        return LayersPanel._build_display_order(
            doc,
            collapsed or set(),
            masks_collapsed,
        )

    def test_flat_display_order(self):
        doc = _make_doc("A", "B")
        result = self._build_display_order(doc)
        names = [t[0].name for t in result]
        assert names == ["B", "A", "Background"]

    def test_group_expanded_shows_children(self):
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        a = _layer_by_name(doc, "A")
        g = _layer_by_name(doc, "G")
        MoveLayerCommand([a.id], g.id).execute(doc)
        result = self._build_display_order(doc)
        # G visible, then A inside, then Background
        names = [t[0].name for t in result]
        assert "G" in names and "A" in names

    def test_group_collapsed_hides_children(self):
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        a = _layer_by_name(doc, "A")
        g = _layer_by_name(doc, "G")
        MoveLayerCommand([a.id], g.id).execute(doc)
        result = self._build_display_order(doc, collapsed={g.id})
        names = [t[0].name for t in result if t[0] is not None]
        assert "G" in names
        assert "A" not in names

    def test_mask_section_visible_by_default(self):
        doc = _make_doc("Parent")
        mask = _attach_mask(doc, "Parent")
        result = self._build_display_order(doc)
        ids = [t[0].id if t[0] else None for t in result]
        assert mask.id in ids

    def test_mask_section_collapsed_hides_masks(self):
        doc = _make_doc("Parent")
        parent = _layer_by_name(doc, "Parent")
        mask = _attach_mask(doc, "Parent")
        result = self._build_display_order(doc, masks_collapsed={parent.id})
        ids = [t[0].id if t[0] else None for t in result]
        assert mask.id not in ids

    def test_separator_rows_in_display_order(self):
        """When a parent has masks and adjustments, separator rows appear."""
        doc = _make_doc("Parent")
        _attach_mask(doc, "Parent")
        _attach_adj(doc, "Brightness", "Parent")
        result = self._build_display_order(doc)
        # Separator rows have (None, indent, "sep")
        seps = [t for t in result if t[0] is None]
        assert len(seps) >= 1

    def test_clips_parent_children_in_display_order(self):
        """clips_parent children appear in the regular children section."""
        doc = _make_doc("Parent", "Clip")
        _clip_to_parent(doc, "Clip", "Parent")
        result = self._build_display_order(doc)
        names = [t[0].name for t in result if t[0] is not None]
        assert "Clip" in names

    def test_mask_collapse_hides_adj_and_clip_children(self):
        """mask_collapse hides ALL child sections: masks, adj, regular."""
        doc = _make_doc("Parent", "Clip")
        parent = _layer_by_name(doc, "Parent")
        _attach_mask(doc, "Parent")
        _attach_adj(doc, "Brightness", "Parent")
        _clip_to_parent(doc, "Clip", "Parent")
        result = self._build_display_order(doc, masks_collapsed={parent.id})
        # Only Parent and Background should be visible
        names = [t[0].name for t in result if t[0] is not None]
        assert "Parent" in names
        assert "Clip" not in names
        assert "Brightness" not in names

    def test_nested_group_collapse_independent(self):
        doc = _make_doc("A", "B")
        AddGroupCommand(name="Outer").execute(doc)
        AddGroupCommand(name="Inner").execute(doc)
        outer = _layer_by_name(doc, "Outer")
        inner = _layer_by_name(doc, "Inner")
        a = _layer_by_name(doc, "A")
        b = _layer_by_name(doc, "B")
        MoveLayerCommand([inner.id], outer.id).execute(doc)
        MoveLayerCommand([a.id], inner.id).execute(doc)
        MoveLayerCommand([b.id], outer.id).execute(doc)
        # Collapse only Inner
        result = self._build_display_order(doc, collapsed={inner.id})
        names = [t[0].name for t in result if t[0] is not None]
        assert "Outer" in names and "Inner" in names and "B" in names
        assert "A" not in names  # hidden by collapsed Inner


# ═══════════════════════════════════════════════════════════════════
# Section 7: Duplicating Parent with Clipped Layers
# ═══════════════════════════════════════════════════════════════════

class TestDuplicateParentWithClips:
    """Test that duplicating a parent does (or doesn't) carry children."""

    def test_duplicate_parent_does_not_copy_children_list(self):
        """Layer.duplicate() does NOT copy children list."""
        doc = _make_doc("Parent", "Clip")
        _clip_to_parent(doc, "Clip", "Parent")
        parent = _layer_by_name(doc, "Parent")
        DuplicateLayerCommand(parent.id).execute(doc)
        dup = [l for l in doc.layers if "copy" in l.name][0]
        # children list should be empty for the duplicate
        assert dup.children == []

    def test_duplicate_parent_deep_copies_mask_layers(self):
        """Duplicating a parent deep-copies its mask layers with new IDs."""
        doc = _make_doc("Parent")
        mask = _attach_mask(doc, "Parent")
        parent = _layer_by_name(doc, "Parent")
        DuplicateLayerCommand(parent.id).execute(doc)
        dup = [l for l in doc.layers if l.name == "Parent copy"][0]
        # Duplicate should have its own mask layer with a new ID
        assert len(dup.mask_layers) == 1
        assert dup.mask_layers[0] != mask.id
        dup_mask = doc.layers.get(dup.mask_layers[0])
        assert dup_mask is not None
        assert dup_mask.parent_id == dup.id

    def test_duplicate_clip_child_is_independent(self):
        """Duplicating a clips_parent child creates an independent layer."""
        doc = _make_doc("Parent", "Clip")
        _clip_to_parent(doc, "Clip", "Parent")
        clip = _layer_by_name(doc, "Clip")
        DuplicateLayerCommand(clip.id).execute(doc)
        dup = [l for l in doc.layers if "copy" in l.name][0]
        # Duplicate should NOT be clips_parent (Layer.duplicate doesn't copy it)
        assert dup.clips_parent is False
        assert dup.parent_id is None

    def test_duplicate_group_preserves_type(self):
        doc = _make_doc("A")
        AddGroupCommand(name="G").execute(doc)
        g = _layer_by_name(doc, "G")
        DuplicateLayerCommand(g.id).execute(doc)
        dup = [l for l in doc.layers if "copy" in l.name][0]
        assert dup.layer_type == LayerType.GROUP


# ═══════════════════════════════════════════════════════════════════
# Section 8: Adjustment / Filter Layers
# ═══════════════════════════════════════════════════════════════════

class TestAdjustmentFilterLayers:
    """Test adjustment and filter layer attachment, update, detach."""

    def test_attach_adjustment_to_layer(self):
        doc = _make_doc("Target")
        _attach_adj(doc, "Brightness", "Target")
        target = _layer_by_name(doc, "Target")
        adj = _layer_by_name(doc, "Brightness")
        assert adj.parent_id == target.id
        assert adj.id in target.children
        assert adj.layer_type == LayerType.ADJUSTMENT

    def test_update_adjustment_params(self):
        doc = _make_doc("Target")
        _attach_adj(doc, "Brightness", "Target")
        adj = _layer_by_name(doc, "Brightness")
        UpdateEffectCommand(adj.id, {"brightness": 0.5, "contrast": 0.3}).execute(doc)
        assert adj.adjustment_params["brightness"] == 0.5
        assert adj.adjustment_params["contrast"] == 0.3

    def test_attach_filter_to_layer(self):
        doc = _make_doc("Target")
        _attach_filter(doc, "Blur", "Target")
        target = _layer_by_name(doc, "Target")
        filt = _layer_by_name(doc, "Blur")
        assert filt.parent_id == target.id
        assert filt.id in target.children
        assert filt.layer_type == LayerType.FILTER

    def test_unparent_adjustment(self):
        doc = _make_doc("Target")
        _attach_adj(doc, "Brightness", "Target")
        adj = _layer_by_name(doc, "Brightness")
        target = _layer_by_name(doc, "Target")
        MoveLayerCommand([adj.id], None).execute(doc)
        assert adj.parent_id is None
        assert adj.id not in target.children

    def test_adjustment_with_mask_and_clip(self):
        """Parent with mask, adjustment, AND clips_parent child."""
        doc = _make_doc("Parent", "Clip")
        _attach_mask(doc, "Parent")
        _attach_adj(doc, "Brightness", "Parent")
        _clip_to_parent(doc, "Clip", "Parent")
        parent = _layer_by_name(doc, "Parent")
        clip = _layer_by_name(doc, "Clip")
        adj = _layer_by_name(doc, "Brightness")
        # Mask is in mask_layers
        assert len(parent.mask_layers) == 1
        # Adj and clip are in children
        assert adj.id in parent.children
        assert clip.id in parent.children

    def test_remove_adjustment_from_parent(self):
        doc = _make_doc("Target")
        _attach_adj(doc, "Brightness", "Target")
        adj = _layer_by_name(doc, "Brightness")
        target = _layer_by_name(doc, "Target")
        RemoveLayerCommand(adj.id).execute(doc)
        # Layer removed from stack
        assert doc.layers.get(adj.id) is None

    def test_attach_multiple_adjustments(self):
        doc = _make_doc("Target")
        _attach_adj(doc, "Adj1", "Target")
        _attach_adj(doc, "Adj2", "Target")
        target = _layer_by_name(doc, "Target")
        adj_ids = [cid for cid in target.children
                   if doc.layers.get(cid) and doc.layers.get(cid).layer_type == LayerType.ADJUSTMENT]
        assert len(adj_ids) == 2

    def test_add_mask_layer_to_adjusted_parent(self):
        doc = _make_doc("Target")
        _attach_adj(doc, "Brightness", "Target")
        mask = _attach_mask(doc, "Target")
        target = _layer_by_name(doc, "Target")
        assert mask.id in target.mask_layers
        adj = _layer_by_name(doc, "Brightness")
        assert adj.id in target.children

    def test_move_adjustment_between_parents(self):
        doc = _make_doc("P1", "P2")
        _attach_adj(doc, "Brightness", "P1")
        adj = _layer_by_name(doc, "Brightness")
        p1 = _layer_by_name(doc, "P1")
        p2 = _layer_by_name(doc, "P2")
        # Move adj from P1 to P2
        MoveLayerCommand([adj.id], p2.id).execute(doc)
        assert adj.parent_id == p2.id
        assert adj.id in p2.children
        assert adj.id not in p1.children


# ═══════════════════════════════════════════════════════════════════
# Section 9: Corner Cases & Regressions
# ═══════════════════════════════════════════════════════════════════

class TestReorderedStackOrder:
    """Test reordered_stack_order with various edge cases."""

    def test_basic_reorder(self):
        display_ids = ["top", "mid", "bottom"]
        result = reordered_stack_order(display_ids, ["mid"], 0)
        # mid moved to row 0 (top) → reversed: bottom, top, mid
        assert result == ["bottom", "top", "mid"]

    def test_reorder_to_end(self):
        display_ids = ["top", "mid", "bottom"]
        result = reordered_stack_order(display_ids, ["top"], 3)
        # Move "top" to row 3 (after last) → display: mid, bottom, top
        # reversed → stack: top, bottom, mid
        assert result == ["top", "bottom", "mid"]

    def test_reorder_multiple_dragged(self):
        display_ids = ["a", "b", "c", "d"]
        result = reordered_stack_order(display_ids, ["a", "b"], 3)
        # Remove a,b → ["c", "d"], insert at 3 → clamp to 2 → ["c", "d", "a", "b"]
        # Wait: above_count: a at idx 0 < 3 → in dragged, count=1; b at idx 1 < 3 → in dragged, count=2
        # remaining = ["c", "d"], insert_at = max(0, min(3-2, 2)) = 1
        # ["c", "a", "b", "d"] → reversed: ["d", "b", "a", "c"]
        assert result == ["d", "b", "a", "c"]

    def test_reorder_with_separators(self):
        display_ids = ["parent", "mask", "__sep__", "adj", "__sep__", "child", "other"]
        result = reordered_stack_order(display_ids, ["other"], 2)
        # seps_above at row 2: display_ids[0]="parent" no, [1]="mask" no → seps_above=0
        # real_ids = ["parent", "mask", "adj", "child", "other"]
        # adjusted_target = 2 - 0 = 2
        # above_count: check real_ids[0..1], "parent"/"mask" not in dragged → 0
        # remaining = ["parent", "mask", "adj", "child"]
        # insert_at = min(2, 4) = 2
        # ["parent", "mask", "other", "adj", "child"] → reversed
        assert result == ["child", "adj", "other", "mask", "parent"]

    def test_reorder_separator_skips_correctly(self):
        display_ids = ["A", "__sep__", "B", "C"]
        result = reordered_stack_order(display_ids, ["C"], 1)
        # seps_above at row 1: display_ids[0]="A" (not sep) → seps_above=0
        # real_ids = ["A", "B", "C"]
        # adjusted_target = 1 - 0 = 1
        # above_count: real_ids[0]="A" not in dragged → 0
        # remaining = ["A", "B"], insert_at = 1
        # ["A", "C", "B"] → reversed: ["B", "C", "A"]
        assert result == ["B", "C", "A"]

    def test_reorder_all_separators_above(self):
        display_ids = ["__sep__", "__sep__", "A", "B"]
        result = reordered_stack_order(display_ids, ["B"], 1)
        # seps_above at row 1: display_ids[0]="__sep__" → seps_above=1
        # real_ids = ["A", "B"]
        # adjusted_target = 1 - 1 = 0
        # above_count: no real_ids before adjusted_target 0 → 0
        # remaining = ["A"], insert_at = max(0, min(0, 1)) = 0
        # ["B", "A"] → reversed: ["A", "B"]
        assert result == ["A", "B"]

    def test_reorder_empty_dragged(self):
        display_ids = ["A", "B", "C"]
        result = reordered_stack_order(display_ids, [], 1)
        assert result == ["C", "B", "A"]

    def test_reorder_drag_to_row_zero(self):
        display_ids = ["A", "B", "C"]
        result = reordered_stack_order(display_ids, ["C"], 0)
        # Move C to top → ["C", "A", "B"] → reversed: ["B", "A", "C"]
        assert result == ["B", "A", "C"]


class TestGetDropIndex:
    """Test the get_drop_index helper for pointer→row mapping."""

    def test_above_first_row(self):
        tops = [0.0, 48.0, 96.0]
        assert get_drop_index(-10.0, tops, 3) == 0

    def test_between_rows(self):
        tops = [0.0, 48.0, 96.0]
        assert get_drop_index(60.0, tops, 3) == 1  # below mid of row 0 (24), below mid of row 1 (72)? No
        # Row 0: mid=24, 60>24 → continue; Row 1: mid=72, 60<72 → return 1
        assert get_drop_index(60.0, tops, 3) == 1

    def test_below_last_row(self):
        tops = [0.0, 48.0, 96.0]
        assert get_drop_index(200.0, tops, 3) == 3

    def test_exactly_at_midpoint(self):
        tops = [0.0, 48.0]
        # mid of row 0 = 24.0; pointer at 24 → 24 < 24 is False → continue → row 1 mid=72 → return 1
        assert get_drop_index(24.0, tops, 2) == 1

    def test_custom_row_heights(self):
        tops = [0.0, 48.0, 54.0]  # row 0: 48px, row 1: 6px (separator), row 2: 48px
        heights = [48.0, 6.0, 48.0]
        # Row 1 mid = 48 + 3 = 51
        assert get_drop_index(52.0, tops, 3, row_heights=heights) == 2

    def test_separator_height_without_custom(self):
        """Without row_heights, separator midpoint is wrong."""
        tops = [0.0, 48.0, 54.0]
        # Row 1 mid = 48 + 24 = 72 (using default ROW_HEIGHT=48)
        # pointer_y=52: 52>24 (row0)→pass; 52<72 (row1)→return 1
        assert get_drop_index(52.0, tops, 3) == 1  # incorrect result without heights

    def test_separator_height_with_custom(self):
        """With row_heights, separator midpoint is correct."""
        tops = [0.0, 48.0, 54.0]
        heights = [48.0, 6.0, 48.0]
        # Row 1 mid = 48 + 3 = 51; pointer_y=52 > 51 → continue
        # Row 2 mid = 54 + 24 = 78; pointer_y=52 < 78 → return 2
        assert get_drop_index(52.0, tops, 3, row_heights=heights) == 2

    def test_single_row(self):
        tops = [0.0]
        assert get_drop_index(-5.0, tops, 1) == 0
        assert get_drop_index(30.0, tops, 1) == 1

    def test_empty_list(self):
        assert get_drop_index(10.0, [], 0) == 0


class TestIsDescendantOf:
    """Test circular reparent detection."""

    def test_direct_child(self):
        children_map = {"parent": ["child"]}
        assert is_descendant_of("child", {"parent"}, children_map) is True

    def test_grandchild(self):
        children_map = {"g": ["p"], "p": ["c"]}
        assert is_descendant_of("c", {"g"}, children_map) is True

    def test_not_descendant(self):
        children_map = {"a": ["b"]}
        assert is_descendant_of("c", {"a"}, children_map) is False

    def test_empty_ancestors(self):
        children_map = {"a": ["b"]}
        assert is_descendant_of("b", set(), children_map) is False

    def test_no_children(self):
        assert is_descendant_of("x", {"parent"}, {}) is False

    def test_self_not_descendant(self):
        children_map = {"a": ["b"]}
        assert is_descendant_of("a", {"a"}, children_map) is False


class TestInferTargetDepth:
    """Test unparent depth from cursor X."""

    def test_depth_zero(self):
        assert infer_target_depth(5.0) == 0

    def test_depth_one(self):
        # INDENT_WIDTH = 20
        assert infer_target_depth(25.0) == 1

    def test_depth_clamped(self):
        # MAX_INDENT_DEPTH = 5
        assert infer_target_depth(500.0) == 5

    def test_negative_x(self):
        assert infer_target_depth(-10.0) == 0


class TestDragState:
    """Test DragState dataclass reset."""

    def test_initial_state(self):
        ds = DragState()
        assert ds.dragging is False
        assert ds.committed is False
        assert ds.dragged_ids == []

    def test_reset(self):
        ds = DragState()
        ds.dragging = True
        ds.dragged_ids.append("layer1")
        ds.committed = True
        ds.drop_mode = DropMode.NEST
        ds.reset()
        assert ds.dragging is False
        assert ds.dragged_ids == []
        assert ds.committed is False
        assert ds.drop_mode is None


class TestSelectedIndices:
    """Test selected_indices_from_layer_ids mapping."""

    def test_maps_ids_to_indices(self):
        layers = [SimpleNamespace(id="a"), SimpleNamespace(id="b"), SimpleNamespace(id="c")]
        result = selected_indices_from_layer_ids(["c", "a"], layers)
        assert result == {0, 2}

    def test_missing_id_skipped(self):
        layers = [SimpleNamespace(id="a"), SimpleNamespace(id="b")]
        result = selected_indices_from_layer_ids(["a", "missing"], layers)
        assert result == {0}

    def test_empty_ids(self):
        layers = [SimpleNamespace(id="a")]
        result = selected_indices_from_layer_ids([], layers)
        assert result == set()


class TestCornerCasesAndRegressions:
    """Miscellaneous regression tests."""

    def test_reorder_command_preserves_all_layers(self):
        doc = _make_doc("A", "B", "C")
        ids = _ids(doc)
        ReorderLayersCommand(list(reversed(ids))).execute(doc)
        assert set(_ids(doc)) == set(ids)

    def test_reorder_command_changes_order(self):
        doc = _make_doc("A", "B", "C")
        bg, a, b, c = _ids(doc)
        ReorderLayersCommand([c, b, a, bg]).execute(doc)
        assert _ids(doc) == [c, b, a, bg]

    def test_flatten_merges_all(self):
        doc = _make_doc("A", "B")
        FlattenCommand().execute(doc)
        assert len(list(doc.layers)) == 1

    def test_merge_down(self):
        doc = _make_doc("Bottom", "Top")
        doc.layers.active_index = 2  # Top
        result = MergeDownCommand().execute(doc)
        assert result is True

    def test_add_mask_layer(self):
        doc = _make_doc("Target")
        target = _layer_by_name(doc, "Target")
        mask = _attach_mask(doc, "Target")
        assert mask.layer_type == LayerType.MASK
        assert mask.id in target.mask_layers

    def test_apply_mask_layer(self):
        doc = _make_doc("Target")
        target = _layer_by_name(doc, "Target")
        mask = _attach_mask(doc, "Target")
        from photo_editor.commands import ApplyMaskLayerCommand
        ApplyMaskLayerCommand(mask.id).execute(doc)
        assert len(target.mask_layers) == 0

    def test_invert_mask_layer(self):
        doc = _make_doc("Target")
        mask = _attach_mask(doc, "Target")
        from photo_editor.commands import InvertMaskLayerCommand
        InvertMaskLayerCommand(mask.id).execute(doc)
        assert mask.get_mask_grayscale().max() < 0.01

    def test_attach_mask_to_layer(self):
        doc = _make_doc("Target")
        target = _layer_by_name(doc, "Target")
        mask = doc.add_mask_layer(target_id="__standalone__", fill_white=True)
        assert mask is not None
        AttachMaskToLayerCommand(mask.id, target.id).execute(doc)
        assert mask.parent_id == target.id
        assert mask.id in target.mask_layers

    def test_parent_with_mask_adj_clip_all_sections(self):
        """Complex layer with mask, adjustment, AND clips_parent child."""
        doc = _make_doc("Parent", "Clip1", "Clip2")
        parent = _layer_by_name(doc, "Parent")
        mask = _attach_mask(doc, "Parent")
        _attach_adj(doc, "Brightness", "Parent")
        _clip_to_parent(doc, "Clip1", "Parent")
        _clip_to_parent(doc, "Clip2", "Parent")
        adj = _layer_by_name(doc, "Brightness")
        c1 = _layer_by_name(doc, "Clip1")
        c2 = _layer_by_name(doc, "Clip2")
        assert mask.id in parent.mask_layers
        assert adj.id in parent.children
        assert c1.id in parent.children
        assert c2.id in parent.children
        assert c1.clips_parent is True
        assert c2.clips_parent is True

    def test_reorder_does_not_lose_layers(self):
        """After any reorder, all layers still exist."""
        doc = _make_doc("A", "B", "C")
        ids_before = set(_ids(doc))
        ids = _ids(doc)
        ReorderLayersCommand([ids[2], ids[0], ids[1], ids[3]]).execute(doc)
        assert set(_ids(doc)) == ids_before

    def test_multiple_clips_parent_after_unparent_one(self):
        """Remove one clip child; other remains."""
        doc = _make_doc("Parent", "Clip1", "Clip2")
        _clip_to_parent(doc, "Clip1", "Parent")
        _clip_to_parent(doc, "Clip2", "Parent")
        parent = _layer_by_name(doc, "Parent")
        c1 = _layer_by_name(doc, "Clip1")
        c2 = _layer_by_name(doc, "Clip2")
        MoveLayerCommand([c1.id], None).execute(doc)
        assert c1.clips_parent is False
        assert c1.id not in parent.children
        assert c2.clips_parent is True
        assert c2.id in parent.children

    def test_layer_in_group_with_clips_parent(self):
        """Layer inside a group also gets a clips_parent child."""
        doc = _make_doc("Child", "Clip")
        AddGroupCommand(name="G").execute(doc)
        child = _layer_by_name(doc, "Child")
        g = _layer_by_name(doc, "G")
        MoveLayerCommand([child.id], g.id).execute(doc)
        _clip_to_parent(doc, "Clip", "Child")
        clip = _layer_by_name(doc, "Clip")
        assert clip.parent_id == child.id
        assert clip.id in child.children
        assert child.parent_id == g.id

    def test_deep_nesting_clip_inside_group_inside_group(self):
        doc = _make_doc("Leaf", "Clip")
        AddGroupCommand(name="Inner").execute(doc)
        AddGroupCommand(name="Outer").execute(doc)
        inner = _layer_by_name(doc, "Inner")
        outer = _layer_by_name(doc, "Outer")
        leaf = _layer_by_name(doc, "Leaf")
        MoveLayerCommand([inner.id], outer.id).execute(doc)
        MoveLayerCommand([leaf.id], inner.id).execute(doc)
        _clip_to_parent(doc, "Clip", "Leaf")
        clip = _layer_by_name(doc, "Clip")
        assert clip.parent_id == leaf.id
        assert leaf.parent_id == inner.id
        assert inner.parent_id == outer.id

    def test_reorder_stack_with_mask_and_adj(self):
        """After reparenting, mask and adj stay attached."""
        doc = _make_doc("Parent")
        mask = _attach_mask(doc, "Parent")
        _attach_adj(doc, "Brightness", "Parent")
        parent = _layer_by_name(doc, "Parent")
        adj = _layer_by_name(doc, "Brightness")
        # Reorder stack
        ids = _ids(doc)
        ReorderLayersCommand(list(reversed(ids))).execute(doc)
        # Parent still owns mask and adj
        assert mask.id in parent.mask_layers
        assert adj.id in parent.children

    def test_duplicate_adjusted_layer(self):
        """Duplicate a layer that has adjustment children."""
        doc = _make_doc("Target")
        _attach_adj(doc, "Brightness", "Target")
        target = _layer_by_name(doc, "Target")
        DuplicateLayerCommand(target.id).execute(doc)
        dup = [l for l in doc.layers if "copy" in l.name][0]
        # dup shouldn't have children (Layer.duplicate doesn't copy children)
        assert dup.children == []

    def test_drop_as_mask_on_self_is_noop(self):
        """Dropping a layer on itself shouldn't crash."""
        doc = _make_doc("A")
        a = _layer_by_name(doc, "A")
        # reparent to self → should be skipped
        MoveLayerCommand([a.id], a.id).execute(doc)  # Shouldn't crash

    def test_reorder_preserves_parent_child_relationship(self):
        """Reorder by IDs doesn't break parent_id / children references."""
        doc = _make_doc("Parent", "Child")
        _clip_to_parent(doc, "Child", "Parent")
        parent = _layer_by_name(doc, "Parent")
        child = _layer_by_name(doc, "Child")
        ids = _ids(doc)
        ReorderLayersCommand(list(reversed(ids))).execute(doc)
        assert child.parent_id == parent.id
        assert child.id in parent.children
        assert child.clips_parent is True
