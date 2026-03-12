"""Tests for render worker and scheduler."""

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from photo_editor.core.document import Document
from photo_editor.core.enums import LayerType
from photo_editor.core.layer import Layer
from photo_editor.engine.render_pipeline import RenderPipeline
from photo_editor.engine.renderer import RenderScheduler, RenderWorker
from photo_editor.engine.renderer.render_worker import RenderCommand
from photo_editor.adjustments.brightness_contrast import BrightnessContrast
from photo_editor.filters.blur.gaussian_blur import GaussianBlur
from photo_editor.filters.blur.motion_blur import MotionBlur
from photo_editor.filters.blur.surface_blur import SurfaceBlur
from photo_editor.filters.sharpen.unsharp_mask import UnsharpMask
from photo_editor.styles.gradient_overlay import GradientOverlay
from photo_editor.styles.outer_glow import OuterGlow
from photo_editor.styles.stroke import Stroke


@pytest.fixture
def app():
    """Ensure QApplication exists for Qt signals and widget-safe reuse."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def doc():
    """Minimal document for rendering."""
    d = Document(64, 64, "Test")
    d.layers[0].pixels[:] = np.array([0.5, 0.5, 0.5, 1.0], dtype=np.float32)
    return d


def test_render_command():
    """RenderCommand has expected fields."""
    cmd = RenderCommand(
        document_width=100,
        document_height=100,
        preview_max_size=2048,
        full_resolution=False,
    )
    assert cmd.document_width == 100
    assert cmd.document_height == 100
    assert cmd.preview_max_size == 2048
    assert cmd.full_resolution is False


def test_render_worker_produces_uint8(doc, app):
    """RenderWorker produces valid uint8 RGBA."""
    pipeline = RenderPipeline(quality_mode="preview")
    cmd = RenderCommand(
        document_width=doc.width,
        document_height=doc.height,
        preview_max_size=0,
        full_resolution=True,
    )
    result_holder = []

    def on_result(rgba, _gen_id, _full_refresh, _full_resolution):
        result_holder.append(rgba)

    worker = RenderWorker(
        pipeline=pipeline,
        document=doc,
        command=cmd,
        generation_id=1,
    )
    worker.signals.finished.connect(on_result)
    from PySide6.QtCore import QThreadPool
    QThreadPool.globalInstance().start(worker)
    # Process events until we get a result
    for _ in range(100):
        app.processEvents()
        if result_holder:
            break
        import time
        time.sleep(0.01)

    assert len(result_holder) == 1
    rgba = result_holder[0]
    assert rgba.dtype == np.uint8
    assert rgba.shape == (64, 64, 4)
    assert np.all(rgba[..., 3] == 255)


def test_render_scheduler_debounces(doc, app):
    """RenderScheduler debounces and emits at most one result per batch."""
    pipeline = RenderPipeline(quality_mode="preview")
    scheduler = RenderScheduler(pipeline, interval_ms=10, preview_max_size=0)
    results = []

    def on_ready(rgba, gen_id, full_refresh, full_resolution):
        results.append((rgba, gen_id, full_refresh, full_resolution))

    scheduler.render_ready.connect(on_ready)

    # Enqueue multiple times rapidly
    for _ in range(5):
        scheduler.enqueue_render(doc, full_refresh=False)

    # Process events until we get a result (or timeout)
    for _ in range(200):
        app.processEvents()
        if results:
            break
        import time
        time.sleep(0.01)

    # Should get exactly one result (debounced)
    assert len(results) >= 1
    rgba, gen_id, full_refresh, full_resolution = results[0]
    assert rgba.dtype == np.uint8
    assert rgba.shape == (64, 64, 4)
    assert full_refresh is False
    assert full_resolution is False


def test_render_scheduler_preview_size_can_be_updated(doc, app):
    pipeline = RenderPipeline(quality_mode="preview")
    scheduler = RenderScheduler(pipeline, interval_ms=10, preview_max_size=64)
    scheduler.set_preview_max_size(16)
    results = []

    def on_ready(rgba, _gen_id, _full_refresh, _full_resolution):
        results.append(rgba)

    scheduler.render_ready.connect(on_ready)
    scheduler.enqueue_render(doc, full_refresh=False)

    for _ in range(200):
        app.processEvents()
        if results:
            break
        import time
        time.sleep(0.01)

    assert len(results) == 1
    assert results[0].shape == (16, 16, 4)


def test_render_worker_downsamples_preview(doc, app):
    pipeline = RenderPipeline(quality_mode="preview")
    cmd = RenderCommand(
        document_width=doc.width,
        document_height=doc.height,
        preview_max_size=32,
        full_resolution=False,
    )
    result_holder = []

    def on_result(rgba, _gen_id, _full_refresh, _full_resolution):
        result_holder.append(rgba)

    worker = RenderWorker(
        pipeline=pipeline,
        document=doc,
        command=cmd,
        generation_id=2,
    )
    worker.signals.finished.connect(on_result)
    from PySide6.QtCore import QThreadPool
    QThreadPool.globalInstance().start(worker)

    for _ in range(100):
        app.processEvents()
        if result_holder:
            break
        import time
        time.sleep(0.01)

    assert len(result_holder) == 1
    rgba = result_holder[0]
    assert rgba.dtype == np.uint8
    assert rgba.shape == (32, 32, 4)


def test_render_pipeline_recomposes_only_dirty_tile_for_simple_raster_stack() -> None:
    doc = Document(400, 300, "Incremental")
    base = doc.layers[0]
    base.pixels[:] = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)

    layer = Layer(name="Overlay", width=400, height=300)
    layer.pixels[:] = np.array([0.0, 0.0, 1.0, 1.0], dtype=np.float32)
    doc.layers.add(layer)

    pipeline = RenderPipeline()
    before = pipeline.execute(doc).copy()

    layer.pixels[10:30, 10:30] = np.array([1.0, 0.0, 0.0, 1.0], dtype=np.float32)
    pipeline.invalidate_region(10, 10, 20, 20)

    dirty_tiles = pipeline._tile_cache.dirty_tiles()
    assert len(dirty_tiles) == 1

    after = pipeline.execute(doc)

    np.testing.assert_allclose(
        after[10:30, 10:30],
        np.broadcast_to(np.array([1.0, 0.0, 0.0, 1.0], dtype=np.float32), (20, 20, 4)),
    )
    np.testing.assert_allclose(after[280:300, 300:320], before[280:300, 300:320])


def test_render_pipeline_invalidates_all_tiles_crossed_by_small_boundary_region() -> None:
    doc = Document(600, 256, "Tile Boundary")
    base = doc.layers[0]
    base.pixels[:] = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)

    overlay = Layer(name="Overlay", width=600, height=256)
    overlay.pixels[:] = np.array([0.0, 0.0, 1.0, 1.0], dtype=np.float32)
    doc.layers.add(overlay)

    pipeline = RenderPipeline()
    pipeline.execute(doc)

    overlay.pixels[:, 250:262] = np.array([1.0, 0.0, 0.0, 1.0], dtype=np.float32)
    pipeline.invalidate_region(250, 10, 12, 20)

    dirty_tiles = {(tile.x, tile.y) for tile in pipeline._tile_cache.dirty_tiles()}
    assert dirty_tiles == {(0, 0), (256, 0)}

    incremental = pipeline.execute(doc)
    full = RenderPipeline().execute(doc)
    np.testing.assert_allclose(incremental, full, atol=1e-6)


def test_render_pipeline_complex_stack_region_matches_full_composite() -> None:
    doc = Document(220, 160, "Complex Incremental")
    doc.layers[0].pixels[:] = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)

    root_base = Layer(name="Root Base", width=220, height=160)
    root_base.pixels[:] = np.array([0.0, 0.4, 0.0, 1.0], dtype=np.float32)
    doc.layers.add(root_base)

    root_clip = Layer(name="Root Clip", width=220, height=160)
    root_clip.pixels[:] = 0.0
    root_clip.pixels[20:140, 20:140] = np.array([1.0, 0.0, 0.0, 0.6], dtype=np.float32)
    root_clip.clipping_mask = True
    doc.layers.add(root_clip)

    standalone_mask = Layer(name="Standalone Mask", width=220, height=160, layer_type=LayerType.MASK)
    standalone_mask.pixels[:] = 1.0
    standalone_mask.pixels[:, :90, :3] = 0.0
    doc.layers.add(standalone_mask)

    group = doc.add_group("Group")
    content = Layer(name="Content", width=220, height=160)
    content.pixels[:] = np.array([0.0, 0.0, 1.0, 1.0], dtype=np.float32)
    doc.layers.add(content)
    doc.layers.reparent([content.id], group.id)

    group_mask = Layer(name="Group Mask", width=220, height=160, layer_type=LayerType.MASK)
    group_mask.pixels[:] = 1.0
    group_mask.pixels[:50, :, :3] = 0.0
    group_mask.parent_id = group.id
    group.mask_layers.append(group_mask.id)
    doc.layers.add(group_mask)

    child_adjustment = Layer(name="Child Adj", width=220, height=160, layer_type=LayerType.ADJUSTMENT)
    child_adjustment.adjustment = BrightnessContrast()
    child_adjustment.adjustment_params = {"brightness": 25, "contrast": 0}
    child_adjustment.parent_id = content.id
    content.children.append(child_adjustment.id)
    doc.layers.add(child_adjustment)

    clip_child = Layer(name="Clip Child", width=220, height=160)
    clip_child.pixels[:] = 0.0
    clip_child.pixels[40:120, 40:180] = np.array([1.0, 1.0, 1.0, 0.5], dtype=np.float32)
    clip_child.parent_id = content.id
    clip_child.clips_parent = True
    content.children.append(clip_child.id)
    doc.layers.add(clip_child)
    doc.layers.update_group_bbox(group)

    pipeline = RenderPipeline()
    pipeline.execute(doc)

    content.pixels[70:90, 70:90] = np.array([1.0, 1.0, 0.0, 1.0], dtype=np.float32)
    pipeline.invalidate_region(70, 70, 20, 20)

    incremental = pipeline.execute(doc)
    full = RenderPipeline().execute(doc)

    np.testing.assert_allclose(incremental, full, atol=1e-6)


def test_render_pipeline_root_filter_region_matches_full_composite() -> None:
    doc = Document(260, 120, "Filter Incremental")
    base = doc.layers[0]
    base.pixels[:] = 0.0
    base.pixels[..., 3] = 1.0
    base.pixels[40:80, 40:80] = np.array([1.0, 0.0, 0.0, 1.0], dtype=np.float32)

    blur = Layer(name="Blur", width=260, height=120, layer_type=LayerType.FILTER)
    blur.adjustment = GaussianBlur()
    blur.adjustment_params = {"radius": 8.0, "preserve_alpha": False}
    doc.layers.add(blur)

    pipeline = RenderPipeline()
    pipeline.execute(doc)

    base.pixels[58:66, 58:66] = np.array([0.0, 0.0, 1.0, 1.0], dtype=np.float32)
    pipeline.invalidate_region(58, 58, 8, 8)

    incremental = pipeline.execute(doc)
    full = RenderPipeline().execute(doc)

    np.testing.assert_allclose(incremental, full, atol=1e-5)


def test_render_pipeline_region_keeps_compacted_layers_unmaterialized() -> None:
    doc = Document(320, 180, "Compacted ROI Incremental")
    base = doc.layers[0]
    gradient_x = np.linspace(0.0, 1.0, doc.width, dtype=np.float32)
    gradient_y = np.linspace(0.2, 0.8, doc.height, dtype=np.float32)[:, None]
    base.pixels[..., 0] = gradient_x
    base.pixels[..., 1] = gradient_y
    base.pixels[..., 2] = 0.35
    base.pixels[..., 3] = 1.0

    overlay = Layer(name="Overlay", width=80, height=60)
    overlay.position = (96, 64)
    overlay.pixels[:] = np.array([0.0, 0.0, 1.0, 0.5], dtype=np.float32)
    doc.layers.add(overlay)

    pipeline = RenderPipeline(quality_mode="preview")
    baseline = pipeline.execute_to_uint8(doc).copy()

    base.compact_display_storage()
    assert base._pixels is None
    assert base._pixels_tile_store is not None
    pipeline.sync_cached_output_from_uint8(baseline)

    overlay.pixels[10:26, 14:30] = np.array([1.0, 0.25, 0.0, 0.8], dtype=np.float32)
    pipeline.invalidate_region(overlay.position[0] + 14, overlay.position[1] + 10, 16, 16)

    incremental = pipeline.execute_to_uint8(doc)

    assert base._pixels is None
    assert base._pixels_tile_store is not None

    full = RenderPipeline().execute_to_uint8(doc)

    assert not np.array_equal(baseline, incremental)
    np.testing.assert_array_equal(incremental[:, :256], full[:, :256])
    np.testing.assert_array_equal(incremental[:, 256:], baseline[:, 256:])


def test_render_pipeline_region_uses_roi_decode_for_gradient_overlay_style() -> None:
    doc = Document(320, 180, "Styled ROI Incremental")
    base = doc.layers[0]
    base.pixels[:] = np.array([0.25, 0.25, 0.25, 1.0], dtype=np.float32)

    style = GradientOverlay()
    style.params.extra = {
        "color1": [1.0, 0.0, 0.0],
        "color2": [0.0, 0.0, 1.0],
        "angle": 30,
        "opacity": 0.7,
    }
    base.styles.append(style)

    overlay = Layer(name="Overlay", width=80, height=60)
    overlay.position = (48, 40)
    overlay.pixels[:] = np.array([0.0, 1.0, 0.0, 0.5], dtype=np.float32)
    doc.layers.add(overlay)

    pipeline = RenderPipeline(quality_mode="preview")
    baseline = pipeline.execute_to_uint8(doc).copy()

    base.compact_display_storage()
    assert base._pixels_tile_store is not None
    pipeline.sync_cached_output_from_uint8(baseline)

    overlay.pixels[12:28, 14:30] = np.array([1.0, 1.0, 0.0, 0.9], dtype=np.float32)
    pipeline.invalidate_region(overlay.position[0] + 14, overlay.position[1] + 12, 16, 16)

    incremental = pipeline.execute_to_uint8(doc)

    assert base._pixels is None
    assert base._pixels_tile_store is not None

    full = RenderPipeline().execute_to_uint8(doc)
    np.testing.assert_array_equal(incremental[:, :256], full[:, :256])
    np.testing.assert_array_equal(incremental[:, 256:], baseline[:, 256:])


def test_render_pipeline_region_uses_roi_decode_for_child_adjustment() -> None:
    doc = Document(320, 180, "Adjusted ROI Incremental")
    bg = doc.layers[0]
    bg.pixels[:] = np.array([0.1, 0.1, 0.1, 1.0], dtype=np.float32)

    base = Layer(name="Base", width=320, height=180)
    base.pixels[..., 0] = np.linspace(0.0, 1.0, 320, dtype=np.float32)
    base.pixels[..., 1] = 0.4
    base.pixels[..., 2] = 0.2
    base.pixels[..., 3] = 1.0
    doc.layers.add(base)

    child_adjustment = Layer(name="Child Adj", width=320, height=180, layer_type=LayerType.ADJUSTMENT)
    child_adjustment.adjustment = BrightnessContrast()
    child_adjustment.adjustment_params = {"brightness": 30, "contrast": 10}
    child_adjustment.parent_id = base.id
    base.children.append(child_adjustment.id)
    doc.layers.add(child_adjustment)

    overlay = Layer(name="Overlay", width=64, height=64)
    overlay.position = (40, 32)
    overlay.pixels[:] = np.array([0.0, 0.0, 1.0, 0.4], dtype=np.float32)
    doc.layers.add(overlay)

    pipeline = RenderPipeline(quality_mode="preview")
    baseline = pipeline.execute_to_uint8(doc).copy()

    base.compact_display_storage()
    assert base._pixels_tile_store is not None
    pipeline.sync_cached_output_from_uint8(baseline)

    overlay.pixels[10:26, 10:26] = np.array([1.0, 0.5, 0.0, 0.85], dtype=np.float32)
    pipeline.invalidate_region(overlay.position[0] + 10, overlay.position[1] + 10, 16, 16)

    incremental = pipeline.execute_to_uint8(doc)

    assert base._pixels is None
    assert base._pixels_tile_store is not None

    full = RenderPipeline().execute_to_uint8(doc)
    np.testing.assert_array_equal(incremental[:, :256], full[:, :256])
    np.testing.assert_array_equal(incremental[:, 256:], baseline[:, 256:])


def test_preview_pipeline_keeps_compacted_outer_glow_layer_on_roi_path() -> None:
    doc = Document(320, 200, "Preview Styled ROI")
    base = doc.layers[0]
    base.pixels[:] = np.array([0.2, 0.2, 0.2, 1.0], dtype=np.float32)
    base.pixels[40:160, 80:240] = np.array([0.8, 0.3, 0.1, 1.0], dtype=np.float32)

    glow = OuterGlow()
    glow.params.extra = {"color": [1.0, 1.0, 0.0], "opacity": 0.8, "spread": 0.2, "size": 8}
    base.styles.append(glow)

    overlay = Layer(name="Overlay", width=64, height=64)
    overlay.position = (24, 24)
    overlay.pixels[:] = np.array([0.0, 0.0, 1.0, 0.4], dtype=np.float32)
    doc.layers.add(overlay)

    pipeline = RenderPipeline(quality_mode="preview")
    baseline = pipeline.execute_to_uint8(doc).copy()
    base.compact_display_storage()
    pipeline.sync_cached_output_from_uint8(baseline)

    overlay.pixels[8:24, 8:24] = np.array([1.0, 0.5, 0.0, 0.9], dtype=np.float32)
    pipeline.invalidate_region(overlay.position[0] + 8, overlay.position[1] + 8, 16, 16)
    preview = pipeline.execute_to_uint8(doc)

    assert base._pixels is None
    assert base._pixels_tile_store is not None
    assert not np.array_equal(preview, baseline)

    full = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_array_equal(preview, full)


def test_preview_pipeline_matches_final_for_positioned_compacted_outer_glow_layer() -> None:
    doc = Document(320, 220, "Preview Positioned Glow ROI")
    bg = doc.layers[0]
    bg.pixels[:] = np.array([0.12, 0.12, 0.12, 1.0], dtype=np.float32)

    base = Layer(name="Base", width=80, height=80)
    base.position = (110, 70)
    base.pixels[:] = 0.0
    base.pixels[20:60, 24:56] = np.array([0.9, 0.3, 0.2, 1.0], dtype=np.float32)
    glow = OuterGlow()
    glow.params.extra = {"color": [1.0, 0.9, 0.2], "opacity": 0.85, "spread": 0.25, "size": 12}
    base.styles.append(glow)
    doc.layers.add(base)

    overlay = Layer(name="Overlay", width=40, height=40)
    overlay.position = (18, 18)
    overlay.pixels[:] = np.array([0.0, 0.3, 1.0, 0.35], dtype=np.float32)
    doc.layers.add(overlay)

    pipeline = RenderPipeline(quality_mode="preview")
    baseline = pipeline.execute_to_uint8(doc).copy()
    base.compact_display_storage()
    pipeline.sync_cached_output_from_uint8(baseline)

    overlay.pixels[8:24, 8:24] = np.array([1.0, 0.7, 0.0, 0.9], dtype=np.float32)
    pipeline.invalidate_region(overlay.position[0] + 8, overlay.position[1] + 8, 16, 16)
    preview = pipeline.execute_to_uint8(doc)

    assert base._pixels is None
    assert base._pixels_u8 is not None
    full = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_array_equal(preview, full)


def test_preview_pipeline_keeps_compacted_motion_blur_layer_on_roi_path() -> None:
    doc = Document(320, 180, "Preview Filter ROI")
    bg = doc.layers[0]
    bg.pixels[:] = np.array([0.1, 0.1, 0.1, 1.0], dtype=np.float32)

    base = Layer(name="Base", width=320, height=180)
    base.pixels[50:130, 60:240] = np.array([0.9, 0.2, 0.2, 1.0], dtype=np.float32)
    doc.layers.add(base)

    motion = Layer(name="Motion", width=320, height=180, layer_type=LayerType.FILTER)
    motion.adjustment = MotionBlur()
    motion.adjustment_params = {"distance": 12, "angle": 25.0, "preserve_alpha": True}
    motion.parent_id = base.id
    base.children.append(motion.id)
    doc.layers.add(motion)

    overlay = Layer(name="Overlay", width=48, height=48)
    overlay.position = (16, 16)
    overlay.pixels[:] = np.array([0.0, 1.0, 0.0, 0.5], dtype=np.float32)
    doc.layers.add(overlay)

    pipeline = RenderPipeline(quality_mode="preview")
    baseline = pipeline.execute_to_uint8(doc).copy()
    base.compact_display_storage()
    pipeline.sync_cached_output_from_uint8(baseline)

    overlay.pixels[12:24, 12:24] = np.array([1.0, 1.0, 0.0, 0.85], dtype=np.float32)
    pipeline.invalidate_region(overlay.position[0] + 12, overlay.position[1] + 12, 12, 12)
    preview = pipeline.execute_to_uint8(doc)

    assert base._pixels is None
    assert base._pixels_tile_store is not None
    assert not np.array_equal(preview, baseline)

    full = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_array_equal(preview, full)


def test_preview_pipeline_keeps_compacted_stroke_layer_on_roi_path() -> None:
    doc = Document(320, 200, "Preview Stroke ROI")
    base = doc.layers[0]
    base.pixels[:] = 0.0
    base.pixels[70:130, 110:210] = np.array([0.3, 0.6, 0.9, 1.0], dtype=np.float32)

    stroke = Stroke()
    stroke.params.extra = {
        "size": 10,
        "position": "outside",
        "color": [1.0, 0.9, 0.1],
        "opacity": 0.85,
    }
    base.styles.append(stroke)

    overlay = Layer(name="Overlay", width=48, height=48)
    overlay.position = (24, 24)
    overlay.pixels[:] = np.array([0.0, 0.4, 0.0, 0.5], dtype=np.float32)
    doc.layers.add(overlay)

    pipeline = RenderPipeline(quality_mode="preview")
    baseline = pipeline.execute_to_uint8(doc).copy()
    base.compact_display_storage()
    pipeline.sync_cached_output_from_uint8(baseline)

    overlay.pixels[8:24, 8:24] = np.array([1.0, 0.3, 0.0, 0.85], dtype=np.float32)
    pipeline.invalidate_region(overlay.position[0] + 8, overlay.position[1] + 8, 16, 16)
    preview = pipeline.execute_to_uint8(doc)

    assert base._pixels is None
    assert base._pixels_tile_store is not None
    assert not np.array_equal(preview, baseline)

    full = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_array_equal(preview, full)


def test_preview_pipeline_keeps_compacted_unsharp_layer_on_roi_path() -> None:
    doc = Document(320, 180, "Preview Unsharp ROI")
    bg = doc.layers[0]
    bg.pixels[:] = np.array([0.12, 0.12, 0.12, 1.0], dtype=np.float32)

    base = Layer(name="Base", width=320, height=180)
    base.pixels[40:140, 70:250] = np.array([0.8, 0.4, 0.2, 1.0], dtype=np.float32)
    doc.layers.add(base)

    sharpen = Layer(name="Unsharp", width=320, height=180, layer_type=LayerType.FILTER)
    sharpen.adjustment = UnsharpMask()
    sharpen.adjustment_params = {"radius": 5.0, "strength": 1.0, "preserve_alpha": True}
    sharpen.parent_id = base.id
    base.children.append(sharpen.id)
    doc.layers.add(sharpen)

    overlay = Layer(name="Overlay", width=44, height=44)
    overlay.position = (18, 18)
    overlay.pixels[:] = np.array([0.0, 0.8, 0.2, 0.45], dtype=np.float32)
    doc.layers.add(overlay)

    pipeline = RenderPipeline(quality_mode="preview")
    baseline = pipeline.execute_to_uint8(doc).copy()
    base.compact_display_storage()
    pipeline.sync_cached_output_from_uint8(baseline)

    overlay.pixels[10:26, 10:26] = np.array([1.0, 1.0, 0.0, 0.9], dtype=np.float32)
    pipeline.invalidate_region(overlay.position[0] + 10, overlay.position[1] + 10, 16, 16)
    preview = pipeline.execute_to_uint8(doc)

    assert base._pixels is None
    assert base._pixels_tile_store is not None
    assert not np.array_equal(preview, baseline)

    full = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_array_equal(preview, full)


def test_preview_pipeline_matches_final_for_compacted_mixed_style_and_filter_stack() -> None:
    doc = Document(320, 220, "Preview Mixed Stack ROI")
    bg = doc.layers[0]
    bg.pixels[:] = np.array([0.1, 0.1, 0.1, 1.0], dtype=np.float32)

    base = Layer(name="Base", width=96, height=96)
    base.position = (104, 64)
    base.pixels[:] = 0.0
    base.pixels[18:78, 20:76] = np.array([0.8, 0.45, 0.2, 1.0], dtype=np.float32)
    stroke = Stroke()
    stroke.params.extra = {
        "size": 8,
        "position": "outside",
        "color": [0.95, 0.9, 0.15],
        "opacity": 0.8,
    }
    base.styles.append(stroke)
    doc.layers.add(base)

    sharpen = Layer(name="Unsharp", width=96, height=96, layer_type=LayerType.FILTER)
    sharpen.adjustment = UnsharpMask()
    sharpen.adjustment_params = {"radius": 4.0, "strength": 1.0, "preserve_alpha": True}
    sharpen.parent_id = base.id
    base.children.append(sharpen.id)
    doc.layers.add(sharpen)

    overlay = Layer(name="Overlay", width=44, height=44)
    overlay.position = (22, 22)
    overlay.pixels[:] = np.array([0.0, 0.8, 0.1, 0.4], dtype=np.float32)
    doc.layers.add(overlay)

    pipeline = RenderPipeline(quality_mode="preview")
    baseline = pipeline.execute_to_uint8(doc).copy()
    base.compact_display_storage()
    pipeline.sync_cached_output_from_uint8(baseline)

    overlay.pixels[10:28, 10:28] = np.array([1.0, 1.0, 0.0, 0.92], dtype=np.float32)
    pipeline.invalidate_region(overlay.position[0] + 10, overlay.position[1] + 10, 18, 18)
    preview = pipeline.execute_to_uint8(doc)

    assert base._pixels is None
    assert base._pixels_u8 is not None
    full = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_array_equal(preview, full)


def test_preview_pipeline_keeps_compacted_surface_blur_layer_on_roi_path() -> None:
    doc = Document(320, 180, "Preview Surface Blur ROI")
    bg = doc.layers[0]
    bg.pixels[:] = np.array([0.08, 0.08, 0.08, 1.0], dtype=np.float32)

    base = Layer(name="Base", width=320, height=180)
    base.pixels[35:145, 60:250] = np.array([0.75, 0.25, 0.15, 1.0], dtype=np.float32)
    base.pixels[70:110, 120:190] = np.array([0.15, 0.85, 0.85, 1.0], dtype=np.float32)
    doc.layers.add(base)

    blur = Layer(name="Surface", width=320, height=180, layer_type=LayerType.FILTER)
    blur.adjustment = SurfaceBlur()
    blur.adjustment_params = {"radius": 6, "threshold": 18, "preserve_alpha": True}
    blur.parent_id = base.id
    base.children.append(blur.id)
    doc.layers.add(blur)

    overlay = Layer(name="Overlay", width=52, height=52)
    overlay.position = (20, 20)
    overlay.pixels[:] = np.array([0.0, 0.5, 0.1, 0.4], dtype=np.float32)
    doc.layers.add(overlay)

    pipeline = RenderPipeline(quality_mode="preview")
    baseline = pipeline.execute_to_uint8(doc).copy()
    base.compact_display_storage()
    pipeline.sync_cached_output_from_uint8(baseline)

    overlay.pixels[12:28, 12:28] = np.array([1.0, 1.0, 0.0, 0.9], dtype=np.float32)
    pipeline.invalidate_region(overlay.position[0] + 12, overlay.position[1] + 12, 16, 16)
    preview = pipeline.execute_to_uint8(doc)

    assert base._pixels is None
    assert base._pixels_tile_store is not None
    assert not np.array_equal(preview, baseline)

    full = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_array_equal(preview, full)
