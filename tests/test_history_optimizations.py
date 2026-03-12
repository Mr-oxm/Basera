from __future__ import annotations

import numpy as np

from photo_editor.core.document import Document
from photo_editor.core.layer import Layer
from photo_editor.commands import ReorderLayersCommand
from photo_editor.transforms.transform_engine import TransformEngine
from photo_editor.tools.brush import BrushTool
from photo_editor.tools.clone_stamp import CloneStampTool
from photo_editor.tools.eyedropper import EyedropperTool
from photo_editor.tools.gradient_tool import GradientTool
from photo_editor.tools.healing_brush import HealingBrushTool
from photo_editor.tools.move.auto_select import point_on_layer
from photo_editor.tools.paint_bucket import PaintBucketTool
from photo_editor.tools.move.move_tool import MoveTool
from photo_editor.commands import MoveLayerCommand


def test_metadata_snapshot_restores_positions_without_pixel_copy_state() -> None:
    doc = Document(64, 64)
    layer = Layer(name="Photo", width=8, height=6)
    layer.pixels[:] = np.array([0.25, 0.5, 0.75, 1.0], dtype=np.float32)
    layer.position = (2, 3)
    doc.layers.add(layer)
    doc.layers.active_index = doc.layers.layers.index(layer)

    doc.save_snapshot("Base")
    layer.position = (17, 19)
    doc.save_metadata_snapshot("Move")

    base_state = doc.history.states[0]
    move_state = doc.history.states[1]

    doc._restore(base_state)
    restored_base = doc.layers.get(layer.id)
    assert restored_base is not None
    assert restored_base.position == (2, 3)

    doc._restore(move_state)
    restored_move = doc.layers.get(layer.id)
    assert restored_move is not None
    assert restored_move.position == (17, 19)
    np.testing.assert_allclose(
        restored_move.pixels,
        restored_base.pixels,
    )


def test_plain_move_uses_lightweight_history_and_skips_nd_source_copy() -> None:
    doc = Document(128, 128)
    layer = Layer(name="Move Me", width=100, height=100)
    layer.pixels[:] = 1.0
    layer.position = (10, 12)
    doc.layers.add(layer)
    doc.layers.active_index = doc.layers.layers.index(layer)

    tool = MoveTool()
    tool.auto_select = False

    tool.on_press(doc, 60, 60)
    tool.on_move(doc, 100, 90)
    tool.on_release(doc, 100, 90)

    moved = doc.layers.get(layer.id)
    assert moved is not None
    assert moved.position != (10, 12)
    assert moved._source_pixels is None
    assert len(doc.history.states) == 1
    assert doc.history.states[0].metadata["_pixel_snapshot"] is False


def test_tile_patch_history_restores_only_captured_region() -> None:
    doc = Document(64, 64)
    layer = Layer(name="Paint", width=32, height=32)
    layer.pixels[:] = np.array([0.1, 0.2, 0.3, 1.0], dtype=np.float32)
    doc.layers.add(layer)
    doc.layers.active_index = doc.layers.layers.index(layer)

    original = layer.pixels.copy()
    doc.begin_layer_tile_patch("Brush Stroke", layer.id, tile_size=8)
    doc.capture_layer_tile_region(layer, 4, 4, 2, 2)
    layer.pixels[4:6, 4:6] = np.array([1.0, 0.0, 0.0, 1.0], dtype=np.float32)

    assert doc.commit_layer_tile_patch() is True
    state = doc.history.states[-1]

    layer.pixels[:] = 0.0
    doc._restore(state)

    np.testing.assert_allclose(layer.pixels[4:6, 4:6], original[4:6, 4:6])
    np.testing.assert_allclose(layer.pixels[16:24, 16:24], 0.0)


def test_tile_patch_history_undo_and_redo_use_before_after_tiles() -> None:
    doc = Document(64, 64)
    layer = Layer(name="Paint", width=32, height=32)
    layer.pixels[:] = np.array([0.1, 0.2, 0.3, 1.0], dtype=np.float32)
    doc.layers.add(layer)
    doc.layers.active_index = doc.layers.layers.index(layer)

    before = layer.pixels.copy()
    doc.begin_layer_tile_patch("Brush Stroke", layer.id, tile_size=8)
    doc.capture_layer_tile_region(layer, 4, 4, 4, 4)
    layer.pixels[4:8, 4:8] = np.array([1.0, 0.0, 0.0, 1.0], dtype=np.float32)
    after = layer.pixels.copy()

    assert doc.commit_layer_tile_patch() is True

    doc.undo()
    np.testing.assert_allclose(layer.pixels, before)

    doc.redo()
    np.testing.assert_allclose(layer.pixels, after)


def test_gradient_history_captures_only_changed_tiles_for_create_and_handle_edit() -> None:
    doc = Document(600, 64)
    layer = doc.layers[0]
    layer.pixels[:] = 1.0
    doc.layers.active_index = 0

    tool = GradientTool()

    tool.on_press(doc, 0, 32)
    tool.on_move(doc, 120, 32)
    tool.on_release(doc, 120, 32)

    first_state = doc.history.states[-1]
    assert first_state.name == "Gradient"
    assert len(first_state.metadata["_tile_patch"]["tiles"]) == 1

    tool.on_press(doc, 120, 32)
    tool.on_move(doc, 180, 32)
    tool.on_release(doc, 180, 32)

    second_state = doc.history.states[-1]
    assert second_state.name == "Gradient Handle Edit"
    assert len(second_state.metadata["_tile_patch"]["tiles"]) == 1


def test_gradient_respects_existing_alpha_shape_and_marks_content_dirty_region() -> None:
    doc = Document(64, 64)
    layer = Layer(name="Circle", width=64, height=64)
    layer.pixels[:] = 0.0
    yy, xx = np.mgrid[0:64, 0:64]
    mask = ((xx - 32) ** 2 + (yy - 32) ** 2) <= 12 ** 2
    layer.pixels[mask] = np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float32)
    doc.layers.add(layer)
    doc.layers.active_index = doc.layers.layers.index(layer)

    tool = GradientTool()
    tool.on_press(doc, 20, 32)
    tool.on_move(doc, 44, 32)

    dirty = doc.consume_dirty_region()
    assert dirty == (20, 20, 25, 25)
    assert np.all(layer.pixels[0:10, 0:10, 3] == 0.0)
    assert np.all(layer.pixels[0:10, 0:10, :3] == 0.0)


def test_move_tool_marks_precise_dirty_region_for_translation() -> None:
    doc = Document(200, 200)
    layer = Layer(name="Move", width=80, height=40)
    layer.position = (10, 15)
    layer.pixels[:] = 1.0
    doc.layers.add(layer)
    doc.layers.active_index = doc.layers.layers.index(layer)

    tool = MoveTool()
    tool.auto_select = False
    tool.on_press(doc, 40, 35)
    tool.on_move(doc, 70, 55)

    assert doc.consume_dirty_region() == (10, 15, 110, 60)


def test_move_layer_command_marks_structural_dirty_region() -> None:
    doc = Document(200, 200)
    group = doc.add_group(name="Group")
    layer = Layer(name="Child", width=20, height=20)
    layer.position = (50, 60)
    layer.pixels[:] = 1.0
    doc.layers.add(layer)

    cmd = MoveLayerCommand([layer.id], target_parent_id=group.id)
    cmd.execute(doc)

    assert doc.consume_dirty_region() == (50, 60, 20, 20)


def test_metadata_snapshot_restores_multi_selection_state() -> None:
    doc = Document(64, 64)
    first = Layer(name="First", width=8, height=8)
    second = Layer(name="Second", width=8, height=8)
    doc.layers.add(first)
    doc.layers.add(second)
    doc.layers.active_index = doc.layers.layers.index(first)
    doc.layers.select_add(doc.layers.layers.index(second))

    doc.save_metadata_snapshot("Select Layers")

    doc.layers.select_only(0)
    doc._restore(doc.history.states[-1])

    assert doc.layers.active_layer is not None
    assert doc.layers.active_layer.id == second.id
    assert doc.layers.selected_indices == {1, 2}


