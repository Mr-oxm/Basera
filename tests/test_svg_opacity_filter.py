"""Test SVG import of opacity and filter (feGaussianBlur) attributes."""

from photo_editor.vector.svg import import_svg, SVGGroup, SVGLeaf


def _collect_leaves(node, out: list):
    if isinstance(node, SVGLeaf):
        out.append(node)
    elif isinstance(node, SVGGroup):
        for c in node.children:
            _collect_leaves(c, out)


def test_shokunin_svg_opacity_and_filter():
    """Import shokunin_sky_with_clouds.svg and verify opacity/filter are parsed."""
    path = "svgs/shokunin_sky_with_clouds.svg"
    root = import_svg(path)
    assert isinstance(root, SVGGroup), "Expected root to be SVGGroup"
    
    leaves: list = []
    _collect_leaves(root, leaves)
    
    # SVG has paths with opacity=".28" and filter="url(#filter4481)"
    with_opacity = [l for l in leaves if getattr(l.object, "opacity", 1.0) != 1.0]
    with_filter = [l for l in leaves if getattr(l.object, "svg_filter", None)]
    
    print(f"Total leaf objects: {len(leaves)}")
    print(f"Objects with opacity < 1: {len(with_opacity)}")
    print(f"Objects with filter: {len(with_filter)}")
    
    # Expected: path4445, path4447, path4449 have opacity .28
    # path4451, path4485, path4487, path4489 have opacity .28 AND filter
    assert len(with_opacity) >= 7, f"Expected at least 7 objects with opacity, got {len(with_opacity)}"
    assert len(with_filter) >= 4, f"Expected at least 4 objects with filter, got {len(with_filter)}"
    
    # Check filter structure
    for leaf in with_filter[:1]:
        sf = leaf.object.svg_filter
        assert sf is not None
        assert sf.get("type") == "gaussian_blur"
        assert "std_deviation" in sf
        print(f"Filter: {sf}")
    
    # Check opacity value
    for leaf in with_opacity[:1]:
        op = leaf.object.opacity
        assert 0 < op < 1
        print(f"Opacity: {op}")
    
    print("PASS: opacity and filter attributes imported correctly")


if __name__ == "__main__":
    test_shokunin_svg_opacity_and_filter()
