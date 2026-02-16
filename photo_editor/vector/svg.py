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
import copy
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
    StrokeCap, StrokeJoin, DashPattern, FillPaint,
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
    
    # Track previous control points separately for cubic (S) and quadratic (T)
    prev_cubic_cp = current
    prev_quad_cp = current
    last_cmd = ""
    
    i = 0

    def _next_float() -> float:
        nonlocal i
        if i < len(tokens):
            try:
                val = float(tokens[i])
                i += 1
                return val
            except ValueError:
                pass
        return 0.0

    def _reflect(p: Vec2, center: Vec2) -> Vec2:
        return Vec2(2 * center.x - p.x, 2 * center.y - p.y)

    while i < len(tokens):
        cmd = tokens[i]
        # Check if it's a command letter
        if cmd in "MmLlCcZzHhVvSsQqTtAa":
            i += 1
        else:
            # Implicit lineto (or moveto subsequent points)
            # If the last command was M/m, implicit next is L/l. 
            # Otherwise assume repetitive numbers for previous command?
            # Standard SVG parser logic: if tokens remain, reuse last_cmd.
            # But M/m is special -> L/l.
            if last_cmd in ("M", "m") and cmd not in "MmLlCcZzHhVvSsQqTtAa":
                cmd = "L" if last_cmd == "M" else "l"
            elif last_cmd:
                cmd = last_cmd
            else:
                cmd = "L" # Fallback

        # Reset CPs if the command is NOT a smooth curve command that uses them.
        # But we must be careful: C sets cubic CP, Q sets quad CP.
        # S uses cubic CP, T uses quad CP.
        # L/M/Z etc reset both.
        
        is_smooth_cubic = (cmd in "Ss")
        is_smooth_quad = (cmd in "Tt")
        is_cubic = (cmd in "CcSs")
        is_quad = (cmd in "QqTt")

        # Position helpers
        start_pos = current

        if cmd == "M":
            x, y = _next_float(), _next_float()
            if nodes:
                sub_paths.append(SubPath(nodes, closed=False))
                nodes = []
            current = Vec2(x, y)
            first = current
            nodes.append(PathNode(position=current, mode=HandleMode.SHARP))
            prev_cubic_cp = current
            prev_quad_cp = current
            last_cmd = "M"

        elif cmd == "m":
            x, y = _next_float(), _next_float()
            if nodes:
                sub_paths.append(SubPath(nodes, closed=False))
                nodes = []
            current = Vec2(current.x + x, current.y + y)
            first = current
            nodes.append(PathNode(position=current, mode=HandleMode.SHARP))
            prev_cubic_cp = current
            prev_quad_cp = current
            last_cmd = "m"

        elif cmd == "L":
            x, y = _next_float(), _next_float()
            current = Vec2(x, y)
            nodes.append(PathNode(position=current, mode=HandleMode.SHARP))
            prev_cubic_cp = current
            prev_quad_cp = current
            last_cmd = "L"

        elif cmd == "l":
            x, y = _next_float(), _next_float()
            current = Vec2(current.x + x, current.y + y)
            nodes.append(PathNode(position=current, mode=HandleMode.SHARP))
            prev_cubic_cp = current
            prev_quad_cp = current
            last_cmd = "l"

        elif cmd == "H":
            x = _next_float()
            current = Vec2(x, current.y)
            nodes.append(PathNode(position=current, mode=HandleMode.SHARP))
            prev_cubic_cp = current
            prev_quad_cp = current
            last_cmd = "H"

        elif cmd == "h":
            x = _next_float()
            current = Vec2(current.x + x, current.y)
            nodes.append(PathNode(position=current, mode=HandleMode.SHARP))
            prev_cubic_cp = current
            prev_quad_cp = current
            last_cmd = "h"

        elif cmd == "V":
            y = _next_float()
            current = Vec2(current.x, y)
            nodes.append(PathNode(position=current, mode=HandleMode.SHARP))
            prev_cubic_cp = current
            prev_quad_cp = current
            last_cmd = "V"

        elif cmd == "v":
            y = _next_float()
            current = Vec2(current.x, current.y + y)
            nodes.append(PathNode(position=current, mode=HandleMode.SHARP))
            prev_cubic_cp = current
            prev_quad_cp = current
            last_cmd = "v"

        elif cmd == "C":
            x1, y1 = _next_float(), _next_float()
            x2, y2 = _next_float(), _next_float()
            x, y = _next_float(), _next_float()
            
            cp1 = Vec2(x1, y1)
            cp2 = Vec2(x2, y2)
            end = Vec2(x, y)
            
            if nodes:
                nodes[-1].out_handle = cp1
            
            nodes.append(PathNode(position=end, in_handle=cp2, mode=HandleMode.SMOOTH))
            current = end
            prev_cubic_cp = cp2
            prev_quad_cp = end
            last_cmd = "C"

        elif cmd == "c":
            x1, y1 = _next_float(), _next_float()
            x2, y2 = _next_float(), _next_float()
            x, y = _next_float(), _next_float()
            
            cp1 = Vec2(current.x + x1, current.y + y1)
            cp2 = Vec2(current.x + x2, current.y + y2)
            end = Vec2(current.x + x, current.y + y)
            
            if nodes:
                nodes[-1].out_handle = cp1
            
            nodes.append(PathNode(position=end, in_handle=cp2, mode=HandleMode.SMOOTH))
            current = end
            prev_cubic_cp = cp2
            prev_quad_cp = end
            last_cmd = "c"

        elif cmd == "S":
            x2, y2 = _next_float(), _next_float()
            x, y = _next_float(), _next_float()
            
            # Reflect ONLY if previous was cubic-compatible
            if last_cmd in ("C", "c", "S", "s"):
                cp1 = _reflect(prev_cubic_cp, start_pos)
            else:
                cp1 = start_pos
            
            cp2 = Vec2(x2, y2)
            end = Vec2(x, y)
            
            if nodes:
                nodes[-1].out_handle = cp1
            
            nodes.append(PathNode(position=end, in_handle=cp2, mode=HandleMode.SMOOTH))
            current = end
            prev_cubic_cp = cp2
            prev_quad_cp = end
            last_cmd = "S"

        elif cmd == "s":
            x2, y2 = _next_float(), _next_float()
            x, y = _next_float(), _next_float()
            
            if last_cmd in ("C", "c", "S", "s"):
                cp1 = _reflect(prev_cubic_cp, start_pos)
            else:
                cp1 = start_pos
            
            cp2 = Vec2(current.x + x2, current.y + y2)
            end = Vec2(current.x + x, current.y + y)
            
            if nodes:
                nodes[-1].out_handle = cp1
            
            nodes.append(PathNode(position=end, in_handle=cp2, mode=HandleMode.SMOOTH))
            current = end
            prev_cubic_cp = cp2
            prev_quad_cp = end
            last_cmd = "s"

        elif cmd == "Q":
            x1, y1 = _next_float(), _next_float()
            x, y = _next_float(), _next_float()
            
            qp = Vec2(x1, y1)
            end = Vec2(x, y)
            
            # Convert Q to C
            cp1 = start_pos + (2.0 / 3.0) * (qp - start_pos)
            cp2 = end + (2.0 / 3.0) * (qp - end)
            
            if nodes:
                nodes[-1].out_handle = cp1
            
            nodes.append(PathNode(position=end, in_handle=cp2, mode=HandleMode.SMOOTH))
            current = end
            prev_cubic_cp = end # Q destroys cubic history? Spec says S after Q assumes sharp.
            prev_quad_cp = qp
            last_cmd = "Q"

        elif cmd == "q":
            x1, y1 = _next_float(), _next_float()
            x, y = _next_float(), _next_float()
            
            qp = Vec2(current.x + x1, current.y + y1)
            end = Vec2(current.x + x, current.y + y)
            
            cp1 = start_pos + (2.0 / 3.0) * (qp - start_pos)
            cp2 = end + (2.0 / 3.0) * (qp - end)
            
            if nodes:
                nodes[-1].out_handle = cp1
            
            nodes.append(PathNode(position=end, in_handle=cp2, mode=HandleMode.SMOOTH))
            current = end
            prev_cubic_cp = end
            prev_quad_cp = qp
            last_cmd = "q"

        elif cmd == "T":
            x, y = _next_float(), _next_float()
            end = Vec2(x, y)
            
            if last_cmd in ("Q", "q", "T", "t"):
                qp = _reflect(prev_quad_cp, start_pos)
            else:
                qp = start_pos
            
            cp1 = start_pos + (2.0 / 3.0) * (qp - start_pos)
            cp2 = end + (2.0 / 3.0) * (qp - end)
            
            if nodes:
                nodes[-1].out_handle = cp1
            
            nodes.append(PathNode(position=end, in_handle=cp2, mode=HandleMode.SMOOTH))
            current = end
            prev_cubic_cp = end
            prev_quad_cp = qp
            last_cmd = "T"

        elif cmd == "t":
            x, y = _next_float(), _next_float()
            end = Vec2(current.x + x, current.y + y)
            
            if last_cmd in ("Q", "q", "T", "t"):
                qp = _reflect(prev_quad_cp, start_pos)
            else:
                qp = start_pos
            
            cp1 = start_pos + (2.0 / 3.0) * (qp - start_pos)
            cp2 = end + (2.0 / 3.0) * (qp - end)
            
            if nodes:
                nodes[-1].out_handle = cp1
            
            nodes.append(PathNode(position=end, in_handle=cp2, mode=HandleMode.SMOOTH))
            current = end
            prev_cubic_cp = end
            prev_quad_cp = qp
            last_cmd = "t"

        elif cmd == "A":
            rx, ry = _next_float(), _next_float()
            rot = _next_float()
            large_arc = _next_float() > 0.5
            sweep = _next_float() > 0.5
            x, y = _next_float(), _next_float()
            end = Vec2(x, y)
            
            _append_arc(nodes, current, rx, ry, rot, large_arc, sweep, end)
            current = end
            prev_cubic_cp = end
            prev_quad_cp = end
            last_cmd = "A"

        elif cmd == "a":
            rx, ry = _next_float(), _next_float()
            rot = _next_float()
            large_arc = _next_float() > 0.5
            sweep = _next_float() > 0.5
            x, y = _next_float(), _next_float()
            end = Vec2(current.x + x, current.y + y)
            
            _append_arc(nodes, current, rx, ry, rot, large_arc, sweep, end)
            current = end
            prev_cubic_cp = end
            prev_quad_cp = end
            last_cmd = "a"

        elif cmd in ("Z", "z"):
            if nodes:
                sub_paths.append(SubPath(nodes, closed=True))
                nodes = []
            current = first
            prev_cubic_cp = current
            prev_quad_cp = current
            last_cmd = "Z"

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
    # Handle negative numbers that aren't separated by space (e.g. 0-1)
    # Look for digit followed effectively by minus
    d = re.sub(r"(\d)-", r"\1 -", d)
    return d.split()