def test_reorder_command_uses_metadata_history_and_marks_changed_region() -> None:
    doc = Document(128, 128)
    left = Layer(name="Left", width=20, height=20)
    left.position = (5, 10)
    left.pixels[:] = 1.0
    right = Layer(name="Right", width=20, height=20)
    right.position = (60, 15)
    right.pixels[:] = 1.0
    doc.layers.add(left)
    doc.layers.add(right)

    new_order = [doc.layers.layers[0].id, right.id, left.id]
    ReorderLayersCommand(new_order).execute(doc)

    assert doc.history.states[-1].metadata["_pixel_snapshot"] is False
    assert doc.consume_dirty_region() == (5, 10, 75, 25)


def test_radial_gradient_preview_marks_only_changed_support_region() -> None:
    doc = Document(128, 128)
    layer = Layer(name="Circle", width=128, height=128)
    layer.pixels[:] = 0.0
    yy, xx = np.mgrid[0:128, 0:128]
    mask = ((xx - 64) ** 2 + (yy - 64) ** 2) <= 28 ** 2
    layer.pixels[mask] = np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float32)
    doc.layers.add(layer)
    doc.layers.active_index = doc.layers.layers.index(layer)

    tool = GradientTool()
    tool.gradient_type = "radial"
    tool.on_press(doc, 64, 64)
    tool.on_move(doc, 76, 64)

    dirty = doc.consume_dirty_region()
    assert dirty == (52, 52, 25, 25)


def test_fast_transform_preview_reuses_cached_proxy(monkeypatch) -> None:
    layer = Layer(name="Transform", width=24, height=16)
    layer.pixels[:] = np.array([0.2, 0.4, 0.8, 1.0], dtype=np.float32)
    layer.init_non_destructive()

    calls = {"scale": 0, "rotate": 0}
    original_scale = TransformEngine.scale
    original_rotate = TransformEngine.rotate

    def counting_scale(image, sx, sy, fast=False):
        calls["scale"] += 1
        return original_scale(image, sx, sy, fast=fast)

    def counting_rotate(image, angle, expand=True, fast=False):
        calls["rotate"] += 1
        return original_rotate(image, angle, expand=expand, fast=fast)

    monkeypatch.setattr(TransformEngine, "scale", staticmethod(counting_scale))
    monkeypatch.setattr(TransformEngine, "rotate", staticmethod(counting_rotate))

    layer.compute_display(scale_x=1.5, scale_y=1.5, angle=12.0, fast=True)
    first_pixels = layer.pixels.copy()
    layer.compute_display(scale_x=1.5, scale_y=1.5, angle=12.0, fast=True)
    second_pixels = layer.pixels.copy()

    assert calls == {"scale": 1, "rotate": 1}
    np.testing.assert_allclose(first_pixels, second_pixels)


def test_final_transform_result_reuses_cached_output(monkeypatch) -> None:
    layer = Layer(name="Transform Final", width=28, height=18)
    layer.pixels[:] = np.array([0.3, 0.5, 0.7, 1.0], dtype=np.float32)
    layer.init_non_destructive()

    calls = {"scale": 0, "rotate": 0}
    original_scale = TransformEngine.scale
    original_rotate = TransformEngine.rotate

    def counting_scale(image, sx, sy, fast=False):
        calls["scale"] += 1
        return original_scale(image, sx, sy, fast=fast)

    def counting_rotate(image, angle, expand=True, fast=False):
        calls["rotate"] += 1
        return original_rotate(image, angle, expand=expand, fast=fast)

    monkeypatch.setattr(TransformEngine, "scale", staticmethod(counting_scale))
    monkeypatch.setattr(TransformEngine, "rotate", staticmethod(counting_rotate))

    layer.compute_display(scale_x=1.25, scale_y=1.4, angle=17.5, fast=False)
    first_pixels = layer.pixels.copy()
    layer.compute_display(scale_x=1.25, scale_y=1.4, angle=17.5, fast=False)
    second_pixels = layer.pixels.copy()

    assert calls == {"scale": 1, "rotate": 1}
    np.testing.assert_allclose(first_pixels, second_pixels)


def test_non_destructive_source_pixels_are_stored_as_uint8_at_rest() -> None:
    layer = Layer(name="Source", width=12, height=10)
    layer.pixels[:] = np.array([0.25, 0.5, 0.75, 1.0], dtype=np.float32)

    layer.init_non_destructive()

    assert layer._source_pixels is not None
    assert layer._source_pixels.dtype == np.uint8

    source_float = layer.source_pixels
    assert source_float.dtype == np.float32
    np.testing.assert_allclose(source_float, layer.pixels, atol=1 / 255.0)

    layer.transform_scale_x = 1.5
    layer.transform_scale_y = 1.5
    layer.compute_display(fast=True)

    assert layer.pixels.dtype == np.float32
    assert layer.width == 18
    assert layer.height == 15


