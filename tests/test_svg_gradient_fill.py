"""Tests for SVG gradient and fill import/rendering."""

from photo_editor.vector.svg import import_svg, SVGGroup, SVGLeaf
from photo_editor.vector.rasterizer import VectorRasterizer
from photo_editor.vector.scene import VectorLayer
from photo_editor.vector.style import GradientPaint, SolidPaint
import numpy as np


def _collect_leaves(node, out: list):
    if isinstance(node, SVGLeaf):
        out.append(node)
    elif isinstance(node, SVGGroup):
        for c in node.children:
            _collect_leaves(c, out)


def test_1298515443_solid_fills():
    """1298515443.svg: paths with solid fill (style=fill:#hex) should parse."""
    root = import_svg("svgs/1298515443.svg")
    leaves = []
    _collect_leaves(root, leaves)
    solid = [l for l in leaves if l.object.style.fills and isinstance(l.object.style.fills[0].paint, SolidPaint)]
    assert len(solid) >= 10, f"Expected >=10 solid fills, got {len(solid)}"


def test_1298515443_radial_gradient():
    """1298515443.svg: path5780 has radial gradient with gradientTransform."""
    root = import_svg("svgs/1298515443.svg")
    leaves = []
    _collect_leaves(root, leaves)
    grad = [l for l in leaves if l.object.style.fills and isinstance(l.object.style.fills[0].paint, GradientPaint)]
    assert len(grad) >= 1, "Expected at least 1 gradient fill"
    g = grad[0].object.style.fills[0].paint
    assert g.gradient_type.name == "RADIAL"
    assert len(g.stops) == 2


def test_1298515443_gradient_rasterizes():
    """Gradient path should rasterize with visible color."""
    root = import_svg("svgs/1298515443.svg")
    leaves = []
    _collect_leaves(root, leaves)
    grad_leaf = next(
        (l for l in leaves if l.object.style.fills and isinstance(l.object.style.fills[0].paint, GradientPaint)),
        None,
    )
    assert grad_leaf is not None
    obj = grad_leaf.object
    bb = obj.bbox()
    w = max(100, int(bb.width) + 20)
    h = max(100, int(bb.height) + 20)
    vl = VectorLayer()
    vl.add(obj)
    px = VectorRasterizer().rasterize_layer(vl, w, h, origin=(bb.min_pt.x - 10, bb.min_pt.y - 10))
    assert np.any(px[..., :3] > 0.01), "Gradient should produce visible color"
    assert np.max(px[..., 3]) > 0.5, "Gradient should have substantial opacity"


def test_shokunin_linear_gradient():
    """shokunin_sky_with_clouds.svg: rect has linear gradient."""
    root = import_svg("svgs/shokunin_sky_with_clouds.svg")
    leaves = []
    _collect_leaves(root, leaves)
    rect = next((l for l in leaves if l.name == "rect4418"), None)
    assert rect is not None
    fill = rect.object.style.fills[0]
    assert isinstance(fill.paint, GradientPaint)
    assert fill.paint.gradient_type.name == "LINEAR"


def test_shokunin_rect_rasterizes():
    """Rect with linear gradient should rasterize."""
    root = import_svg("svgs/shokunin_sky_with_clouds.svg")
    leaves = []
    _collect_leaves(root, leaves)
    rect = next((l for l in leaves if l.name == "rect4418"), None)
    assert rect is not None
    vl = VectorLayer()
    vl.add(rect.object)
    px = VectorRasterizer().rasterize_layer(vl, 800, 1100, origin=(0, 0))
    assert np.any(px[..., :3] > 0.01), "Linear gradient rect should produce color"


if __name__ == "__main__":
    test_1298515443_solid_fills()
    print("PASS: solid fills")
    test_1298515443_radial_gradient()
    print("PASS: radial gradient")
    test_1298515443_gradient_rasterizes()
    print("PASS: gradient rasterizes")
    test_shokunin_linear_gradient()
    print("PASS: linear gradient")
    test_shokunin_rect_rasterizes()
    print("PASS: all gradient tests")
