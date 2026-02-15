"""SVG import and export for vector paths.

Export
------
Converts ``VectorObject`` instances to well-formed SVG markup.  Path
data uses the compact SVG ``d`` attribute syntax (M, L, C, Z commands).
Style properties map to SVG ``fill``, ``stroke``, ``stroke-width``, etc.

Import
------
Parses SVG ``<path>``, ``<rect>``, ``<circle>``, ``<ellipse>``,
``<polygon>``, and ``<polyline>`` elements into ``VectorObject``
instances.  Transform attributes are parsed and applied.

The parser is intentionally lightweight — it handles the common subset
of SVG used by vector editors without requiring a full XML/CSS engine.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Sequence


from .geometry import Vec2, AffineTransform
from .path import (
    VectorPath, SubPath, PathNode, HandleMode, FillRule,
)
from .scene import VectorObject, VectorLayer
from .style import (
    VectorStyle, VectorFill, VectorStroke,
    SolidPaint, GradientPaint, GradientStop, GradientType,
    StrokeCap, StrokeJoin, DashPattern,
)
from .shapes import RectangleShape, EllipseShape

__all__ = ["export_svg", "import_svg", "path_to_svg_d", "svg_d_to_path"]

_SVG_NS = "http://www.w3.org/2000/svg"


# ---------------------------------------------------------------------------
#  Hierarchical Import Types
# ---------------------------------------------------------------------------

@dataclass
class SVGNode:
    """Base class for SVG import hierarchy."""
    name: str = "Node"
    transform: AffineTransform = field(default_factory=AffineTransform.identity)

@dataclass
class SVGGroup(SVGNode):
    """Represents a container (group or layer)."""
    children: list[SVGNode] = field(default_factory=list)

@dataclass
class SVGLeaf(SVGNode):
    """Represents a single vector object."""
    object: VectorObject = field(default_factory=VectorObject)


# ---------------------------------------------------------------------------
#  SVG Path Data (d attribute) ↔ VectorPath
# ---------------------------------------------------------------------------

def path_to_svg_d(path: VectorPath) -> str:
    """Convert a VectorPath to SVG ``d`` attribute string."""
    parts: list[str] = []
    for sp in path.sub_paths:
        if not sp.nodes:
            continue
        origin = sp.nodes[0].position
        parts.append(f"M {origin.x:.4f},{origin.y:.4f}")
        for seg in sp.segments:
            from .path import SegmentType
            if seg.seg_type == SegmentType.LINE:
                parts.append(f"L {seg.end.x:.4f},{seg.end.y:.4f}")
            elif seg.seg_type == SegmentType.CUBIC:
                parts.append(
                    f"C {seg.cp1.x:.4f},{seg.cp1.y:.4f} "
                    f"{seg.cp2.x:.4f},{seg.cp2.y:.4f} "
                    f"{seg.end.x:.4f},{seg.end.y:.4f}"
                )
            elif seg.seg_type == SegmentType.CLOSE:
                parts.append("Z")
    return " ".join(parts)


def svg_d_to_path(d: str) -> VectorPath:
    """Parse an SVG ``d`` attribute string into a VectorPath."""
    tokens = _tokenise_svg_d(d)
    sub_paths: list[SubPath] = []
    nodes: list[PathNode] = []
    current = Vec2(0.0, 0.0)
    first = current
    i = 0

    def _next_float() -> float:
        nonlocal i
        if i < len(tokens):
            val = float(tokens[i])
            i += 1
            return val
        return 0.0

    while i < len(tokens):
        cmd = tokens[i]
        if cmd in ("M", "m", "L", "l", "C", "c", "Z", "z", "H", "h", "V", "v", "S", "s", "Q", "q"):
            i += 1
        else:
            # Implicit lineto
            cmd = "L"

        if cmd == "M":
            if nodes:
                sub_paths.append(SubPath(nodes, closed=False))
                nodes = []
            x, y = _next_float(), _next_float()
            current = Vec2(x, y)
            first = current
            nodes.append(PathNode(position=current, mode=HandleMode.SHARP))

        elif cmd == "m":
            if nodes:
                sub_paths.append(SubPath(nodes, closed=False))
                nodes = []
            x, y = _next_float(), _next_float()
            current = Vec2(current.x + x, current.y + y)
            first = current
            nodes.append(PathNode(position=current, mode=HandleMode.SHARP))

        elif cmd == "L":
            x, y = _next_float(), _next_float()
            current = Vec2(x, y)
            nodes.append(PathNode(position=current, mode=HandleMode.SHARP))

        elif cmd == "l":
            x, y = _next_float(), _next_float()
            current = Vec2(current.x + x, current.y + y)
            nodes.append(PathNode(position=current, mode=HandleMode.SHARP))

        elif cmd == "H":
            x = _next_float()
            current = Vec2(x, current.y)
            nodes.append(PathNode(position=current, mode=HandleMode.SHARP))

        elif cmd == "h":
            x = _next_float()
            current = Vec2(current.x + x, current.y)
            nodes.append(PathNode(position=current, mode=HandleMode.SHARP))

        elif cmd == "V":
            y = _next_float()
            current = Vec2(current.x, y)
            nodes.append(PathNode(position=current, mode=HandleMode.SHARP))

        elif cmd == "v":
            y = _next_float()
            current = Vec2(current.x, current.y + y)
            nodes.append(PathNode(position=current, mode=HandleMode.SHARP))

        elif cmd == "C":
            x1, y1 = _next_float(), _next_float()
            x2, y2 = _next_float(), _next_float()
            x, y = _next_float(), _next_float()
            # Set out-handle on previous node
            if nodes:
                nodes[-1].out_handle = Vec2(x1, y1)
            new_node = PathNode(
                position=Vec2(x, y),
                in_handle=Vec2(x2, y2),
                mode=HandleMode.SMOOTH,
            )
            nodes.append(new_node)
            current = Vec2(x, y)

        elif cmd == "c":
            x1, y1 = _next_float(), _next_float()
            x2, y2 = _next_float(), _next_float()
            x, y = _next_float(), _next_float()
            abs_cp1 = Vec2(current.x + x1, current.y + y1)
            abs_cp2 = Vec2(current.x + x2, current.y + y2)
            abs_end = Vec2(current.x + x, current.y + y)
            if nodes:
                nodes[-1].out_handle = abs_cp1
            new_node = PathNode(
                position=abs_end,
                in_handle=abs_cp2,
                mode=HandleMode.SMOOTH,
            )
            nodes.append(new_node)
            current = abs_end

        elif cmd == "S":
            x2, y2 = _next_float(), _next_float()
            x, y = _next_float(), _next_float()
            # Reflect previous cp2
            if nodes and nodes[-1].in_handle:
                ref = Vec2(
                    2 * current.x - nodes[-1].in_handle.x,
                    2 * current.y - nodes[-1].in_handle.y,
                )
            else:
                ref = current
            if nodes:
                nodes[-1].out_handle = ref
            new_node = PathNode(
                position=Vec2(x, y),
                in_handle=Vec2(x2, y2),
                mode=HandleMode.SMOOTH,
            )
            nodes.append(new_node)
            current = Vec2(x, y)

        elif cmd == "s":
            x2, y2 = _next_float(), _next_float()
            x, y = _next_float(), _next_float()
            if nodes and nodes[-1].in_handle:
                ref = Vec2(
                    2 * current.x - nodes[-1].in_handle.x,
                    2 * current.y - nodes[-1].in_handle.y,
                )
            else:
                ref = current
            if nodes:
                nodes[-1].out_handle = ref
            abs_cp2 = Vec2(current.x + x2, current.y + y2)
            abs_end = Vec2(current.x + x, current.y + y)
            new_node = PathNode(
                position=abs_end,
                in_handle=abs_cp2,
                mode=HandleMode.SMOOTH,
            )
            nodes.append(new_node)
            current = abs_end

        elif cmd == "Q":
            x1, y1 = _next_float(), _next_float()
            x, y = _next_float(), _next_float()
            # Convert quadratic to cubic
            cp = Vec2(x1, y1)
            end = Vec2(x, y)
            cp1 = Vec2(
                current.x + 2.0 / 3.0 * (cp.x - current.x),
                current.y + 2.0 / 3.0 * (cp.y - current.y),
            )
            cp2 = Vec2(
                end.x + 2.0 / 3.0 * (cp.x - end.x),
                end.y + 2.0 / 3.0 * (cp.y - end.y),
            )
            if nodes:
                nodes[-1].out_handle = cp1
            new_node = PathNode(position=end, in_handle=cp2, mode=HandleMode.SMOOTH)
            nodes.append(new_node)
            current = end

        elif cmd == "q":
            x1, y1 = _next_float(), _next_float()
            x, y = _next_float(), _next_float()
            cp = Vec2(current.x + x1, current.y + y1)
            end = Vec2(current.x + x, current.y + y)
            cp1 = Vec2(
                current.x + 2.0 / 3.0 * (cp.x - current.x),
                current.y + 2.0 / 3.0 * (cp.y - current.y),
            )
            cp2 = Vec2(
                end.x + 2.0 / 3.0 * (cp.x - end.x),
                end.y + 2.0 / 3.0 * (cp.y - end.y),
            )
            if nodes:
                nodes[-1].out_handle = cp1
            new_node = PathNode(position=end, in_handle=cp2, mode=HandleMode.SMOOTH)
            nodes.append(new_node)
            current = end

        elif cmd in ("Z", "z"):
            if nodes:
                sub_paths.append(SubPath(nodes, closed=True))
                nodes = []
            current = first

    # Remaining open sub-path
    if nodes:
        sub_paths.append(SubPath(nodes, closed=False))

    return VectorPath(sub_paths)


def _tokenise_svg_d(d: str) -> list[str]:
    """Split an SVG ``d`` string into command letters and number tokens."""
    # Insert space before command letters so they become separate tokens
    d = re.sub(r"([MmLlHhVvCcSsQqTtAaZz])", r" \1 ", d)
    # Replace commas with spaces
    d = d.replace(",", " ")
    # Handle negative numbers that aren't separated by space
    d = re.sub(r"(\d)-", r"\1 -", d)
    return d.split()


# ---------------------------------------------------------------------------
#  Full SVG export
# ---------------------------------------------------------------------------

def export_svg(
    objects: Sequence[VectorObject],
    width: float = 800,
    height: float = 600,
    viewbox: str | None = None,
) -> str:
    """Export vector objects to a complete SVG document string."""
    vb = viewbox or f"0 0 {width} {height}"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="{_SVG_NS}" width="{width}" height="{height}" viewBox="{vb}">',
    ]
    for obj in objects:
        if not obj.visible:
            continue
        lines.append(_object_to_svg(obj))
    lines.append("</svg>")
    return "\n".join(lines)


def export_svg_to_file(
    objects: Sequence[VectorObject],
    filepath: str,
    width: float = 800,
    height: float = 600,
) -> None:
    svg = export_svg(objects, width, height)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(svg)


def _object_to_svg(obj: VectorObject) -> str:
    """Convert a single VectorObject to an SVG element."""
    path = obj.transformed_path()
    d = path_to_svg_d(path)
    style_parts = _style_to_svg_attrs(obj.style)
    attrs = f'd="{d}" {style_parts}'
    return f'  <path {attrs}/>'


def _style_to_svg_attrs(style: VectorStyle) -> str:
    """Convert VectorStyle to SVG inline style attributes."""
    parts: list[str] = []

    # First visible fill
    fill_str = "none"
    fill_opacity = "1"
    for f in style.fills:
        if f.visible and f.opacity > 0:
            if isinstance(f.paint, SolidPaint):
                r, g, b, a = f.paint.color
                fill_str = f"rgb({int(r*255)},{int(g*255)},{int(b*255)})"
                fill_opacity = f"{f.opacity * a:.3f}"
            break
    parts.append(f'fill="{fill_str}"')
    if fill_opacity != "1":
        parts.append(f'fill-opacity="{fill_opacity}"')

    # First visible stroke
    stroke_str = "none"
    stroke_w = "0"
    stroke_opacity = "1"
    for s in style.strokes:
        if s.visible and s.opacity > 0 and s.width > 0:
            if isinstance(s.paint, SolidPaint):
                r, g, b, a = s.paint.color
                stroke_str = f"rgb({int(r*255)},{int(g*255)},{int(b*255)})"
                stroke_opacity = f"{s.opacity * a:.3f}"
            stroke_w = f"{s.width:.2f}"
            # Caps and joins
            cap_map = {StrokeCap.BUTT: "butt", StrokeCap.ROUND: "round", StrokeCap.SQUARE: "square"}
            join_map = {StrokeJoin.MITER: "miter", StrokeJoin.ROUND: "round", StrokeJoin.BEVEL: "bevel"}
            parts.append(f'stroke-linecap="{cap_map.get(s.cap, "round")}"')
            parts.append(f'stroke-linejoin="{join_map.get(s.join, "round")}"')
            if not s.dash.is_solid:
                dash_str = " ".join(f"{v:.2f}" for v in s.dash.dashes)
                parts.append(f'stroke-dasharray="{dash_str}"')
            break
    parts.append(f'stroke="{stroke_str}"')
    parts.append(f'stroke-width="{stroke_w}"')
    if stroke_opacity != "1":
        parts.append(f'stroke-opacity="{stroke_opacity}"')

    return " ".join(parts)


# ---------------------------------------------------------------------------
#  SVG import
# ---------------------------------------------------------------------------

def import_svg(filepath: str) -> SVGNode:
    """Import an SVG file into a hierarchical node structure.
    
    Returns a root ``SVGGroup`` containing the parsed objects and groups.
    Transforms are baked into the leaf objects' geometry transforms, but
    groups are preserved for organizational structure (Layers).
    """
    tree = ET.parse(filepath)
    root = tree.getroot()
    return _import_element_recursive(root, AffineTransform.identity())


def import_svg_string(svg_text: str) -> SVGNode:
    """Import from SVG string."""
    root = ET.fromstring(svg_text)
    return _import_element_recursive(root, AffineTransform.identity())


def _import_element_recursive(elem: ET.Element, parent_xf: AffineTransform) -> SVGNode:
    """Recursively parse an SVG element and its children."""
    tag = _strip_ns(elem.tag)
    
    # Parse element-level transform
    # Note: SVG transform attribute applies to the element and its children.
    # We bake this into the accumulated transform passed down.
    local_xf = _parse_transform(elem.get("transform", ""))
    current_xf = parent_xf.concat(local_xf)
    
    # Identify element ID/Name
    name = elem.get("id", tag)

    # 1. Container elements
    if tag in ("g", "svg", "a", "defs", "symbol"): 
        # Note: defs/symbol shouldn't render directly but for simplicity 
        # we parse them as groups (though usually they are referenced).
        # Standard SVG readers usually hide defs. 
        # For now, treat 'g' and 'svg' as groups. 'defs' we might ideally skip 
        # unless referenced, but let's just parse 'g' and 'svg' as visible groups.
        if tag in ("defs", "symbol"):
            # Skip non-rendering definitions for now (simple parser)
            return SVGGroup(name=name + " (Defs)")
            
        group = SVGGroup(name=name)
        # Recurse
        for child in elem:
            # We don't assume child inherits formatting from parent in this simple parser
            # (CSS inheritance is complex), but we DO inherit transform via current_xf.
            node = _import_element_recursive(child, current_xf)
            # Only add nodes that contain content
            if isinstance(node, SVGGroup) and not node.children:
                continue
            if isinstance(node, SVGLeaf) and node.object.effective_path().is_empty and not node.object.shape:
                continue
            group.children.append(node)
        return group

    # 2. Graphic elements
    obj: VectorObject | None = None
    if tag == "path":
        obj = _parse_path_element(elem)
    elif tag == "rect":
        obj = _parse_rect_element(elem)
    elif tag == "circle":
        obj = _parse_circle_element(elem)
    elif tag == "ellipse":
        obj = _parse_ellipse_element(elem)
    elif tag == "polygon":
        obj = _parse_polygon_element(elem)
    elif tag == "polyline":
        obj = _parse_polyline_element(elem)
        
    if obj:
        # The object parser grabbed the local transform already? 
        # Let's check _parse_path_element etc below.
        # They do: xf = _parse_transform(elem.get("transform", ""))
        # We need to Combine parent_xf with the object's local transform.
        # The _parse_* functions return an object with 'transform' set to local only.
        # So we overwrite/combine it here.
        
        # Actually, let's check _parse_path_element implementation:
        # returns VectorObject(..., transform=xf) 
        # So obj.transform is currently just the element's local transform.
        # We need to apply parent_xf to it.
        
        obj.transform = parent_xf.concat(obj.transform)
        return SVGLeaf(name=obj.name, object=obj)

    # Fallback for unknown/empty
    return SVGGroup(name=f"Empty ({tag})")


# ---------------------------------------------------------------------------
#  Element parsers
# ---------------------------------------------------------------------------

def _parse_path_element(elem: ET.Element) -> VectorObject | None:
    d = elem.get("d", "")
    if not d:
        return None
    path = svg_d_to_path(d)
    style = _parse_style_attrs(elem)
    xf = _parse_transform(elem.get("transform", ""))
    return VectorObject(
        name=elem.get("id", "Path"),
        path=path,
        style=style,
        transform=xf,
    )


def _parse_rect_element(elem: ET.Element) -> VectorObject | None:
    x = float(elem.get("x", "0"))
    y = float(elem.get("y", "0"))
    w = float(elem.get("width", "0"))
    h = float(elem.get("height", "0"))
    rx = float(elem.get("rx", "0"))
    ry = float(elem.get("ry", str(rx)))
    r = max(rx, ry)
    shape = RectangleShape(width=w, height=h, corner_radii=(r, r, r, r))
    style = _parse_style_attrs(elem)
    xf = AffineTransform.translation(x + w / 2, y + h / 2)
    parent_xf = _parse_transform(elem.get("transform", ""))
    xf = parent_xf.concat(xf)
    return VectorObject(
        name=elem.get("id", "Rectangle"),
        shape=shape,
        style=style,
        transform=xf,
    )


def _parse_circle_element(elem: ET.Element) -> VectorObject | None:
    cx = float(elem.get("cx", "0"))
    cy = float(elem.get("cy", "0"))
    r = float(elem.get("r", "0"))
    shape = EllipseShape(rx=r, ry=r)
    style = _parse_style_attrs(elem)
    xf = AffineTransform.translation(cx, cy)
    parent_xf = _parse_transform(elem.get("transform", ""))
    xf = parent_xf.concat(xf)
    return VectorObject(
        name=elem.get("id", "Circle"),
        shape=shape,
        style=style,
        transform=xf,
    )


def _parse_ellipse_element(elem: ET.Element) -> VectorObject | None:
    cx = float(elem.get("cx", "0"))
    cy = float(elem.get("cy", "0"))
    rx = float(elem.get("rx", "0"))
    ry = float(elem.get("ry", "0"))
    shape = EllipseShape(rx=rx, ry=ry)
    style = _parse_style_attrs(elem)
    xf = AffineTransform.translation(cx, cy)
    parent_xf = _parse_transform(elem.get("transform", ""))
    xf = parent_xf.concat(xf)
    return VectorObject(
        name=elem.get("id", "Ellipse"),
        shape=shape,
        style=style,
        transform=xf,
    )


def _parse_polygon_element(elem: ET.Element) -> VectorObject | None:
    pts_str = elem.get("points", "")
    points = _parse_points(pts_str)
    if len(points) < 3:
        return None
    nodes = [PathNode(position=p, mode=HandleMode.SHARP) for p in points]
    sp = SubPath(nodes, closed=True)
    path = VectorPath([sp])
    style = _parse_style_attrs(elem)
    xf = _parse_transform(elem.get("transform", ""))
    return VectorObject(name=elem.get("id", "Polygon"), path=path, style=style, transform=xf)


def _parse_polyline_element(elem: ET.Element) -> VectorObject | None:
    pts_str = elem.get("points", "")
    points = _parse_points(pts_str)
    if len(points) < 2:
        return None
    nodes = [PathNode(position=p, mode=HandleMode.SHARP) for p in points]
    sp = SubPath(nodes, closed=False)
    path = VectorPath([sp])
    style = _parse_style_attrs(elem)
    xf = _parse_transform(elem.get("transform", ""))
    return VectorObject(name=elem.get("id", "Polyline"), path=path, style=style, transform=xf)


# ---------------------------------------------------------------------------
#  Style parsing
# ---------------------------------------------------------------------------

def _parse_style_attrs(elem: ET.Element) -> VectorStyle:
    """Parse fill / stroke attributes from an SVG element."""
    # Check for inline style attribute
    inline = elem.get("style", "")
    attrs: dict[str, str] = {}
    if inline:
        for part in inline.split(";"):
            kv = part.strip().split(":", 1)
            if len(kv) == 2:
                attrs[kv[0].strip()] = kv[1].strip()

    # Direct attributes (lower priority than inline)
    for attr in ("fill", "stroke", "stroke-width", "fill-opacity", "stroke-opacity",
                 "stroke-linecap", "stroke-linejoin", "stroke-dasharray"):
        if attr not in attrs:
            val = elem.get(attr)
            if val is not None:
                attrs[attr] = val

    fills: list[VectorFill] = []
    strokes: list[VectorStroke] = []

    # Fill
    fill_str = attrs.get("fill", "black")
    fill_opacity = float(attrs.get("fill-opacity", "1"))
    if fill_str and fill_str != "none":
        color = _parse_svg_color(fill_str)
        fills.append(VectorFill(SolidPaint(color), opacity=fill_opacity))

    # Stroke
    stroke_str = attrs.get("stroke", "none")
    stroke_opacity = float(attrs.get("stroke-opacity", "1"))
    stroke_w = float(attrs.get("stroke-width", "1"))
    if stroke_str and stroke_str != "none":
        color = _parse_svg_color(stroke_str)
        cap_map = {"butt": StrokeCap.BUTT, "round": StrokeCap.ROUND, "square": StrokeCap.SQUARE}
        join_map = {"miter": StrokeJoin.MITER, "round": StrokeJoin.ROUND, "bevel": StrokeJoin.BEVEL}
        cap = cap_map.get(attrs.get("stroke-linecap", "round"), StrokeCap.ROUND)
        join = join_map.get(attrs.get("stroke-linejoin", "round"), StrokeJoin.ROUND)
        dash = DashPattern()
        dash_str = attrs.get("stroke-dasharray", "")
        if dash_str and dash_str != "none":
            dash.dashes = [float(v) for v in dash_str.replace(",", " ").split()]
        strokes.append(VectorStroke(
            SolidPaint(color), width=stroke_w, opacity=stroke_opacity,
            cap=cap, join=join, dash=dash,
        ))

    return VectorStyle(
        fills=fills or [VectorFill(SolidPaint((0.0, 0.0, 0.0, 1.0)))],
        strokes=strokes,
    )


def _parse_svg_color(s: str) -> tuple[float, float, float, float]:
    """Parse SVG colour strings: named, #hex, rgb()."""
    s = s.strip().lower()
    named = {
        "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0),
        "green": (0, 128, 0), "blue": (0, 0, 255), "yellow": (255, 255, 0),
        "cyan": (0, 255, 255), "magenta": (255, 0, 255), "gray": (128, 128, 128),
        "grey": (128, 128, 128), "orange": (255, 165, 0), "purple": (128, 0, 128),
        "none": (0, 0, 0),
    }
    if s in named:
        r, g, b = named[s]
        return (r / 255.0, g / 255.0, b / 255.0, 1.0)
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            h = h[0] * 2 + h[1] * 2 + h[2] * 2
        if len(h) == 6:
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            return (r / 255.0, g / 255.0, b / 255.0, 1.0)
    m = re.match(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", s)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return (r / 255.0, g / 255.0, b / 255.0, 1.0)
    return (0.0, 0.0, 0.0, 1.0)


def _parse_transform(s: str) -> AffineTransform:
    """Parse SVG transform string (basic subset)."""
    if not s:
        return AffineTransform.identity()
    xf = AffineTransform.identity()
    for m in re.finditer(r"(\w+)\(([^)]*)\)", s):
        name = m.group(1)
        vals = [float(v) for v in m.group(2).replace(",", " ").split()]
        if name == "translate" and len(vals) >= 1:
            dy = vals[1] if len(vals) > 1 else 0.0
            xf = xf.concat(AffineTransform.translation(vals[0], dy))
        elif name == "scale" and len(vals) >= 1:
            sy = vals[1] if len(vals) > 1 else vals[0]
            xf = xf.concat(AffineTransform.scaling(vals[0], sy))
        elif name == "rotate" and len(vals) >= 1:
            angle = math.radians(vals[0])
            if len(vals) == 3:
                xf = xf.concat(AffineTransform.rotation_around(angle, Vec2(vals[1], vals[2])))
            else:
                xf = xf.concat(AffineTransform.rotation(angle))
        elif name == "matrix" and len(vals) >= 6:
            xf = xf.concat(AffineTransform(vals[0], vals[2], vals[1], vals[3], vals[4], vals[5]))
    return xf


def _parse_points(s: str) -> list[Vec2]:
    """Parse SVG points attribute (space/comma-separated x,y pairs)."""
    nums = [float(v) for v in s.replace(",", " ").split() if v]
    points: list[Vec2] = []
    return points


def _strip_ns(tag: str) -> str:
    """Remove XML namespace from a tag."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag



