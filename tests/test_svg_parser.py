
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from photo_editor.vector.svg import import_svg_string, SVGGroup, SVGLeaf
    from photo_editor.vector.geometry import AffineTransform
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)

xml = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <g id="group1" transform="translate(10, 10)">
    <rect id="rect1" x="0" y="0" width="20" height="20" fill="red"/>
    <g id="subgroup">
       <circle id="circle1" cx="30" cy="30" r="10" fill="blue"/>
    </g>
  </g>
</svg>"""

try:
    node = import_svg_string(xml)
    print("Root type:", type(node).__name__)
    if isinstance(node, SVGGroup):
        print("Children count:", len(node.children))
        for child in node.children:
            print(f"- Child: {child.name} ({type(child).__name__})")
            if isinstance(child, SVGGroup):
                 for sub in child.children:
                     print(f"  - Sub: {sub.name} ({type(sub).__name__})")
            if isinstance(child, SVGLeaf):
                 print(f"  - Transform: {child.object.transform}")

    print("SVG Tree parsed successfully.")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
