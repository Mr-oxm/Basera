import numpy as np
import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from photo_editor.adjustments.brightness_contrast import BrightnessContrast
from photo_editor.core.document import Document
from photo_editor.core.enums import BlendMode, LayerType
from photo_editor.core.layer import Layer
from photo_editor.engine.gpu_backend import QtGpuCompositorBackend
from photo_editor.engine.render_pipeline import RenderPipeline
from photo_editor.filters.blur.gaussian_blur import GaussianBlur
from photo_editor.styles.outer_glow import OuterGlow


@pytest.fixture
def app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _image_to_array(image: QImage) -> np.ndarray:
    converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
    buffer = converted.bits()
    arr = np.frombuffer(buffer, dtype=np.uint8, count=converted.width() * converted.height() * 4)
    return arr.reshape((converted.height(), converted.width(), 4)).copy()


def _render_with_backend(backend: QtGpuCompositorBackend, doc: Document) -> np.ndarray:
    image = QImage(doc.width, doc.height, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    ok = backend.render_document(painter, doc, QRectF(0, 0, doc.width, doc.height))
    painter.end()
    assert ok is True
    return _image_to_array(image)


def test_qt_gpu_backend_matches_cpu_for_supported_flat_stack(app) -> None:
    doc = Document(64, 64, "GPU Simple")
    base = doc.layers[0]
    base.pixels[:] = np.array([0.2, 0.25, 0.3, 1.0], dtype=np.float32)

    overlay = Layer(name="Overlay", width=64, height=64)
    overlay.pixels[:] = 0.0
    overlay.pixels[8:40, 10:46] = np.array([0.9, 0.3, 0.2, 0.75], dtype=np.float32)
    overlay.blend_mode = BlendMode.NORMAL
    doc.layers.add(overlay)

    multiply = Layer(name="Multiply", width=64, height=64)
    multiply.pixels[:] = 0.0
    multiply.pixels[20:56, 18:54] = np.array([0.5, 0.8, 0.4, 0.6], dtype=np.float32)
    multiply.blend_mode = BlendMode.MULTIPLY
    doc.layers.add(multiply)

    backend = QtGpuCompositorBackend()
    assert backend.can_render_document(doc) is True

    image = QImage(doc.width, doc.height, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    ok = backend.render_document(painter, doc, QRectF(0, 0, doc.width, doc.height))
    painter.end()

    assert ok is True
    gpu_like = _image_to_array(image)
    cpu = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_allclose(gpu_like, cpu, atol=1)


def test_qt_gpu_backend_rejects_styled_document(app) -> None:
    doc = Document(64, 64, "GPU Unsupported")
    base = doc.layers[0]
    glow = OuterGlow()
    base.styles.append(glow)

    backend = QtGpuCompositorBackend()
    assert backend.can_render_document(doc) is True

    image = QImage(doc.width, doc.height, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    ok = backend.render_document(painter, doc, QRectF(0, 0, doc.width, doc.height))
    painter.end()

    assert ok is True
    gpu_like = _image_to_array(image)
    cpu = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_allclose(gpu_like, cpu, atol=1)


def test_qt_gpu_backend_supports_child_filter_document(app) -> None:
    doc = Document(64, 64, "GPU Child Filter")
    base = doc.layers[0]
    child = Layer(name="Filter", width=64, height=64, layer_type=LayerType.FILTER)
    child.parent_id = base.id
    base.children.append(child.id)
    from photo_editor.filters.sharpen.unsharp_mask import UnsharpMask
    child.adjustment = UnsharpMask()
    child.adjustment_params = {"radius": 3.0, "strength": 1.0, "preserve_alpha": True}
    doc.layers.add(child)

    backend = QtGpuCompositorBackend()
    assert backend.can_render_document(doc) is True

    image = QImage(doc.width, doc.height, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    ok = backend.render_document(painter, doc, QRectF(0, 0, doc.width, doc.height))
    painter.end()

    assert ok is True
    gpu_like = _image_to_array(image)
    cpu = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_allclose(gpu_like, cpu, atol=1)


def test_qt_gpu_backend_supports_legacy_masked_layer_document(app) -> None:
    doc = Document(64, 64, "GPU Legacy Mask")
    base = doc.layers[0]
    base.pixels[:] = 0.0
    base.pixels[10:54, 10:54] = np.array([0.8, 0.35, 0.2, 1.0], dtype=np.float32)
    base.add_mask(fill_white=False)
    assert base.mask is not None
    base.mask[18:44, 18:44] = 1.0

    backend = QtGpuCompositorBackend()
    assert backend.can_render_document(doc) is True

    image = QImage(doc.width, doc.height, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    ok = backend.render_document(painter, doc, QRectF(0, 0, doc.width, doc.height))
    painter.end()

    assert ok is True
    gpu_like = _image_to_array(image)
    cpu = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_allclose(gpu_like, cpu, atol=1)


def test_qt_gpu_backend_supports_child_mask_layer_document(app) -> None:
    doc = Document(64, 64, "GPU Child Mask")
    base = doc.layers[0]
    base.pixels[:] = 0.0
    base.pixels[8:56, 8:56] = np.array([0.15, 0.55, 0.9, 1.0], dtype=np.float32)
    mask = doc.add_mask_layer(target_id=base.id, fill_white=False, name="Base Mask")
    assert mask is not None
    mask.pixels[16:48, 20:44, :3] = 1.0

    backend = QtGpuCompositorBackend()
    assert backend.can_render_document(doc) is True

    image = QImage(doc.width, doc.height, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    ok = backend.render_document(painter, doc, QRectF(0, 0, doc.width, doc.height))
    painter.end()

    assert ok is True
    gpu_like = _image_to_array(image)
    cpu = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_allclose(gpu_like, cpu, atol=1)


def test_qt_gpu_backend_supports_channel_filtered_layer_document(app) -> None:
    doc = Document(64, 64, "GPU Channels")
    base = doc.layers[0]
    base.pixels[:] = 0.0
    base.pixels[10:54, 12:52] = np.array([0.8, 0.4, 0.2, 1.0], dtype=np.float32)
    base.channel_g = False
    base.channel_a = False

    backend = QtGpuCompositorBackend()
    assert backend.can_render_document(doc) is True

    image = QImage(doc.width, doc.height, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    ok = backend.render_document(painter, doc, QRectF(0, 0, doc.width, doc.height))
    painter.end()

    assert ok is True
    gpu_like = _image_to_array(image)
    cpu = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_allclose(gpu_like, cpu, atol=1)


def test_qt_gpu_backend_supports_group_document(app) -> None:
    doc = Document(64, 64, "GPU Group")
    group = doc.add_group("Group")
    child = Layer(name="Child", width=32, height=32)
    child.position = (14, 16)
    child.pixels[:] = 0.0
    child.pixels[4:28, 6:26] = np.array([0.85, 0.25, 0.15, 0.9], dtype=np.float32)
    child.parent_id = group.id
    group.children.append(child.id)
    doc.layers.add(child)

    backend = QtGpuCompositorBackend()
    assert backend.can_render_document(doc) is True

    image = QImage(doc.width, doc.height, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    ok = backend.render_document(painter, doc, QRectF(0, 0, doc.width, doc.height))
    painter.end()

    assert ok is True
    gpu_like = _image_to_array(image)
    cpu = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_allclose(gpu_like, cpu, atol=1)


def test_qt_gpu_backend_supports_channel_filtered_group_document(app) -> None:
    doc = Document(64, 64, "GPU Group Channels")
    group = doc.add_group("Group")
    child = Layer(name="Child", width=28, height=28)
    child.position = (18, 20)
    child.pixels[:] = np.array([0.25, 0.85, 0.35, 1.0], dtype=np.float32)
    child.parent_id = group.id
    group.children.append(child.id)
    group.channel_b = False
    group.channel_a = False
    doc.layers.add(child)

    backend = QtGpuCompositorBackend()
    assert backend.can_render_document(doc) is True

    image = QImage(doc.width, doc.height, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    ok = backend.render_document(painter, doc, QRectF(0, 0, doc.width, doc.height))
    painter.end()

    assert ok is True
    gpu_like = _image_to_array(image)
    cpu = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_allclose(gpu_like, cpu, atol=1)


def test_qt_gpu_backend_supports_top_level_clipping_chain_document(app) -> None:
    doc = Document(64, 64, "GPU Clip")
    base = doc.layers[0]
    base.pixels[:] = 0.0
    base.pixels[8:56, 8:56] = np.array([0.15, 0.45, 0.8, 1.0], dtype=np.float32)

    clip = Layer(name="Clip", width=64, height=64)
    clip.pixels[:] = 0.0
    clip.pixels[20:48, 16:52] = np.array([1.0, 0.2, 0.1, 0.75], dtype=np.float32)
    clip.clipping_mask = True
    doc.layers.add(clip)

    backend = QtGpuCompositorBackend()
    assert backend.can_render_document(doc) is True

    image = QImage(doc.width, doc.height, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    ok = backend.render_document(painter, doc, QRectF(0, 0, doc.width, doc.height))
    painter.end()

    assert ok is True
    gpu_like = _image_to_array(image)
    cpu = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_allclose(gpu_like, cpu, atol=1)


def test_qt_gpu_backend_tracks_clipping_chain_as_cache_bearing_graph_segment(app) -> None:
    doc = Document(64, 64, "GPU Clip Graph")
    base = doc.layers[0]
    base.pixels[:] = 0.0
    base.pixels[8:56, 8:56] = np.array([0.15, 0.45, 0.8, 1.0], dtype=np.float32)

    clip = Layer(name="Clip", width=64, height=64)
    clip.pixels[:] = 0.0
    clip.pixels[20:48, 16:52] = np.array([1.0, 0.2, 0.1, 0.75], dtype=np.float32)
    clip.clipping_mask = True
    doc.layers.add(clip)

    backend = QtGpuCompositorBackend()
    graph = backend._build_top_level_graph(backend._top_level_visible_layers(doc))

    assert [(type(segment).__name__, segment.cache_key, tuple(layer.id for layer in segment.layers)) for segment in graph] == [
        ("_ChainNode", base.id, (base.id, clip.id)),
    ]
    assert backend._invalidation_keys_for_document(doc, base.id) == [base.id]
    assert backend._invalidation_keys_for_document(doc, clip.id) == [base.id]


def test_qt_gpu_backend_supports_standalone_root_mask_document(app) -> None:
    doc = Document(64, 64, "GPU Standalone Mask")
    base = doc.layers[0]
    base.pixels[:] = np.array([0.1, 0.5, 0.85, 1.0], dtype=np.float32)

    overlay = Layer(name="Overlay", width=64, height=64)
    overlay.pixels[:] = 0.0
    overlay.pixels[12:52, 8:56] = np.array([0.9, 0.2, 0.15, 0.8], dtype=np.float32)
    doc.layers.add(overlay)

    mask = Layer(name="Standalone Mask", width=64, height=64, layer_type=LayerType.MASK)
    mask.pixels[:] = 1.0
    mask.pixels[:, :24, :3] = 0.0
    mask.pixels[18:46, 24:44, :3] = 0.5
    doc.layers.add(mask)

    backend = QtGpuCompositorBackend()
    assert backend.can_render_document(doc) is True

    image = QImage(doc.width, doc.height, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    ok = backend.render_document(painter, doc, QRectF(0, 0, doc.width, doc.height))
    painter.end()

    assert ok is True
    gpu_like = _image_to_array(image)
    cpu = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_allclose(gpu_like, cpu, atol=1)


def test_qt_gpu_backend_tracks_standalone_mask_execution_dependencies_in_graph(app) -> None:
    doc = Document(64, 64, "GPU Standalone Mask Graph")
    base = doc.layers[0]
    base.pixels[:] = np.array([0.1, 0.5, 0.85, 1.0], dtype=np.float32)

    overlay = Layer(name="Overlay", width=64, height=64)
    overlay.pixels[:] = 0.0
    overlay.pixels[12:52, 8:56] = np.array([0.9, 0.2, 0.15, 0.8], dtype=np.float32)
    doc.layers.add(overlay)

    mask = Layer(name="Standalone Mask", width=64, height=64, layer_type=LayerType.MASK)
    mask.pixels[:] = 1.0
    mask.pixels[:, :24, :3] = 0.0
    doc.layers.add(mask)

    top = Layer(name="Top", width=64, height=64)
    top.pixels[:] = 0.0
    top.pixels[18:34, 20:44] = np.array([0.1, 0.95, 0.2, 0.6], dtype=np.float32)
    doc.layers.add(top)

    backend = QtGpuCompositorBackend()
    graph = backend._build_top_level_graph(backend._top_level_visible_layers(doc))

    assert [
        (type(segment).__name__, getattr(segment, "cache_key", None), segment.graph_dependencies, tuple(layer.id for layer in segment.layers))
        for segment in graph
    ] == [
        ("_ChainNode", base.id, (), (base.id,)),
        ("_ChainNode", overlay.id, (0,), (overlay.id,)),
        ("_MaskNode", None, (1,), (mask.id,)),
        ("_ChainNode", top.id, (2,), (top.id,)),
    ]
    assert backend._render_schedule_indices(graph) == [0, 1, 2, 3]
    assert backend._invalidation_keys_for_document(doc, mask.id) == [mask.id]


def test_qt_gpu_backend_supports_root_adjustment_document(app) -> None:
    doc = Document(64, 64, "GPU Root Adjustment")
    base = doc.layers[0]
    base.pixels[:] = np.array([0.2, 0.35, 0.65, 1.0], dtype=np.float32)

    overlay = Layer(name="Overlay", width=64, height=64)
    overlay.pixels[:] = 0.0
    overlay.pixels[14:50, 10:54] = np.array([0.9, 0.25, 0.15, 0.7], dtype=np.float32)
    doc.layers.add(overlay)

    root_adjustment = Layer(name="Root Adjustment", width=64, height=64, layer_type=LayerType.ADJUSTMENT)
    root_adjustment.adjustment = BrightnessContrast()
    root_adjustment.adjustment_params = {"brightness": 20, "contrast": 10}
    doc.layers.add(root_adjustment)

    top = Layer(name="Top", width=64, height=64)
    top.pixels[:] = 0.0
    top.pixels[18:34, 20:44] = np.array([0.1, 0.95, 0.2, 0.6], dtype=np.float32)
    doc.layers.add(top)

    backend = QtGpuCompositorBackend()
    assert backend.can_render_document(doc) is True

    image = QImage(doc.width, doc.height, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    ok = backend.render_document(painter, doc, QRectF(0, 0, doc.width, doc.height))
    painter.end()

    assert ok is True
    gpu_like = _image_to_array(image)
    cpu = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_allclose(gpu_like, cpu, atol=2)


def test_qt_gpu_backend_supports_root_filter_document(app) -> None:
    doc = Document(64, 64, "GPU Root Filter")
    base = doc.layers[0]
    base.pixels[:] = np.array([0.75, 0.3, 0.12, 1.0], dtype=np.float32)

    root_filter = Layer(name="Root Filter", width=64, height=64, layer_type=LayerType.FILTER)
    root_filter.adjustment = GaussianBlur()
    root_filter.adjustment_params = {"radius": 2.0}
    doc.layers.add(root_filter)

    top = Layer(name="Top", width=64, height=64)
    top.pixels[:] = 0.0
    top.pixels[20:44, 20:44] = np.array([0.2, 0.8, 0.95, 0.7], dtype=np.float32)
    doc.layers.add(top)

    backend = QtGpuCompositorBackend()
    assert backend.can_render_document(doc) is True

    image = QImage(doc.width, doc.height, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    ok = backend.render_document(painter, doc, QRectF(0, 0, doc.width, doc.height))
    painter.end()

    assert ok is True
    gpu_like = _image_to_array(image)
    cpu = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_allclose(gpu_like, cpu, atol=2)


def test_qt_gpu_backend_invalidates_only_affected_root_effect_segment(app) -> None:
    doc = Document(64, 64, "GPU Root Effect Invalidation")
    base = doc.layers[0]
    base.pixels[:] = np.array([0.2, 0.35, 0.65, 1.0], dtype=np.float32)

    root_adjustment = Layer(name="Root Adjustment", width=64, height=64, layer_type=LayerType.ADJUSTMENT)
    root_adjustment.adjustment = BrightnessContrast()
    root_adjustment.adjustment_params = {"brightness": 20, "contrast": 10}
    doc.layers.add(root_adjustment)

    top = Layer(name="Top", width=64, height=64)
    top.pixels[:] = 0.0
    top.pixels[18:34, 20:44] = np.array([0.1, 0.95, 0.2, 0.6], dtype=np.float32)
    doc.layers.add(top)

    backend = QtGpuCompositorBackend()
    _render_with_backend(backend, doc)
    suffix_key = f"suffix:{root_adjustment.id}:2"

    assert root_adjustment.id in backend._layer_pixmaps
    assert suffix_key in backend._layer_pixmaps

    backend.invalidate_document_layer(doc, top.id)
    assert root_adjustment.id in backend._layer_pixmaps
    assert suffix_key not in backend._layer_pixmaps

    _render_with_backend(backend, doc)
    assert root_adjustment.id in backend._layer_pixmaps
    assert suffix_key in backend._layer_pixmaps

    backend.invalidate_document_layer(doc, base.id)
    assert root_adjustment.id not in backend._layer_pixmaps
    assert suffix_key in backend._layer_pixmaps


def test_qt_gpu_backend_reuses_upstream_prefix_cache_for_multiple_root_effects(app) -> None:
    doc = Document(64, 64, "GPU Multi Root Effects")
    base = doc.layers[0]
    base.pixels[:] = np.array([0.18, 0.32, 0.58, 1.0], dtype=np.float32)

    first_adjustment = Layer(name="First Adjustment", width=64, height=64, layer_type=LayerType.ADJUSTMENT)
    first_adjustment.adjustment = BrightnessContrast()
    first_adjustment.adjustment_params = {"brightness": 18, "contrast": 6}
    doc.layers.add(first_adjustment)

    middle = Layer(name="Middle", width=64, height=64)
    middle.pixels[:] = 0.0
    middle.pixels[10:42, 14:50] = np.array([0.92, 0.25, 0.12, 0.7], dtype=np.float32)
    doc.layers.add(middle)

    second_filter = Layer(name="Second Filter", width=64, height=64, layer_type=LayerType.FILTER)
    second_filter.adjustment = GaussianBlur()
    second_filter.adjustment_params = {"radius": 2.0}
    doc.layers.add(second_filter)

    top = Layer(name="Top", width=64, height=64)
    top.pixels[:] = 0.0
    top.pixels[20:44, 20:44] = np.array([0.14, 0.9, 0.25, 0.55], dtype=np.float32)
    doc.layers.add(top)

    backend = QtGpuCompositorBackend()
    gpu_like = _render_with_backend(backend, doc)
    cpu = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_allclose(gpu_like, cpu, atol=3)
    suffix_key = f"suffix:{second_filter.id}:4"

    assert first_adjustment.id in backend._layer_pixmaps
    assert second_filter.id in backend._layer_pixmaps
    assert suffix_key in backend._layer_pixmaps

    backend.invalidate_document_layer(doc, middle.id)
    assert first_adjustment.id in backend._layer_pixmaps
    assert second_filter.id not in backend._layer_pixmaps
    assert suffix_key in backend._layer_pixmaps

    _render_with_backend(backend, doc)
    assert first_adjustment.id in backend._layer_pixmaps
    assert second_filter.id in backend._layer_pixmaps


def test_qt_gpu_backend_reuses_upstream_detached_mask_barrier_for_later_root_effect(app) -> None:
    doc = Document(64, 64, "GPU Mixed Barriers")
    base = doc.layers[0]
    base.pixels[:] = np.array([0.22, 0.38, 0.7, 1.0], dtype=np.float32)

    detached_mask = Layer(name="Detached Mask", width=64, height=64, layer_type=LayerType.MASK)
    detached_mask.pixels[:] = 1.0
    detached_mask.pixels[:, :18, :3] = 0.0
    detached_mask.ex_parent_id = base.id
    doc.layers.add(detached_mask)

    middle = Layer(name="Middle", width=64, height=64)
    middle.pixels[:] = 0.0
    middle.pixels[12:40, 16:52] = np.array([0.9, 0.25, 0.18, 0.75], dtype=np.float32)
    doc.layers.add(middle)

    root_adjustment = Layer(name="Root Adjustment", width=64, height=64, layer_type=LayerType.ADJUSTMENT)
    root_adjustment.adjustment = BrightnessContrast()
    root_adjustment.adjustment_params = {"brightness": 12, "contrast": 8}
    doc.layers.add(root_adjustment)

    top = Layer(name="Top", width=64, height=64)
    top.pixels[:] = 0.0
    top.pixels[20:44, 22:46] = np.array([0.1, 0.92, 0.24, 0.58], dtype=np.float32)
    doc.layers.add(top)

    backend = QtGpuCompositorBackend()
    gpu_like = _render_with_backend(backend, doc)
    cpu = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_allclose(gpu_like, cpu, atol=3)
    suffix_key = f"suffix:{root_adjustment.id}:4"

    assert detached_mask.id in backend._layer_pixmaps
    assert root_adjustment.id in backend._layer_pixmaps
    assert suffix_key in backend._layer_pixmaps

    backend.invalidate_document_layer(doc, middle.id)
    assert detached_mask.id in backend._layer_pixmaps
    assert root_adjustment.id not in backend._layer_pixmaps
    assert suffix_key in backend._layer_pixmaps


def test_qt_gpu_backend_builds_explicit_top_level_graph_for_mixed_barriers(app) -> None:
    doc = Document(64, 64, "GPU Graph")
    base = doc.layers[0]
    base.pixels[:] = np.array([0.22, 0.38, 0.7, 1.0], dtype=np.float32)

    detached_mask = Layer(name="Detached Mask", width=64, height=64, layer_type=LayerType.MASK)
    detached_mask.pixels[:] = 1.0
    detached_mask.ex_parent_id = base.id
    doc.layers.add(detached_mask)

    middle = Layer(name="Middle", width=64, height=64)
    middle.pixels[:] = 0.0
    middle.pixels[12:40, 16:52] = np.array([0.9, 0.25, 0.18, 0.75], dtype=np.float32)
    doc.layers.add(middle)

    root_adjustment = Layer(name="Root Adjustment", width=64, height=64, layer_type=LayerType.ADJUSTMENT)
    root_adjustment.adjustment = BrightnessContrast()
    root_adjustment.adjustment_params = {"brightness": 12, "contrast": 8}
    doc.layers.add(root_adjustment)

    top = Layer(name="Top", width=64, height=64)
    top.pixels[:] = 0.0
    top.pixels[20:44, 22:46] = np.array([0.1, 0.92, 0.24, 0.58], dtype=np.float32)
    doc.layers.add(top)

    backend = QtGpuCompositorBackend()
    graph = backend._build_top_level_graph(backend._top_level_visible_layers(doc))

    assert [(type(segment).__name__, segment.cache_key) for segment in graph] == [
        ("_RunCacheNode", f"segment:{detached_mask.id}"),
        ("_PrefixCacheNode", detached_mask.id),
        ("_RunCacheNode", f"segment:{root_adjustment.id}"),
        ("_PrefixNode", root_adjustment.id),
        ("_SegmentNode", f"suffix:{root_adjustment.id}:4"),
    ]
    assert [type(segment).__name__ for segment in graph] == [
        "_RunCacheNode",
        "_PrefixCacheNode",
        "_RunCacheNode",
        "_PrefixNode",
        "_SegmentNode",
    ]
    assert vars(graph[0]) == {
        "start_index": 0,
        "end_index": 1,
        "graph_dependencies": (),
        "cache_key": f"segment:{detached_mask.id}",
        "layers": (base,),
    }
    assert [getattr(segment, "cache_dependencies", ()) for segment in graph] == [
        (),
        (f"segment:{detached_mask.id}",),
        (),
        (detached_mask.id, f"segment:{root_adjustment.id}"),
        (),
    ]
    assert backend._render_schedule_indices(graph) == [3, 4]
    graph_and_plan = backend._build_graph_and_render_plan(doc)
    assert graph_and_plan is not None
    _, plan = graph_and_plan
    assert [type(step).__name__ for step in plan] == [
        "_PrefixRenderStep",
        "_SegmentRenderStep",
    ]
    assert vars(plan[0]) == {"graph_index": 3}


def test_qt_gpu_backend_invalidation_follows_graph_dependencies(app) -> None:
    doc = Document(64, 64, "GPU Graph Invalidation")
    base = doc.layers[0]
    base.pixels[:] = np.array([0.22, 0.38, 0.7, 1.0], dtype=np.float32)

    detached_mask = Layer(name="Detached Mask", width=64, height=64, layer_type=LayerType.MASK)
    detached_mask.pixels[:] = 1.0
    detached_mask.ex_parent_id = base.id
    doc.layers.add(detached_mask)

    middle = Layer(name="Middle", width=64, height=64)
    middle.pixels[:] = 0.0
    middle.pixels[12:40, 16:52] = np.array([0.9, 0.25, 0.18, 0.75], dtype=np.float32)
    doc.layers.add(middle)

    root_adjustment = Layer(name="Root Adjustment", width=64, height=64, layer_type=LayerType.ADJUSTMENT)
    root_adjustment.adjustment = BrightnessContrast()
    root_adjustment.adjustment_params = {"brightness": 12, "contrast": 8}
    doc.layers.add(root_adjustment)

    backend = QtGpuCompositorBackend()

    assert backend._invalidation_keys_for_document(doc, base.id) == [
        f"segment:{detached_mask.id}",
        detached_mask.id,
        root_adjustment.id,
    ]
    assert backend._invalidation_keys_for_document(doc, middle.id) == [
        f"segment:{root_adjustment.id}",
        root_adjustment.id,
    ]
    assert backend._invalidation_keys_for_document(doc, root_adjustment.id) == [
        root_adjustment.id,
    ]


def test_qt_gpu_backend_caches_inter_barrier_segment_and_invalidates_it_independently(app) -> None:
    doc = Document(64, 64, "GPU Inter Barrier Segment")
    base = doc.layers[0]
    base.pixels[:] = np.array([0.18, 0.32, 0.58, 1.0], dtype=np.float32)

    first_adjustment = Layer(name="First Adjustment", width=64, height=64, layer_type=LayerType.ADJUSTMENT)
    first_adjustment.adjustment = BrightnessContrast()
    first_adjustment.adjustment_params = {"brightness": 18, "contrast": 6}
    doc.layers.add(first_adjustment)

    middle = Layer(name="Middle", width=64, height=64)
    middle.pixels[:] = 0.0
    middle.pixels[10:42, 14:50] = np.array([0.92, 0.25, 0.12, 0.7], dtype=np.float32)
    doc.layers.add(middle)

    second_filter = Layer(name="Second Filter", width=64, height=64, layer_type=LayerType.FILTER)
    second_filter.adjustment = GaussianBlur()
    second_filter.adjustment_params = {"radius": 2.0}
    doc.layers.add(second_filter)

    backend = QtGpuCompositorBackend()
    gpu_like = _render_with_backend(backend, doc)
    cpu = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_allclose(gpu_like, cpu, atol=3)

    second_segment_key = f"segment:{second_filter.id}"
    assert first_adjustment.id in backend._layer_pixmaps
    assert second_filter.id in backend._layer_pixmaps
    assert second_segment_key in backend._layer_pixmaps

    backend.invalidate_document_layer(doc, middle.id)
    assert first_adjustment.id in backend._layer_pixmaps
    assert second_segment_key not in backend._layer_pixmaps
    assert second_filter.id not in backend._layer_pixmaps


def test_qt_gpu_backend_supports_detached_root_mask_document(app) -> None:
    doc = Document(64, 64, "GPU Detached Mask")
    base = doc.layers[0]
    base.pixels[:] = np.array([0.25, 0.4, 0.75, 1.0], dtype=np.float32)

    overlay = Layer(name="Overlay", width=64, height=64)
    overlay.pixels[:] = 0.0
    overlay.pixels[12:52, 16:48] = np.array([0.9, 0.2, 0.15, 0.8], dtype=np.float32)
    doc.layers.add(overlay)

    mask = Layer(name="Detached Mask", width=64, height=64, layer_type=LayerType.MASK)
    mask.pixels[:] = 1.0
    mask.pixels[:, :20, :3] = 0.0
    mask.pixels[18:42, 20:44, :3] = 0.35
    mask.ex_parent_id = base.id
    doc.layers.add(mask)

    top = Layer(name="Top", width=64, height=64)
    top.pixels[:] = 0.0
    top.pixels[20:44, 18:46] = np.array([0.15, 0.95, 0.25, 0.6], dtype=np.float32)
    doc.layers.add(top)

    backend = QtGpuCompositorBackend()
    assert backend.can_render_document(doc) is True

    image = QImage(doc.width, doc.height, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    ok = backend.render_document(painter, doc, QRectF(0, 0, doc.width, doc.height))
    painter.end()

    assert ok is True
    gpu_like = _image_to_array(image)
    cpu = RenderPipeline(quality_mode="final").execute_to_uint8(doc)
    np.testing.assert_allclose(gpu_like, cpu, atol=2)


def test_qt_gpu_backend_rejects_orphan_clipping_mask_document(app) -> None:
    doc = Document(64, 64, "GPU Orphan Clip")
    doc.layers.remove(doc.layers[0].id)

    clip = Layer(name="Clip", width=64, height=64)
    clip.pixels[:] = np.array([0.7, 0.1, 0.1, 1.0], dtype=np.float32)
    clip.clipping_mask = True
    doc.layers.add(clip)

    backend = QtGpuCompositorBackend()
    assert backend.can_render_document(doc) is False