def _append_arc(
    nodes: list[PathNode], 
    start: Vec2, 
    rx: float, ry: float, 
    rot_deg: float, 
    large: bool, sweep: bool, 
    end: Vec2
) -> None:
    """Approximate SVG arc with cubic Bezier segments and append to nodes."""
    if rx == 0 or ry == 0:
        # Treat as line
        nodes.append(PathNode(position=end, mode=HandleMode.SHARP))
        return

    rx, ry = abs(rx), abs(ry)
    phi = math.radians(rot_deg)
    
    # Standard Step 1: Compute (x1', y1')
    dx = (start.x - end.x) / 2.0
    dy = (start.y - end.y) / 2.0
    x1p = math.cos(phi) * dx + math.sin(phi) * dy
    y1p = -math.sin(phi) * dx + math.cos(phi) * dy
    
    # Check scaling
    lambda_v = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lambda_v > 1.0:
        scale = math.sqrt(lambda_v)
        rx *= scale
        ry *= scale
    
    # Step 2: Compute (cx', cy')
    sign = -1.0 if (large == sweep) else 1.0
    sq_num = (rx*rx*ry*ry) - (rx*rx*y1p*y1p) - (ry*ry*x1p*x1p)
    sq_den = (rx*rx*y1p*y1p) + (ry*ry*x1p*x1p)
    if sq_den == 0:
        factor = 0.0
    else:
        factor = sign * math.sqrt(max(0.0, sq_num / sq_den))
    
    cxp = factor * (rx * y1p / ry)
    cyp = factor * (-ry * x1p / rx)
    
    # Step 3: Compute (cx, cy) from (cx', cy')
    cx = math.cos(phi) * cxp - math.sin(phi) * cyp + (start.x + end.x) / 2.0
    cy = math.sin(phi) * cxp + math.cos(phi) * cyp + (start.y + end.y) / 2.0
    
    # Step 4: Compute angles
    def angle(u: Vec2, v: Vec2) -> float:
        # Angle between two vectors
        sign = 1.0 if (u.x * v.y - u.y * v.x) >= 0 else -1.0
        dot = u.x * v.x + u.y * v.y
        ln = u.length() * v.length()
        if ln == 0: return 0.0
        val = dot / ln
        return sign * math.acos(max(-1.0, min(1.0, val)))

    v1 = Vec2((x1p - cxp) / rx, (y1p - cyp) / ry)
    v2 = Vec2((-x1p - cxp) / rx, (-y1p - cyp) / ry)
    
    theta1 = angle(Vec2(1, 0), v1)
    delta_theta = angle(v1, v2) % (2 * math.pi)
    
    if not sweep and delta_theta > 0:
        delta_theta -= 2 * math.pi
    elif sweep and delta_theta < 0:
        delta_theta += 2 * math.pi
        
    # Split into segments
    # Useful to keep segments small (<= 90 degrees) for cubic approx accuracy
    n_segs = int(math.ceil(abs(delta_theta) / (math.pi / 2.0)))
    dt = delta_theta / n_segs
    t = theta1
    
    for _ in range(n_segs):
        t_end = t + dt
        
        # Arc approx: kappa = 4/3 * tan(delta/4)
        kappa = (4.0 / 3.0) * math.tan(dt / 4.0)
        
        p1 = Vec2(math.cos(t), math.sin(t))
        p2 = Vec2(math.cos(t_end), math.sin(t_end))
        
        # Derivatives on unit circle
        d1 = Vec2(-math.sin(t), math.cos(t)) * kappa
        d2 = Vec2(math.sin(t_end), -math.cos(t_end)) * kappa
        
        # Control points in unit circle
        q1 = p1 + d1
        q2 = p2 + d2
        
        # Transform back to real space
        def transform(p: Vec2) -> Vec2:
            x_rot = p.x * rx
            y_rot = p.y * ry
            real_x = math.cos(phi) * x_rot - math.sin(phi) * y_rot + cx
            real_y = math.sin(phi) * x_rot + math.cos(phi) * y_rot + cy
            return Vec2(real_x, real_y)
            
        real_cp1 = transform(q1)
        real_cp2 = transform(q2)
        real_end = transform(p2)
        
        if nodes:
            nodes[-1].out_handle = real_cp1
        
        nodes.append(PathNode(position=real_end, in_handle=real_cp2, mode=HandleMode.SMOOTH))
        t = t_end


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

    # Collect filter definitions from objects and emit a <defs> block
    filter_defs: list[str] = []
    filter_id_map: dict[int, str] = {}  # id(obj) -> filter_id string
    filt_counter = 0
    for obj in objects:
        if not obj.visible:
            continue
        svg_filt = getattr(obj, "svg_filter", None)
        if svg_filt and svg_filt.get("type") == "gaussian_blur":
            filt_counter += 1
            fid = f"filter{filt_counter}"
            filter_id_map[id(obj)] = fid
            std_dev = svg_filt.get("std_deviation", 0.0)
            preserve = svg_filt.get("preserve_alpha", True)
            preserve_attr = f' preserveAlpha="{str(preserve).lower()}"'
            filter_defs.append(
                f'    <filter id="{fid}">'
                f'<feGaussianBlur stdDeviation="{std_dev:.2f}"{preserve_attr}/>'
                f'</filter>'
            )

    if filter_defs:
        lines.append("  <defs>")
        lines.extend(filter_defs)
        lines.append("  </defs>")

    for obj in objects:
        if not obj.visible:
            continue
        lines.append(_object_to_svg(obj, filter_id_map))
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


