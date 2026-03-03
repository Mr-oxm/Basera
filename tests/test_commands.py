"""Tests for command system."""

import pytest

import numpy as np

from photo_editor.commands import (
    AddGroupCommand,
    AddLayerCommand,
    AddMaskLayerCommand,
    ApplyMaskLayerCommand,
    AttachAdjustmentToLayerCommand,
    AttachMaskToLayerCommand,
    ConvertToMaskCommand,
    DuplicateLayerCommand,
    FlattenCommand,
    InvertMaskLayerCommand,
    MergeDownCommand,
    MoveLayerCommand,
    PlaceImageCommand,
    RemoveLayerCommand,
    RemoveMaskLayerCommand,
    RenameLayerCommand,
    ReorderLayersCommand,
    UpdateEffectCommand,
)
from photo_editor.core.document import Document
from photo_editor.core.enums import LayerType


def test_add_layer_command():
    """AddLayerCommand adds a layer."""
    doc = Document(64, 64)
    initial_count = len(list(doc.layers))
    cmd = AddLayerCommand(name="Test Layer", layer_type=LayerType.RASTER)
    cmd.execute(doc)
    assert len(list(doc.layers)) == initial_count + 1
    added = [l for l in doc.layers if l.name == "Test Layer"]
    assert len(added) == 1


def test_remove_layer_command():
    """RemoveLayerCommand removes a layer."""
    doc = Document(64, 64)
    layer = doc.add_layer(name="ToRemove")
    lid = layer.id
    cmd = RemoveLayerCommand(layer_id=lid)
    cmd.execute(doc)
    assert doc.layers.get(lid) is None


def test_update_effect_command():
    """UpdateEffectCommand updates adjustment params."""
    doc = Document(64, 64)
    from photo_editor.adjustments.brightness_contrast import BrightnessContrast
    layer = doc.add_layer(name="Adj", layer_type=LayerType.ADJUSTMENT)
    layer.adjustment = BrightnessContrast()
    layer.adjustment_params = {"brightness": 0, "contrast": 0}
    cmd = UpdateEffectCommand(layer_id=layer.id, params={"brightness": 0.2, "contrast": 0.1})
    cmd.execute(doc)
    assert layer.adjustment_params["brightness"] == 0.2
    assert layer.adjustment_params["contrast"] == 0.1


def test_move_layer_command_reparent():
    """MoveLayerCommand reparents layers to a group."""
    doc = Document(64, 64)
    group = doc.add_group(name="Group")
    layer = doc.add_layer(name="Child")
    assert layer.parent_id is None
    cmd = MoveLayerCommand(layer_ids=[layer.id], target_parent_id=group.id)
    cmd.execute(doc)
    assert layer.parent_id == group.id
    assert layer.id in group.children


def test_move_layer_command_unparent():
    """MoveLayerCommand unparents layers."""
    doc = Document(64, 64)
    group = doc.add_group(name="Group")
    layer = doc.add_layer(name="Child")
    doc.layers.reparent([layer.id], group.id)
    cmd = MoveLayerCommand(layer_ids=[layer.id], target_parent_id=None)
    cmd.execute(doc)
    assert layer.parent_id is None


def test_add_group_command():
    """AddGroupCommand adds a group."""
    doc = Document(64, 64)
    cmd = AddGroupCommand(name="My Group")
    cmd.execute(doc)
    groups = [l for l in doc.layers if l.name == "My Group"]
    assert len(groups) == 1


def test_duplicate_layer_command():
    """DuplicateLayerCommand duplicates a layer."""
    doc = Document(64, 64)
    layer = doc.add_layer(name="Original")
    initial_count = len(list(doc.layers))
    cmd = DuplicateLayerCommand(layer.id)
    cmd.execute(doc)
    assert len(list(doc.layers)) == initial_count + 1


def test_add_mask_layer_command():
    """AddMaskLayerCommand adds a mask layer."""
    doc = Document(64, 64)
    layer = doc.add_layer(name="Target")
    doc.layers.active_index = 1
    cmd = AddMaskLayerCommand(fill_white=True)
    cmd.execute(doc)
    assert len(layer.mask_layers) == 1


def test_flatten_command():
    """FlattenCommand merges all layers."""
    doc = Document(64, 64)
    doc.add_layer(name="L1")
    doc.add_layer(name="L2")
    cmd = FlattenCommand()
    cmd.execute(doc)
    assert len(list(doc.layers)) == 1
    assert doc.layers[0].name == "Background"


def test_merge_down_command():
    """MergeDownCommand merges active onto layer below."""
    doc = Document(64, 64)
    l1 = doc.add_layer(name="Bottom")
    l2 = doc.add_layer(name="Top")
    doc.layers.active_index = 2
    result = MergeDownCommand().execute(doc)
    assert result is True
    assert len(list(doc.layers)) == 2  # Background + merged


def test_rename_layer_command():
    """RenameLayerCommand renames a layer."""
    doc = Document(64, 64)
    layer = doc.add_layer(name="Old")
    cmd = RenameLayerCommand(layer.id, "New Name")
    cmd.execute(doc)
    assert doc.layers.get(layer.id).name == "New Name"


def test_apply_mask_layer_command():
    """ApplyMaskLayerCommand burns mask into parent and removes it."""
    doc = Document(64, 64)
    layer = doc.add_layer(name="Target")
    doc.layers.active_index = 1
    mask = doc.add_mask_layer(fill_white=True)
    assert mask is not None
    assert len(layer.mask_layers) == 1
    cmd = ApplyMaskLayerCommand(mask.id)
    cmd.execute(doc)
    assert len(layer.mask_layers) == 0


def test_invert_mask_layer_command():
    """InvertMaskLayerCommand inverts mask grayscale."""
    doc = Document(64, 64)
    layer = doc.add_layer(name="Target")
    doc.layers.active_index = 1
    mask = doc.add_mask_layer(fill_white=True)
    assert mask is not None
    cmd = InvertMaskLayerCommand(mask.id)
    cmd.execute(doc)
    # Inverted white mask should be black
    assert mask.get_mask_grayscale().max() < 0.01


def test_convert_to_mask_command():
    """ConvertToMaskCommand converts layer to mask."""
    doc = Document(64, 64)
    l1 = doc.add_layer(name="Below")
    l2 = doc.add_layer(name="ToConvert")
    cmd = ConvertToMaskCommand(l2.id, l1.id)
    cmd.execute(doc)
    assert l2.layer_type == LayerType.MASK
    assert l2.parent_id == l1.id
    assert l2.id in l1.mask_layers


def test_place_image_command():
    """PlaceImageCommand adds image as new layer."""
    doc = Document(64, 64)
    img = np.ones((32, 32, 4), dtype=np.float32) * 0.5
    initial_count = len(list(doc.layers))
    cmd = PlaceImageCommand(img, name="Placed")
    cmd.execute(doc)
    assert len(list(doc.layers)) == initial_count + 1
    placed = [l for l in doc.layers if l.name == "Placed"]
    assert len(placed) == 1
    assert placed[0].pixels.shape == (32, 32, 4)


def test_attach_mask_to_layer_command():
    """AttachMaskToLayerCommand reparents mask to target."""
    doc = Document(64, 64)
    target = doc.add_layer(name="Target")
    mask = doc.add_mask_layer(target_id="__standalone__", fill_white=True)
    assert mask is not None and mask.parent_id is None
    cmd = AttachMaskToLayerCommand(mask.id, target.id)
    cmd.execute(doc)
    assert mask.parent_id == target.id
    assert mask.id in target.mask_layers


def test_attach_adjustment_to_layer_command():
    """AttachAdjustmentToLayerCommand reparents adj/filter to target."""
    doc = Document(64, 64)
    from photo_editor.adjustments.brightness_contrast import BrightnessContrast
    target = doc.add_layer(name="Target")
    adj = doc.add_layer(name="Brightness", layer_type=LayerType.ADJUSTMENT)
    adj.adjustment = BrightnessContrast()
    adj.adjustment_params = {"brightness": 0, "contrast": 0}
    adj.parent_id = None
    cmd = AttachAdjustmentToLayerCommand(adj.id, target.id)
    cmd.execute(doc)
    assert adj.parent_id == target.id
    assert adj.id in target.children


def test_reorder_layers_command():
    """ReorderLayersCommand reorders the layer stack."""
    doc = Document(64, 64)
    bg_id = doc.layers[0].id
    l1 = doc.add_layer(name="L1")
    l2 = doc.add_layer(name="L2")
    l3 = doc.add_layer(name="L3")
    new_order = [bg_id, l3.id, l1.id, l2.id]  # bottom to top
    cmd = ReorderLayersCommand(new_order)
    cmd.execute(doc)
    order_after = [l.id for l in doc.layers]
    assert order_after == new_order
