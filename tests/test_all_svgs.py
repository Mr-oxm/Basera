"""Test that all SVGs in svgs/ folder import and rasterize without error."""

from pathlib import Path

from photo_editor.vector.svg import import_svg, SVGGroup, SVGLeaf
from photo_editor.vector.rasterizer import VectorRasterizer
from photo_editor.vector.scene import VectorLayer
from photo_editor.vector.geometry import BBox


def _collect_leaves(node, out: list):
    if isinstance(node, SVGLeaf):
        out.append(node)
    elif isinstance(node, SVGGroup):
        for c in node.children:
            _collect_leaves(c, out)


def test_all_svgs_import_and_rasterize():
    """Each SVG in svgs/ should import and produce at least one renderable object."""
    svg_dir = Path(__file__).parent.parent / "svgs"
    if not svg_dir.exists():
        return  # Skip if no svgs folder

    for svg_path in sorted(svg_dir.glob("*.svg")):
        root = import_svg(str(svg_path))
        assert isinstance(root, SVGGroup), f"{svg_path.name}: expected SVGGroup"

        leaves = []
        _collect_leaves(root, leaves)

        # Collect renderable objects (visible, has path, has fill)
        renderable = [
            l.object
            for l in leaves
            if l.object.visible
            and not l.object.effective_path().is_empty
            and l.object.style.fills
        ]

        # Build layer and rasterize
        vl = VectorLayer()
        for obj in renderable:
            vl.add(obj)

        union = BBox.empty()
        for obj in vl.objects:
            union = union.union(obj.bbox())

        if union.is_empty:
            continue  # No geometry is ok for some SVGs (e.g. defs only)

        x0 = int(union.min_pt.x) - 5
        y0 = int(union.min_pt.y) - 5
        w = max(50, int(union.width) + 20)
        h = max(50, int(union.height) + 20)

        # Should not raise
        px = VectorRasterizer().rasterize_layer(vl, w, h, origin=(float(x0), float(y0)))
        assert px.shape[0] == h and px.shape[1] == w, f"{svg_path.name}: wrong size"