def _object_to_svg(
    obj: VectorObject,
    filter_id_map: dict[int, str] | None = None,
) -> str:
    """Convert a single VectorObject to an SVG element."""
    path = obj.transformed_path()
    d = path_to_svg_d(path)
    style_parts = _style_to_svg_attrs(obj.style)
    filter_attr = ""
    if filter_id_map and id(obj) in filter_id_map:
        fid = filter_id_map[id(obj)]
        filter_attr = f' filter="url(#{fid})"'
    attrs = f'd="{d}" {style_parts}{filter_attr}'
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
    Opacity, filters (e.g. feGaussianBlur), and styles are preserved.
    """
    tree = ET.parse(filepath)
    root = tree.getroot()
    root_xf = _get_root_transform(root)
    defs = _collect_defs(root)
    filters = _collect_filters(root)
    css_rules = _parse_css_rules(root)
    node = _import_element_recursive(
        root, root_xf, parent_style=None,
        defs=defs, filters=filters, css_rules=css_rules,
    )
    return _unwrap_redundant_root(node)


def _unwrap_redundant_root(node: SVGNode) -> SVGNode:
    """Remove an extra group wrapper when the root has exactly one child group.
    
    Typical SVG structure: <svg><g>...</g></svg> produces root(svg)->group(g)->leaves.
    We unwrap so the effective root is the inner group, avoiding a redundant parent.
    """
    if not isinstance(node, SVGGroup):
        return node
    if len(node.children) != 1:
        return node
    child = node.children[0]
    if not isinstance(child, SVGGroup):
        return node
    return child


def import_svg_string(svg_text: str) -> SVGNode:
    """Import from SVG string."""
    root = ET.fromstring(svg_text)
    root_xf = _get_root_transform(root)
    defs = _collect_defs(root)
    filters = _collect_filters(root)
    css_rules = _parse_css_rules(root)
    node = _import_element_recursive(
        root, root_xf, parent_style=None,
        defs=defs, filters=filters, css_rules=css_rules,
    )
    return _unwrap_redundant_root(node)


def _parse_css_rules(root: ET.Element) -> dict[str, dict[str, str]]:
    """Parse simple CSS class rules from <style> tags."""
    css_rules: dict[str, dict[str, str]] = {}
    
    # Find all style tags
    # Usually direct children of svg or inside defs, but could be anywhere
    for elem in root.iter():
        if _strip_ns(elem.tag) == "style":
            content = elem.text
            if not content:
                continue
                
            # Naive regex parser for .classname { key:val; }
            # Handles multi-line, whitespace
            # Non-greedy matching for class names and content
            # Assuming class selectors only for now
            blocks = re.findall(r"\.([\w-]+)\s*\{([^}]+)\}", content)
            for class_name, body in blocks:
                props = {}
                for part in body.split(";"):
                    if ":" in part:
                        k, v = part.split(":", 1)
                        props[k.strip()] = v.strip()
                if props:
                    css_rules[class_name] = props
                    
    return css_rules


def _collect_defs(root: ET.Element) -> dict[str, FillPaint]:
    """Pre-scan for definitions (gradients, patterns)."""
    defs: dict[str, FillPaint] = {}
    
    # Simple recursive search or iter? iter() searches whole tree.
    for elem in root.iter():
        tag = _strip_ns(elem.tag)
        id_ = elem.get("id")
        if not id_:
            continue
            
        if tag == "linearGradient":
            defs[id_] = _parse_linear_gradient(elem)
        elif tag == "radialGradient":
            defs[id_] = _parse_radial_gradient(elem)
            
    return defs


def _collect_filters(root: ET.Element) -> dict[str, dict]:
    """Pre-scan for filter definitions (feGaussianBlur, etc.)."""
    filters: dict[str, dict] = {}
    
    for elem in root.iter():
        tag = _strip_ns(elem.tag)
        id_ = elem.get("id")
        if not id_:
            continue
        
        if tag == "filter":
            # Parse filter primitives inside this filter
            for child in elem:
                child_tag = _strip_ns(child.tag)
                if child_tag == "feGaussianBlur":
                    std_dev = child.get("stdDeviation", "0").strip()
                    # Can be "x" or "x y" for horizontal/vertical
                    parts = std_dev.replace(",", " ").split()
                    try:
                        sigma = float(parts[0]) if parts else 0.0
                    except ValueError:
                        sigma = 0.0
                    # Parse preserveAlpha (custom or SVG2 attribute)
                    pa_str = child.get("preserveAlpha", "false").strip().lower()
                    preserve_alpha = pa_str in ("true", "1", "yes")
                    filters[id_] = {
                        "type": "gaussian_blur",
                        "std_deviation": sigma,
                        "preserve_alpha": preserve_alpha,
                    }
                    break
                # Add more filter types as needed: feBlend, feColorMatrix, etc.
    
    return filters


def _parse_gradient_stops(elem: ET.Element) -> list[GradientStop]:
    stops = []
    for child in elem:
        if _strip_ns(child.tag) == "stop":
            off_str = child.get("offset", "0").strip()
            if off_str.endswith("%"):
                offset = float(off_str.removesuffix("%")) / 100.0
            else:
                offset = float(off_str)
            
            # stop-color
            style_str = child.get("style", "")
            color_str = child.get("stop-color")
            opacity = float(child.get("stop-opacity", "1"))
            
            # Handle style="stop-color:..." precedence
            if style_str:
                for part in style_str.split(";"):
                    kv = part.strip().split(":", 1)
                    if len(kv) == 2:
                        k, v = kv[0].strip(), kv[1].strip()
                        if k == "stop-color":
                            color_str = v
                        elif k == "stop-opacity":
                            opacity = float(v)
            
            if not color_str:
                color_str = "black"
                
            r, g, b, a = _parse_svg_color(color_str)
            stops.append(GradientStop(offset, (r, g, b, a * opacity)))
    
    # Sort by offset
    stops.sort(key=lambda s: s.offset)
    if not stops:
        # Default fallback
        stops = [GradientStop(0, (0,0,0,1)), GradientStop(1, (1,1,1,1))]
    return stops


def _parse_coord(s: str | None, default: float) -> float:
    if not s:
        return default
    s = s.strip()
    if s.endswith("%"):
        return float(s.removesuffix("%")) / 100.0
    try:
        return float(s)
    except ValueError:
        return default


def _parse_gradient_transform(elem: ET.Element) -> AffineTransform:
    """Parse gradientTransform or gradientUnits from gradient element."""
    gt = elem.get("gradientTransform")
    if gt:
        return _parse_transform(gt)
    return AffineTransform.identity()


def _parse_linear_gradient(elem: ET.Element) -> GradientPaint:
    stops = _parse_gradient_stops(elem)
    
    x1 = _parse_coord(elem.get("x1"), 0.0)
    y1 = _parse_coord(elem.get("y1"), 0.0)
    x2 = _parse_coord(elem.get("x2"), 1.0)
    y2 = _parse_coord(elem.get("y2"), 0.0)
    
    start = Vec2(x1, y1)
    end = Vec2(x2, y2)
    xf = _parse_gradient_transform(elem)
    if not xf.is_identity:
        start = xf.apply(start)
        end = xf.apply(end)
    
    return GradientPaint(
        gradient_type=GradientType.LINEAR,
        stops=stops,
        start=start,
        end=end,
    )


def _parse_radial_gradient(elem: ET.Element) -> GradientPaint:
    stops = _parse_gradient_stops(elem)
    
    cx = _parse_coord(elem.get("cx"), 0.5)
    cy = _parse_coord(elem.get("cy"), 0.5)
    r = _parse_coord(elem.get("r"), 0.5)
    fx = _parse_coord(elem.get("fx"), cx)
    fy = _parse_coord(elem.get("fy"), cy)
    
    center = Vec2(cx, cy)
    focal = Vec2(fx, fy)
    xf = _parse_gradient_transform(elem)
    if not xf.is_identity:
        center = xf.apply(center)
        focal = xf.apply(focal)
        r = r * xf.max_scale_factor()
    
    return GradientPaint(
        gradient_type=GradientType.RADIAL,
        stops=stops,
        start=center,
        end=focal,
        radius=r,
        focal_offset=Vec2(focal.x - center.x, focal.y - center.y)
    )


def _get_root_transform(root: ET.Element) -> AffineTransform:
    """Calculate the global transform from SVG root viewport (width/height/viewBox)."""
    # Parse dimensions (handle units like 'mm', 'in')
    w_str = root.get("width")
    h_str = root.get("height")
    w_px = _parse_length(w_str) if w_str else 0.0
    h_px = _parse_length(h_str) if h_str else 0.0

    # Parse viewBox
    vb_str = root.get("viewBox", "")
    if not vb_str:
        return AffineTransform.identity()
    
    try:
        # replace commas with spaces just in case
        vb = [float(f) for f in vb_str.replace(",", " ").split()]
        if len(vb) != 4:
            return AffineTransform.identity()
        vx, vy, vw, vh = vb
    except ValueError:
        return AffineTransform.identity()

    if vw <= 0 or vh <= 0:
        return AffineTransform.identity()

    # Calculate scale
    # If width/height are specified, we map viewBox to those dimensions.
    # Otherwise we assume 1 user unit = 1 pixel (scale 1).
    sx = w_px / vw if w_px > 0 else 1.0
    sy = h_px / vh if h_px > 0 else 1.0
    
    # If only one dimension is specified, preserve aspect ratio? 
    # SVG spec implies usually both or none for root. 
    # If neither specified, default to 1.0 scale (user units).
    
    # Create transform: translate(-vx, -vy) -> scale(sx, sy)
    # The order is: first shift the viewbox origin to (0,0), then scale.
    t1 = AffineTransform.translation(-vx, -vy)
    s1 = AffineTransform.scaling(sx, sy)
    return t1.concat(s1)


def _parse_element_opacity(
    elem: ET.Element,
    css_rules: dict[str, dict[str, str]] | None = None,
) -> float:
    """Parse element-level opacity from attribute or style."""
    val = elem.get("opacity")
    if val is not None:
        try:
            return float(val.strip())
        except ValueError:
            pass
    # Check style attribute
    style = elem.get("style", "")
    if style:
        for part in style.split(";"):
            if ":" in part:
                k, v = part.strip().split(":", 1)
                if k.strip() == "opacity":
                    try:
                        return float(v.strip())
                    except ValueError:
                        pass
    # Check CSS class
    if css_rules:
        for cls_name in elem.get("class", "").split():
            if cls_name in css_rules and "opacity" in css_rules[cls_name]:
                try:
                    return float(css_rules[cls_name]["opacity"].strip())
                except ValueError:
                    pass
    return 1.0


def _parse_filter_ref(
    filter_attr: str | None,
    filters: dict[str, dict],
) -> dict | None:
    """Resolve filter attribute (e.g. url(#filter4481)) to filter definition."""
    if not filter_attr or not filter_attr.strip().startswith("url(#"):
        return None
    # Extract id from url(#filter4481)
    match = re.search(r"url\(#([^)]+)\)", filter_attr.strip())
    if match:
        ref_id = match.group(1)
        return filters.get(ref_id)
    return None


def _import_element_recursive(
    elem: ET.Element, 
    parent_xf: AffineTransform, 
    parent_style: VectorStyle | None = None,
    defs: dict[str, FillPaint] | None = None,
    filters: dict[str, dict] | None = None,
    css_rules: dict[str, dict[str, str]] | None = None,
    inherited_filter: dict | None = None,
) -> SVGNode:
    """Recursively parse an SVG element and its children."""
    tag = _strip_ns(elem.tag)
    
    # Parse element-level transform
    local_xf = _parse_transform(elem.get("transform", ""))
    current_xf = parent_xf.concat(local_xf)
    
    # Resolve style for this element (inheriting from parent)
    resolved_style = _parse_style_attrs(elem, parent_style, defs, css_rules)

    # Identify element ID/Name
    name = elem.get("id", tag)

    # 1. Container elements
    if tag in ("g", "svg", "a", "defs", "symbol"): 
        if tag in ("defs", "symbol"):
            # Parsing defs as a group for now (though they are usually hidden)
            # Ideally we should populate a Defs context, but for now we structure them.
            return SVGGroup(name=name + " (Defs)")
            
        group = SVGGroup(name=name)
        # Group-level filter applies to all descendants (SVG spec)
        group_filter = _parse_filter_ref(elem.get("filter"), filters or {})
        child_inherited = group_filter if group_filter else inherited_filter
        # Recurse
        for child in elem:
            node = _import_element_recursive(
                child, current_xf, resolved_style,
                defs=defs, filters=filters, css_rules=css_rules,
                inherited_filter=child_inherited,
            )
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
        obj = _parse_path_element(elem, resolved_style)
    elif tag == "rect":
        obj = _parse_rect_element(elem, resolved_style)
    elif tag == "circle":
        obj = _parse_circle_element(elem, resolved_style)
    elif tag == "ellipse":
        obj = _parse_ellipse_element(elem, resolved_style)
    elif tag == "polygon":
        obj = _parse_polygon_element(elem, resolved_style)
    elif tag == "polyline":
        obj = _parse_polyline_element(elem, resolved_style)
        
    if obj:
        obj.transform = parent_xf.concat(obj.transform)
        # Apply element-level opacity and filter (element's own or inherited from group)
        obj.opacity = _parse_element_opacity(elem, css_rules)
        svg_filt = _parse_filter_ref(elem.get("filter"), filters or {}) or inherited_filter
        if svg_filt:
            obj.svg_filter = svg_filt
        return SVGLeaf(name=obj.name, object=obj)

    # Fallback for unknown/empty
    return SVGGroup(name=f"Empty ({tag})")


# ---------------------------------------------------------------------------
#  Element parsers
# ---------------------------------------------------------------------------

def _parse_path_element(elem: ET.Element, style: VectorStyle) -> VectorObject | None:
    d = elem.get("d", "")
    if not d:
        return None
    path = svg_d_to_path(d)
    path.fill_rule = _parse_fill_rule(elem)
    
    xf = _parse_transform(elem.get("transform", ""))
    return VectorObject(
        name=elem.get("id", "Path"),
        path=path,
        style=style,
        transform=xf,
    )


def _parse_rect_element(elem: ET.Element, style: VectorStyle) -> VectorObject | None:
    x = float(elem.get("x", "0"))
    y = float(elem.get("y", "0"))
    w = float(elem.get("width", "0"))
    h = float(elem.get("height", "0"))
    rx = float(elem.get("rx", "0"))
    ry = float(elem.get("ry", str(rx)))
    r = max(rx, ry)
    shape = RectangleShape(width=w, height=h, corner_radii=(r, r, r, r))
    xf = AffineTransform.translation(x + w / 2, y + h / 2)
    parent_xf = _parse_transform(elem.get("transform", ""))
    xf = parent_xf.concat(xf)
    return VectorObject(
        name=elem.get("id", "Rectangle"),
        shape=shape,
        style=style,
        transform=xf,
    )


def _parse_circle_element(elem: ET.Element, style: VectorStyle) -> VectorObject | None:
    cx = float(elem.get("cx", "0"))
    cy = float(elem.get("cy", "0"))
    r = float(elem.get("r", "0"))
    shape = EllipseShape(rx=r, ry=r)
    xf = AffineTransform.translation(cx, cy)
    parent_xf = _parse_transform(elem.get("transform", ""))
    xf = parent_xf.concat(xf)
    return VectorObject(
        name=elem.get("id", "Circle"),
        shape=shape,
        style=style,
        transform=xf,
    )


def _parse_ellipse_element(elem: ET.Element, style: VectorStyle) -> VectorObject | None:
    cx = float(elem.get("cx", "0"))
    cy = float(elem.get("cy", "0"))
    rx = float(elem.get("rx", "0"))
    ry = float(elem.get("ry", "0"))
    shape = EllipseShape(rx=rx, ry=ry)
    xf = AffineTransform.translation(cx, cy)
    parent_xf = _parse_transform(elem.get("transform", ""))
    xf = parent_xf.concat(xf)
    return VectorObject(
        name=elem.get("id", "Ellipse"),
        shape=shape,
        style=style,
        transform=xf,
    )


def _parse_polygon_element(elem: ET.Element, style: VectorStyle) -> VectorObject | None:
    pts_str = elem.get("points", "")
    points = _parse_points(pts_str)
    if len(points) < 3:
        return None
    nodes = [PathNode(position=p, mode=HandleMode.SHARP) for p in points]
    sp = SubPath(nodes, closed=True)
    path = VectorPath([sp])
    path.fill_rule = _parse_fill_rule(elem)
    
    xf = _parse_transform(elem.get("transform", ""))
    return VectorObject(name=elem.get("id", "Polygon"), path=path, style=style, transform=xf)


def _parse_polyline_element(elem: ET.Element, style: VectorStyle) -> VectorObject | None:
    pts_str = elem.get("points", "")
    points = _parse_points(pts_str)
    if len(points) < 2:
        return None
    nodes = [PathNode(position=p, mode=HandleMode.SHARP) for p in points]
    sp = SubPath(nodes, closed=False)
    path = VectorPath([sp])
    path.fill_rule = _parse_fill_rule(elem)
    
    xf = _parse_transform(elem.get("transform", ""))
    return VectorObject(name=elem.get("id", "Polyline"), path=path, style=style, transform=xf)


def _parse_fill_rule(elem: ET.Element) -> FillRule:
    rule = elem.get("fill-rule", "nonzero").lower()
    # Check style strings
    style = elem.get("style", "")
    if style:
        for part in style.split(";"):
            kv = part.strip().split(":", 1)
            if len(kv) == 2 and kv[0].strip() == "fill-rule":
                rule = kv[1].strip().lower()
    
    if rule == "evenodd":
        return FillRule.EVEN_ODD
    return FillRule.NON_ZERO


# ---------------------------------------------------------------------------
#  Style parsing
# ---------------------------------------------------------------------------

def _parse_style_attrs(
    elem: ET.Element, 
    parent: VectorStyle | None = None,
    defs: dict[str, FillPaint] | None = None,
    css_rules: dict[str, dict[str, str]] | None = None
) -> VectorStyle:
    """Parse fill / stroke attributes from an SVG element, merging with parent."""
    # Check for inline style attribute
    inline = elem.get("style", "")
    attrs: dict[str, str] = {}
    
    # 1. Apply CSS classes (lowest priority in this local scope, but overrides inherited)
    # Actually, presentation attrs override class, and inline overrides presentation.
    # Spec: https://www.w3.org/TR/SVG11/styling.html#UsingPresentationAttributes
    # "Presentation attributes ... are equivalent to 0-specificity CSS rules."
    # So: Class > Presentation Attribute > Inherited.
    # Inline style > Class.
    
    # So order of application to 'attrs' dict (last write wins):
    # 1. Class rules
    # 2. Presentation attributes? NO. Logic error in spec reading?
    # Spec says: "Presentation attributes... act as a backup" for non-CSS UAs?
    # No, spec says: "presentation attributes... are translated to corresponding CSS property declarations... with specificity 0".
    # CSS Classes have specificity >= 10 (usually).
    # So Class wins over Presentation Attribute.
    # Inline style has specificity 1000.
    
    # Implementation:
    # 1. Load Presentation Attributes
    # 2. Overwrite with Class Rules
    # 3. Overwrite with Inline Style
    
    # 1. Presentation Attributes
    for attr in ("fill", "stroke", "stroke-width", "fill-opacity", "stroke-opacity",
                 "stroke-linecap", "stroke-linejoin", "stroke-dasharray"):
         val = elem.get(attr)
         if val is not None:
             attrs[attr] = val
             
    # 2. Class Rules
    if css_rules:
        cls_attr = elem.get("class", "")
        if cls_attr:
            # Handle multiple classes "cls1 cls2"
            for cls_name in cls_attr.split():
                if cls_name in css_rules:
                    # Merge class properties
                    for k, v in css_rules[cls_name].items():
                        # Only apply known vector attributes
                        if k in ("fill", "stroke", "stroke-width", "fill-opacity", "stroke-opacity",
                                 "stroke-linecap", "stroke-linejoin", "stroke-dasharray"):
                            attrs[k] = v

    # 3. Inline Style
    if inline:
        for part in inline.split(";"):
            kv = part.strip().split(":", 1)
            if len(kv) == 2:
                attrs[kv[0].strip()] = kv[1].strip()

    fills: list[VectorFill] = []
    strokes: list[VectorStroke] = []
    
    # Defaults
    
    # 1. Fill
    fill_parsed = False
    fill_str = attrs.get("fill")
    if fill_str is not None:
        fill_parsed = True
        fill_opacity = float(attrs.get("fill-opacity", "1"))
        if fill_str != "none":
            # Check for URL reference
            paint: FillPaint | None = None
            if fill_str.startswith("url(#") and fill_str.endswith(")") and defs:
                ref_id = fill_str[5:-1]
                if ref_id in defs:
                    paint = copy.deepcopy(defs[ref_id])
            
            if paint is None:
                color = _parse_svg_color(fill_str)
                paint = SolidPaint(color)
                
            fills.append(VectorFill(paint, opacity=fill_opacity))
    
    if not fill_parsed and parent and parent.fills:
        # Inherit
        fills = [copy.deepcopy(f) for f in parent.fills]
    elif not fill_parsed and not fills:
        # Initial value: black (if NOT 'none' and no parent)
        fills.append(VectorFill(SolidPaint((0.0, 0.0, 0.0, 1.0))))


    # 2. Stroke
    stroke_parsed = False
    stroke_str = attrs.get("stroke")
    if stroke_str is not None:
        stroke_parsed = True
        stroke_opacity = float(attrs.get("stroke-opacity", "1"))
        stroke_w = _parse_length(attrs.get("stroke-width", "1"))
        cap_val = attrs.get("stroke-linecap", "round")
        join_val = attrs.get("stroke-linejoin", "round")
        dash_str = attrs.get("stroke-dasharray", "")
        
        if stroke_str != "none":
            # Stroke paint
            paint: FillPaint | None = None
            if stroke_str.startswith("url(#") and stroke_str.endswith(")") and defs:
                ref_id = stroke_str[5:-1]
                if ref_id in defs:
                    paint = copy.deepcopy(defs[ref_id])
            
            if paint is None:
                color = _parse_svg_color(stroke_str)
                paint = SolidPaint(color)
            
            cap_map = {"butt": StrokeCap.BUTT, "round": StrokeCap.ROUND, "square": StrokeCap.SQUARE}
            join_map = {"miter": StrokeJoin.MITER, "round": StrokeJoin.ROUND, "bevel": StrokeJoin.BEVEL}
            cap = cap_map.get(cap_val, StrokeCap.ROUND)
            join = join_map.get(join_val, StrokeJoin.ROUND)
            
            dash = DashPattern()
            if dash_str and dash_str != "none":
                dash.dashes = [float(v) for v in dash_str.replace(",", " ").split()]
                
            strokes.append(VectorStroke(
                paint, width=stroke_w, opacity=stroke_opacity,
                cap=cap, join=join, dash=dash,
            ))
            
    if not stroke_parsed and parent and parent.strokes:
        # Inherit stroke
        strokes = [copy.deepcopy(s) for s in parent.strokes]
        
    return VectorStyle( fills=fills, strokes=strokes )


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
            h = "".join(c * 2 for c in h)
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
    # Replace commas with spaces and handle negative numbers
    s = s.replace(",", " ")
    # Basic tokenisation
    tokens = s.split()
    nums = []
    for t in tokens:
        try:
            nums.append(float(t))
        except ValueError:
            pass
    
    points: list[Vec2] = []
    for i in range(0, len(nums) - 1, 2):
        points.append(Vec2(nums[i], nums[i+1]))
    return points


def _parse_length(s: str) -> float:
    """Parse SVG length string (e.g. '10px', '2pt') to float pixels."""
    if not s:
        return 0.0
    s = s.strip().lower()
    if s.endswith("px"):
        return float(s.removesuffix("px"))
    elif s.endswith("pt"):
        return float(s.removesuffix("pt")) * 1.333333
    elif s.endswith("pc"):
        return float(s.removesuffix("pc")) * 16.0
    elif s.endswith("mm"):
        return float(s.removesuffix("mm")) * 3.779527
    elif s.endswith("cm"):
        return float(s.removesuffix("cm")) * 37.795275
    elif s.endswith("in"):
        return float(s.removesuffix("in")) * 96.0
    elif s.endswith("%"):
        # Percentage requires context (viewport size), fallback to raw value or 0
        try:
            return float(s.removesuffix("%"))
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _strip_ns(tag: str) -> str:
    """Remove XML namespace from a tag."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag
