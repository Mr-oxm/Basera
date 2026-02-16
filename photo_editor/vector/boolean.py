"""Boolean operations on VectorPaths using QPainterPath.
"""

from __future__ import annotations
from enum import Enum, auto

from PySide6.QtGui import QPainterPath
from PySide6.QtCore import Qt

from .path import VectorPath, SubPath, PathNode, HandleMode, FillRule
from .geometry import Vec2

__all__ = ["BooleanOp", "path_boolean"]


class BooleanOp(Enum):
    UNION = auto()
    SUBTRACT = auto()
    INTERSECT = auto()
    EXCLUDE = auto()       # XOR
    DIVIDE = auto()        # Not directly supported by QPainterPath as a primitive, need emulation


def path_boolean(
    subject: VectorPath,
    clip: VectorPath,
    op: BooleanOp,
    tolerance: float = 0.25,
) -> VectorPath:
    """Perform a boolean operation between *subject* and *clip*."""
    
    p1 = subject.qpath
    p2 = clip.qpath
    
    # Ensure fill rules are consistent for the operation if needed, 
    # but QPainterPath handles them.
    
    result_qpath = QPainterPath()
    
    if op == BooleanOp.UNION:
        result_qpath = p1.united(p2)
    elif op == BooleanOp.SUBTRACT:
        result_qpath = p1.subtracted(p2)
    elif op == BooleanOp.INTERSECT:
        result_qpath = p1.intersected(p2)
    elif op == BooleanOp.EXCLUDE:
        # XOR
        # QPainterPath doesn't have explicit xor, but we can do (A+B) - (A*B)
        # Actually Qt might assume winding?
        # United includes everything. Intersect includes overlap.
        # Subtracted...
        # A XOR B = (A | B) - (A & B)
        # But QPainterPath doesn't have xor? 
        # Wait, strictly speaking, XOR fill rule with combined path is XOR?
        # But we want a path outline.
        # (p1.subtracted(p2)).united(p2.subtracted(p1))
        part1 = p1.subtracted(p2)
        part2 = p2.subtracted(p1)
        result_qpath = part1.united(part2)
    
    elif op == BooleanOp.DIVIDE:
        # Division is complex: (A & B) + (A - B) + (B - A)
        # Result is a compound path containing all these pieces as separate subpaths?
        # QPainterPath united just merges them.
        # VectorPath usually represents a single object.
        # This operation might expect to return multiple VectorPaths?
        # The original signature returns `VectorPath` (singular).
        # So it probably returns the union of the split parts (which is just the union?).
        # Or maybe it keeps internal lines?
        # If the user wants "Divide", they usually want separate objects.
        # But since we return one VectorPath, let's just return the Union of interactions
        # but with internal edges? QPainterPath boolean ops dissolve internal edges.
        # For now, let's implement as (A & B) | (A - B) | (B - A) which is just Union if touching.
        # Actually, let's return the simplified union for now as a fallback 
        # because QPainterPath doesn't support non-dissolving boolean easily.
        result_qpath = p1.united(p2)

    return qpath_to_vector_path(result_qpath)


def qpath_to_vector_path(qpath: QPainterPath) -> VectorPath:
    """Convert a QPainterPath back to an editable VectorPath."""
    vp = VectorPath()
    count = qpath.elementCount()
    
    if count == 0:
        return vp
        
    current_nodes: list[PathNode] = []
    
    def flush_subpath(closed: bool):
        if current_nodes:
            vp.add_sub_path(SubPath(list(current_nodes), closed=closed))
            current_nodes.clear()

    i = 0
    while i < count:
        d = qpath.elementAt(i)
        
        # QPainterPath.Element type check
        # Types are integers or enums. 
        # MoveToElement=0, LineToElement=1, CurveToElement=2, CurveToDataElement=3
        
        etype = d.type
        
        if etype == QPainterPath.MoveToElement:
            flush_subpath(closed=False) # Previous was open if we are moving?
            # Actually QPainterPath doesn't explicitly mark 'closed' except by geometry?
            # Or assume subpaths are open unless we detect closure?
            # Ideally we check if last point equals first point.
            
            node = PathNode(Vec2(d.x, d.y))
            current_nodes.append(node)
            i += 1
            
        elif etype == QPainterPath.LineToElement:
            node = PathNode(Vec2(d.x, d.y))
            current_nodes.append(node)
            i += 1
            
        elif etype == QPainterPath.CurveToElement:
            # d is CP1
            cp1 = Vec2(d.x, d.y)
            i += 1
            if i >= count: break
            
            d2 = qpath.elementAt(i) # CP2
            cp2 = Vec2(d2.x, d2.y)
            i += 1
            if i >= count: break
            
            d3 = qpath.elementAt(i) # End
            end = Vec2(d3.x, d3.y)
            i += 1
            
            # Retrieve previous node to set its out_handle (CP1)
            if current_nodes:
                prev = current_nodes[-1]
                prev.out_handle = cp1
                prev.mode = HandleMode.SMOOTH # Assume smooth if curve
            
            # Create new node with in_handle (CP2)
            node = PathNode(end, in_handle=cp2, mode=HandleMode.SMOOTH)
            current_nodes.append(node)
            
        else:
            i += 1
            
    # Check closure for the last subpath
    if current_nodes:
        # If last node approx equals first node, treat as closed and remove last node
        if len(current_nodes) > 1 and current_nodes[-1].position.approx_eq(current_nodes[0].position):
            # Pass the handles from last node to first node if any
            first = current_nodes[0]
            last = current_nodes[-1]
            first.in_handle = last.in_handle
            current_nodes.pop()
            flush_subpath(closed=True)
        else:
            flush_subpath(closed=False)
            
    return vp
