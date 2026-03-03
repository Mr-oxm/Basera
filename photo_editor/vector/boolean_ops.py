"""Higher-level boolean operations at the document-layer level.

Each operation:
1. Takes multiple selected SHAPE layers from the document.
2. Extracts their flattened ``VectorPath`` instances.
3. Runs the QPainterPath boolean operation.
4. Creates new SHAPE layer(s) with the resulting path(s).
5. Removes the source layers.

All operations go through ``doc.save_snapshot`` first so they are
undoable as a single action.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from PySide6.QtGui import QPainterPath

from .boolean import BooleanOp, path_boolean, qpath_to_vector_path
from .scene import VectorObject, VectorLayer
from .style import VectorStyle
from .geometry import AffineTransform

if TYPE_CHECKING:
    from ..core.document import Document
    from ..core.layer import Layer


__all__ = [
    "perform_union",
    "perform_subtract",
    "perform_intersect",
    "perform_exclude",
    "perform_divide",
    "get_sorted_vector_layers",
    "compute_preview_path",
]


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def get_sorted_vector_layers(
    doc: "Document", layer_ids: list[str] | set[str],
) -> list["Layer"]:
    """Return vector layers in stack order (bottom → top)."""
    result = []
    for layer in doc.layers.layers:
        if layer.id in layer_ids and getattr(layer, "_vector_data", None) is not None:
            result.append(layer)
    return result  # already in stack order (layers list is bottom→top)


def _get_ordered_layers(
    doc: "Document", layer_ids: list[str] | set[str],
) -> list["Layer"]:
    """Return vector layers preserving the order of *layer_ids*.

    Unlike ``get_sorted_vector_layers`` which sorts by stack position,
    this keeps the user's selection order so that the first ID in the
    list corresponds to the first-selected layer (base for Subtract).
    """
    layer_map = {l.id: l for l in doc.layers.layers
                 if getattr(l, "_vector_data", None) is not None}
    return [layer_map[lid] for lid in layer_ids if lid in layer_map]


def _extract_combined_qpath(layer: "Layer") -> QPainterPath:
    """Combine all VectorObjects in a layer into a single QPainterPath."""
    vl = getattr(layer, "_vector_data", None)
    if vl is None:
        return QPainterPath()
    combined = QPainterPath()
    for obj in vl.objects:
        combined = combined.united(obj.flatten_to_path().qpath)
    return combined


def _extract_path(layer: "Layer"):
    """Extract combined VectorPath from a layer."""
    qp = _extract_combined_qpath(layer)
    return qpath_to_vector_path(qp)


def _get_first_style(layer: "Layer") -> VectorStyle:
    """Clone the style from the first object on the layer."""
    vl = getattr(layer, "_vector_data", None)
    if vl is not None and vl.objects:
        return copy.deepcopy(vl.objects[0].style)
    return VectorStyle()


def _insert_result_layer(
    doc: "Document",
    result_path,
    name: str,
    style: VectorStyle,
    insert_index: int,
) -> "Layer":
    """Create a SHAPE layer with *result_path* at *insert_index*."""
    from ..core.enums import LayerType
    from ..core.layer import Layer as _Layer
    from .rasterizer import rasterize_vector_layer_tight

    new_layer = _Layer(
        name=name,
        width=max(doc.width, 1),
        height=max(doc.height, 1),
        layer_type=LayerType.SHAPE,
    )
    vl = VectorLayer()
    obj = VectorObject(name=name, path=result_path, style=style)
    vl.add(obj)
    new_layer._vector_data = vl

    idx = min(insert_index, len(doc.layers.layers))
    doc.layers.add(new_layer, index=idx)
    rasterize_vector_layer_tight(doc, layer=new_layer)
    return new_layer


def _remove_source_layers(doc: "Document", layer_ids: list[str]) -> None:
    """Remove source layers *without* creating individual snapshots.

    Also cleans ``_selected_indices`` so no stale indices remain.
    """
    for lid in list(layer_ids):
        doc.layers.remove(lid)
    # Purge selected_indices that are now out of range
    max_idx = len(doc.layers.layers) - 1
    doc.layers._selected_indices = {
        i for i in doc.layers._selected_indices if 0 <= i <= max_idx
    }


def _select_result_layer(doc: "Document", layer: "Layer") -> None:
    """Point active_index and selected_indices at the new result layer."""
    try:
        idx = doc.layers.layers.index(layer)
    except ValueError:
        return
    doc.layers._active_index = idx
    doc.layers._selected_indices = {idx}


def _bottom_index(doc: "Document", layers: list["Layer"]) -> int:
    """Return the lowest stack index among *layers*."""
    all_layers = doc.layers.layers
    indices = []
    for l in layers:
        try:
            indices.append(all_layers.index(l))
        except ValueError:
            pass
    return min(indices) if indices else len(all_layers)


# ---------------------------------------------------------------------------
#  Preview helper (for hover-preview on canvas)
# ---------------------------------------------------------------------------

def compute_preview_path(
    doc: "Document",
    layer_ids: list[str] | set[str],
    op: BooleanOp,
):
    """Return a VectorPath preview of the boolean result (or *None*).

    *layer_ids* is an **ordered** list — the first element is the base
    (for Subtract: what remains), the second is the cutter.
    """
    layers = _get_ordered_layers(doc, layer_ids)
    if len(layers) < 2:
        return None

    if op == BooleanOp.SUBTRACT:
        base = _extract_combined_qpath(layers[0])   # first-selected
        cutter = _extract_combined_qpath(layers[1])  # second-selected
        return qpath_to_vector_path(base.subtracted(cutter))

    if op == BooleanOp.DIVIDE:
        return None  # preview not meaningful for multiple fragments

    # Accumulate from first
    result = _extract_combined_qpath(layers[0])
    for layer in layers[1:]:
        other = _extract_combined_qpath(layer)
        if op == BooleanOp.UNION:
            result = result.united(other)
        elif op == BooleanOp.INTERSECT:
            result = result.intersected(other)
        elif op == BooleanOp.EXCLUDE:
            part1 = result.subtracted(other)
            part2 = other.subtracted(result)
            result = part1.united(part2)
    return qpath_to_vector_path(result)


# ---------------------------------------------------------------------------
#  Operations
# ---------------------------------------------------------------------------

def perform_union(doc: "Document", layer_ids: list[str]) -> str | None:
    """Union of 2+ paths → single result layer.  Returns new layer ID."""
    layers = get_sorted_vector_layers(doc, layer_ids)
    if len(layers) < 2:
        return None

    doc.save_snapshot("Boolean: Union")

    result_qp = _extract_combined_qpath(layers[0])
    for layer in layers[1:]:
        result_qp = result_qp.united(_extract_combined_qpath(layer))

    result_path = qpath_to_vector_path(result_qp)
    style = _get_first_style(layers[0])
    idx = _bottom_index(doc, layers)
    ids = [l.id for l in layers]
    _remove_source_layers(doc, ids)
    new = _insert_result_layer(doc, result_path, "Union Result", style, idx)
    _select_result_layer(doc, new)
    return new.id


def perform_subtract(doc: "Document", layer_ids: list[str]) -> str | None:
    """Subtract second-selected from first-selected.  Returns new layer ID.

    *layer_ids* is ordered by selection sequence: ids[0] is the base
    (what survives), ids[1] is the cutter (what is removed).
    """
    layers = _get_ordered_layers(doc, layer_ids)
    if len(layers) != 2:
        return None

    doc.save_snapshot("Boolean: Subtract")

    base, cutter = layers[0], layers[1]  # selection order
    base_qp = _extract_combined_qpath(base)
    cutter_qp = _extract_combined_qpath(cutter)
    result_qp = base_qp.subtracted(cutter_qp)

    result_path = qpath_to_vector_path(result_qp)
    style = _get_first_style(base)
    idx = _bottom_index(doc, layers)
    ids = [l.id for l in layers]
    _remove_source_layers(doc, ids)
    new = _insert_result_layer(doc, result_path, "Subtract Result", style, idx)
    _select_result_layer(doc, new)
    return new.id


def perform_intersect(doc: "Document", layer_ids: list[str]) -> str | None:
    """Intersection of 2+ paths.  Returns new layer ID or None if empty."""
    layers = get_sorted_vector_layers(doc, layer_ids)
    if len(layers) < 2:
        return None

    doc.save_snapshot("Boolean: Intersect")

    result_qp = _extract_combined_qpath(layers[0])
    for layer in layers[1:]:
        result_qp = result_qp.intersected(_extract_combined_qpath(layer))

    if result_qp.isEmpty():
        return None  # caller should show "No intersection found"

    result_path = qpath_to_vector_path(result_qp)
    style = _get_first_style(layers[0])
    idx = _bottom_index(doc, layers)
    ids = [l.id for l in layers]
    _remove_source_layers(doc, ids)
    new = _insert_result_layer(doc, result_path, "Intersect Result", style, idx)
    _select_result_layer(doc, new)
    return new.id


def perform_exclude(doc: "Document", layer_ids: list[str]) -> str | None:
    """XOR of 2 paths.  Returns new layer ID.

    *layer_ids* is ordered by selection sequence: ids[0] = A, ids[1] = B.
    Result is (A − B) ∪ (B − A) — the order affects which region
    keeps which style.
    """
    layers = _get_ordered_layers(doc, layer_ids)
    if len(layers) != 2:
        return None

    doc.save_snapshot("Boolean: Exclude")

    qp_a = _extract_combined_qpath(layers[0])
    qp_b = _extract_combined_qpath(layers[1])
    part1 = qp_a.subtracted(qp_b)
    part2 = qp_b.subtracted(qp_a)
    result_qp = part1.united(part2)

    result_path = qpath_to_vector_path(result_qp)
    style = _get_first_style(layers[0])
    idx = _bottom_index(doc, layers)
    ids = [l.id for l in layers]
    _remove_source_layers(doc, ids)
    new = _insert_result_layer(doc, result_path, "Exclude Result", style, idx)
    _select_result_layer(doc, new)
    return new.id


def perform_divide(doc: "Document", layer_ids: list[str]) -> list[str]:
    """Divide 2+ paths into fragments.  Returns list of new layer IDs."""
    layers = get_sorted_vector_layers(doc, layer_ids)
    if len(layers) < 2:
        return []

    doc.save_snapshot("Boolean: Divide")

    # Collect all QPaths
    qpaths = [_extract_combined_qpath(l) for l in layers]

    # Build distinct regions:
    # For every pair, compute: only-A, only-B, A∩B
    # For n inputs this is a simplification — we compute pairwise
    # fragments and collect them.
    fragments: list[QPainterPath] = []
    seen_empty = set()

    if len(qpaths) == 2:
        a, b = qpaths
        ab = a.intersected(b)
        a_only = a.subtracted(b)
        b_only = b.subtracted(a)
        for frag in (a_only, ab, b_only):
            if not frag.isEmpty():
                fragments.append(frag)
    else:
        # For 3+ paths: accumulate intersections and differences
        # Use a sweep approach: each path minus union-of-others + pairwise intersections
        union_all = QPainterPath()
        for qp in qpaths:
            union_all = union_all.united(qp)

        for i, qp_i in enumerate(qpaths):
            others = QPainterPath()
            for j, qp_j in enumerate(qpaths):
                if i != j:
                    others = others.united(qp_j)
            only_i = qp_i.subtracted(others)
            if not only_i.isEmpty():
                fragments.append(only_i)

        # Pairwise intersections minus other paths
        for i in range(len(qpaths)):
            for j in range(i + 1, len(qpaths)):
                inter = qpaths[i].intersected(qpaths[j])
                if not inter.isEmpty():
                    # Subtract any other paths' interiors to get unique region
                    for k in range(len(qpaths)):
                        if k != i and k != j:
                            inter = inter.subtracted(qpaths[k])
                    if not inter.isEmpty():
                        fragments.append(inter)

        # Full intersection of all paths
        if len(qpaths) >= 3:
            full_inter = qpaths[0]
            for qp in qpaths[1:]:
                full_inter = full_inter.intersected(qp)
            if not full_inter.isEmpty():
                fragments.append(full_inter)

    if not fragments:
        return []

    style = _get_first_style(layers[0])
    idx = _bottom_index(doc, layers)
    ids = [l.id for l in layers]
    _remove_source_layers(doc, ids)

    new_ids: list[str] = []
    for i, frag_qp in enumerate(fragments, 1):
        frag_path = qpath_to_vector_path(frag_qp)
        name = f"Divide Fragment {i}"
        new = _insert_result_layer(doc, frag_path, name, copy.deepcopy(style), idx + i - 1)
        new_ids.append(new.id)

    # Select the first result layer so it's immediately usable
    if new_ids:
        first = doc.layers.get(new_ids[0])
        if first:
            _select_result_layer(doc, first)

    return new_ids