def test_init_non_destructive_can_capture_from_compacted_display() -> None:
    layer = Layer(name="Compacted Source", width=14, height=12)
    layer.pixels[:] = np.array([0.15, 0.35, 0.75, 1.0], dtype=np.float32)
    layer.compact_display_storage()

    assert layer._pixels is None
    layer.init_non_destructive()

    assert layer._source_pixels is not None
    assert layer._source_pixels.dtype == np.uint8
    assert layer._pixels is None


def test_display_pixels_can_compact_to_uint8_and_materialize_lazily() -> None:
    layer = Layer(name="Display", width=10, height=8)
    layer.pixels[:] = np.array([0.2, 0.4, 0.6, 1.0], dtype=np.float32)

    layer.compact_display_storage()

    assert layer._pixels is None
    assert layer._pixels_u8 is not None
    assert layer._pixels_u8.dtype == np.uint8

    materialized = layer.pixels
    assert materialized.dtype == np.float32
    expected = np.broadcast_to(
        np.array([0.2, 0.4, 0.6, 1.0], dtype=np.float32),
        materialized.shape,
    )
    np.testing.assert_allclose(materialized, expected, atol=1 / 255.0)


def test_transformed_display_compacts_back_to_uint8_storage() -> None:
    layer = Layer(name="Transformed Compact", width=40, height=24)
    layer.pixels[:] = np.array([0.2, 0.6, 0.8, 1.0], dtype=np.float32)
    layer.init_non_destructive()

    layer.compute_display(scale_x=1.5, scale_y=1.25, angle=9.0, fast=False)

    assert layer._pixels is None
    assert layer._pixels_u8 is not None or layer._pixels_tile_store is not None
    materialized = layer.pixels
    assert materialized.dtype == np.float32


def test_point_reads_on_compacted_layer_do_not_materialize_display() -> None:
    layer = Layer(name="Point Read", width=300, height=220)
    layer.pixels[:] = 0.0
    layer.pixels[..., 3] = 1.0
    layer.pixels[100:140, 120:160] = np.array([0.9, 0.2, 0.1, 1.0], dtype=np.float32)
    layer.position = (10, 12)
    layer.compact_display_storage()

    assert point_on_layer(layer, 140, 130) is True
    assert layer._pixels is None

    sampled: list[np.ndarray] = []
    tool = EyedropperTool()
    tool.set_color_callback(lambda color: sampled.append(color.copy()))
    doc = Document(320, 240, "Point Read")
    doc.layers.add(layer)
    doc.layers.active_index = doc.layers.layers.index(layer)
    tool.on_press(doc, 140, 130)

    assert sampled
    assert layer._pixels is None
    assert float(sampled[0][0]) > 0.5


def test_large_display_pixels_compact_to_tiled_uint8_storage() -> None:
    layer = Layer(name="Large Display", width=520, height=300)
    layer.pixels[..., 0] = np.linspace(0.0, 1.0, layer.width, dtype=np.float32)
    layer.pixels[..., 1] = np.linspace(0.0, 1.0, layer.height, dtype=np.float32)[:, None]
    layer.pixels[..., 2] = 0.5
    layer.pixels[..., 3] = 1.0

    layer.compact_display_storage()

    assert layer._pixels is None
    assert layer._pixels_tile_store is not None
    assert layer._pixels_u8 is None

    decoded = layer.decode_display_roi(256, 128, 80, 64)
    assert decoded is not None
    roi, position = decoded
    assert position == (256, 128)
    expected = layer._u8_to_float(layer._pixels_tile_store.decode_roi(256, 128, 80, 64))
    np.testing.assert_allclose(roi, expected, atol=1 / 255.0)


