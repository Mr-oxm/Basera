
from photo_editor.vector.svg import svg_d_to_path, import_svg_string, SVGGroup, SVGLeaf
from photo_editor.vector.path import SegmentType, SubPath, PathNode, VectorPath, HandleMode, FillRule
from photo_editor.vector.geometry import Vec2, AffineTransform
from photo_editor.vector.style import GradientPaint, GradientStop, GradientType

def test_t_command():
    print("\n--- Testing T Command Parse ---")
    # Path with T command: M 10,10 Q 50,20 90,10 T 170,10
    # Q(50,20) -> end(90,10). Reflected CP for T should be end + (end - cp) = (90,10) + (40,-10) = (130, 0)
    # T ends at (170,10).
    d = "M 10,10 Q 50,20 90,10 T 170,10"
    path = svg_d_to_path(d)
    
    # Check structure
    segs = path.sub_paths[0].segments
    print(f"Segment count: {len(segs)}")
        
    if len(segs) > 1 and segs[1].seg_type == SegmentType.CUBIC:
        print("PASS: Second segment is CUBIC (smooth quad)")
    else:
        print("FAIL: Second segment not CUBIC")

def test_style_inheritance():
    print("\n--- Testing Style Inheritance ---")
    svg_content = """
    <svg>
      <g fill="red" stroke="blue">
        <rect id="rect1" x="10" y="10" width="100" height="100" />
        <circle id="circle1" cx="50" cy="50" r="40" fill="green" />
      </g>
    </svg>
    """
    
    node = import_svg_string(svg_content)
    g_node = node.children[0]
    rect_leaf = g_node.children[0]
    circle_leaf = g_node.children[1]
    
    rect_style = rect_leaf.object.style
    circle_style = circle_leaf.object.style
    
    rect_stroke = rect_style.strokes[0].paint.color if rect_style.strokes else None
    
    print(f"Rect Stroke: {rect_stroke} (Expected: (0.0, 0.0, 1.0, 1.0))")


def test_gradient_parsing():
    print("\n--- Testing Gradient Parsing ---")
    svg_content = """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
      <defs>
        <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" style="stop-color:rgb(255,255,0);stop-opacity:1" />
          <stop offset="100%" style="stop-color:rgb(255,0,0);stop-opacity:1" />
        </linearGradient>
      </defs>
      <rect id="rect_grad" x="10" y="10" width="80" height="80" fill="url(#grad1)" />
    </svg>
    """
    
    node = import_svg_string(svg_content)
    
    rect_node = None
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, SVGLeaf):
             if n.name == "rect_grad":
                 rect_node = n
                 break
        elif isinstance(n, SVGGroup):
             stack.extend(n.children)
    
    if not rect_node:
        print("FAIL: Could not find rect_grad node")
        return

    style = rect_node.object.style
    if not style.fills:
        print("FAIL: No fill found")
        return
        
    fill = style.fills[0]
    
    if isinstance(fill.paint, GradientPaint):
        print("PASS: Fill is GradientPaint")
        print(f"Type: {fill.paint.gradient_type}")
        print(f"Stops: {len(fill.paint.stops)}")
        if len(fill.paint.stops) == 2:
             s1 = fill.paint.stops[0]
             s2 = fill.paint.stops[1]
             print(f"Stop 1: {s1.offset}, {s1.color}")
             print(f"Stop 2: {s2.offset}, {s2.color}")
    else:
        print(f"FAIL: Fill is {type(fill.paint)}")


def test_arc_command():
    print("\n--- Testing Arc (A) Command Parse ---")
    d = "M 10,10 A 30,30 0 0 1 70,70"
    path = svg_d_to_path(d)
    
    segs = path.sub_paths[0].segments
    print(f"Segment count: {len(segs)}")
    
    all_cubic = True
    for s in segs:
        if s.seg_type != SegmentType.CUBIC:
            all_cubic = False
            break
            
    if all_cubic and len(segs) >= 1:
        print("PASS: Arc approximated by cubic segments")
    else:
        print(f"FAIL: Segments types: {[s.seg_type for s in segs]}")


if __name__ == "__main__":
    test_t_command()
    test_style_inheritance()
    test_gradient_parsing()
    test_arc_command()