def test_brush_mutates_compacted_tile_backing_locally() -> None:
    doc = Document(300, 220, "Brush Tile Local")
    layer = doc.layers[0]
    layer.pixels[:] = 0.0
    layer.pixels[..., 3] = 1.0
    layer.compact_display_storage()
    doc.layers.active_index = 0

    tool = BrushTool()
    tool.color = np.array([1.0, 0.0, 0.0, 1.0], dtype=np.float32)
    tool.size = 24
    tool.opacity = 1.0
    tool.flow = 1.0

    tool.on_press(doc, 120, 100, pressure=1.0)
    tool.on_release(doc, 120, 100)

    assert layer._pixels is None
    assert layer._pixels_tile_store is not None
    painted = layer.decode_display_roi(layer.position[0] + 100, layer.position[1] + 80, 40, 40)
    assert painted is not None
    region, _position = painted
    assert float(region[..., 0].max()) > 0.5


def test_bucket_mutates_compacted_tile_backing_locally() -> None:
    doc = Document(320, 240, "Bucket Tile Local")
    layer = doc.layers[0]
    layer.pixels[:] = 0.0
    layer.pixels[..., 3] = 1.0
    layer.pixels[80:160, 110:210, :3] = 0.2
    layer.compact_display_storage()
    doc.layers.active_index = 0

    tool = PaintBucketTool()
    tool.color = np.array([0.9, 0.1, 0.2, 1.0], dtype=np.float32)
    tool.opacity = 1.0
    tool.tolerance = 0.01
    tool.contiguous = True

    tool.on_press(doc, 140, 120)

    assert layer._pixels is None
    assert layer._pixels_tile_store is not None
    filled = layer.decode_display_roi(110, 80, 100, 80)
    assert filled is not None
    region, _position = filled
    assert float(region[..., 0].mean()) > 0.75


def test_clone_stamp_mutates_compacted_tile_backing_locally() -> None:
    doc = Document(320, 240, "Clone Tile Local")
    layer = doc.layers[0]
    layer.pixels[:] = 0.0
    layer.pixels[..., 3] = 1.0
    layer.pixels[70:110, 70:110] = np.array([1.0, 0.2, 0.1, 1.0], dtype=np.float32)
    layer.compact_display_storage()
    doc.layers.active_index = 0

    tool = CloneStampTool()
    tool.size = 24
    tool.hardness = 1.0
    tool.opacity = 1.0
    tool.set_source(90, 90)
    tool.on_press(doc, 210, 140)
    tool.on_release(doc, 210, 140)

    assert layer._pixels is None
    assert layer._pixels_tile_store is not None
    painted = layer.decode_display_roi(198, 128, 24, 24)
    assert painted is not None
    region, _position = painted
    assert float(region[..., 0].max()) > 0.5


def test_healing_brush_mutates_compacted_tile_backing_locally() -> None:
    doc = Document(320, 240, "Heal Tile Local")
    layer = doc.layers[0]
    layer.pixels[:] = 0.0
    layer.pixels[..., 3] = 1.0
    layer.pixels[70:110, 70:110, 0] = 1.0
    layer.pixels[70:110, 70:110, 1] = 0.7
    layer.pixels[130:170, 180:220, :3] = 0.15
    before = layer.pixels[130:170, 180:220, :3].copy()
    layer.compact_display_storage()
    doc.layers.active_index = 0

    tool = HealingBrushTool()
    tool.size = 26
    tool.hardness = 1.0
    tool.opacity = 1.0
    tool.set_source(90, 90)
    tool.on_press(doc, 200, 150)
    tool.on_release(doc, 200, 150)

    assert layer._pixels is None
    assert layer._pixels_tile_store is not None
    healed = layer.decode_display_roi(180, 130, 40, 40)
    assert healed is not None
    region, _position = healed
    assert float(np.abs(region[..., :3] - before).max()) > 0.1


def test_gradient_commit_mutates_compacted_tile_backing_locally() -> None:
    doc = Document(320, 220, "Gradient Tile Local")
    layer = doc.layers[0]
    layer.pixels[:] = np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float32)
    layer.compact_display_storage()
    doc.layers.active_index = 0

    tool = GradientTool()
    tool.on_press(doc, 40, 110)
    tool.on_move(doc, 260, 110)
    tool.on_release(doc, 260, 110)

    assert layer._pixels is None
    assert layer._pixels_tile_store is not None
    painted = layer.decode_display_roi(40, 80, 220, 60)
    assert painted is not None
    region, _position = painted
    assert float(region[..., 0].max() - region[..., 0].min()) > 0.5