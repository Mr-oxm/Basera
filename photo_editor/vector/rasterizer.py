"""Fast vector rasteriser → numpy RGBA float32 buffers.

Uses vectorised numpy operations for all inner loops — no Python-level
per-pixel work.  Configurable super-sampling for anti-aliased edges.

The rasteriser only allocates/writes to the bounding-box region of each
object, minimising memory and compute for small shapes on large canvases.

Per-object render cache avoids re-rasterising unchanged objects during
interactive edits.
"""

from __future__ import annotations

import hashlib
import math
from typing import Sequence

import numpy as np

from .geometry import Vec2, BBox, AffineTransform
from .path import VectorPath, SubPath, FillRule
from .style import (
    VectorStyle, VectorFill, VectorStroke,
    SolidPaint, GradientPaint, GradientType, PatternPaint,
    StrokeCap, StrokeJoin, StrokeAlign,
)
from .scene import VectorObject, VectorLayer

__all__ = ["VectorRasterizer"]

# Super-sampling factor for anti-aliased edges (default high-quality)
_SS = 4
_SS_INV = 1.0 / _SS

# Interactive mode uses lower super-sampling for speed
_interactive_mode: bool = False


def set_interactive_mode(enabled: bool) -> None:
    """Enable low-quality mode during drags for faster preview."""
    global _interactive_mode
    _interactive_mode = enabled


def get_interactive_mode() -> bool:
    return _interactive_mode


class VectorRasterizer:
    """Rasterises a ``VectorLayer`` into a float32 RGBA buffer.

    Includes a per-object render cache that avoids expensive scanline
    rasterisation when objects haven't changed.
    """

    def __init__(self, tile_size: int = 256) -> None:
        self.tile_size = tile_size
        # Cache: obj_id → (state_hash, origin, rendered_buf)
        self._cache: dict[str, tuple[str, tuple[float, float], np.ndarray]] = {}
        self._max_cache_entries: int = 128

    # ---- Public API ---------------------------------------------------------

    def rasterize_layer(
        self,
        vector_layer: VectorLayer,
        width: int,
        height: int,
        viewport: BBox | None = None,
        zoom: float = 1.0,
        origin: tuple[float, float] = (0.0, 0.0),
    ) -> np.ndarray:
        """Render all visible objects to an RGBA float32 array.

        *origin* is the world-space coordinate that maps to pixel (0, 0).
        Use this to render into a tight bounding-box buffer.

        Per-object caching skips re-rendering objects whose state
        (geometry, style, transform) hasn't changed since the last call.
        """
        buf = np.zeros((height, width, 4), dtype=np.float32)
        for obj in vector_layer.objects:
            if not obj.visible:
                continue
            state_hash = self._object_state_hash(obj)
            cached = self._cache.get(obj.id)
            if cached is not None:
                c_hash, c_origin, c_buf = cached
                if c_hash == state_hash and c_origin == origin:
                    # Composite cached buffer onto output
                    ch, cw = c_buf.shape[:2]
                    if ch <= height and cw <= width:
                        # Cached buf is same size — direct alpha-over composite
                        alpha = c_buf[:, :, 3:4]
                        buf[:ch, :cw] = buf[:ch, :cw] * (1.0 - alpha) + c_buf
                        continue
            # Cache miss — render from scratch
            obj_buf = np.zeros((height, width, 4), dtype=np.float32)
            self._render_object(obj_buf, obj, zoom, origin)
            # Store in cache
            if len(self._cache) >= self._max_cache_entries:
                # Evict oldest entries (simple FIFO)
                to_remove = list(self._cache.keys())[: len(self._cache) // 4]
                for k in to_remove:
                    del self._cache[k]
            self._cache[obj.id] = (state_hash, origin, obj_buf)
            # Composite onto output
            alpha = obj_buf[:, :, 3:4]
            buf = buf * (1.0 - alpha) + obj_buf
        return buf

    def rasterize_object(
        self,
        obj: VectorObject,
        width: int,
        height: int,
        zoom: float = 1.0,
        origin: tuple[float, float] = (0.0, 0.0),
    ) -> np.ndarray:
        buf = np.zeros((height, width, 4), dtype=np.float32)
        self._render_object(buf, obj, zoom, origin)
        return buf

    def invalidate(self, obj_id: str | None = None) -> None:
        """Remove cached render for *obj_id*, or all if None."""
        if obj_id is None:
            self._cache.clear()
        else:
            self._cache.pop(obj_id, None)

    def clear_cache(self) -> None:
        self._cache.clear()

    # ---- State hashing (for cache) ------------------------------------------

    @staticmethod
    def _object_state_hash(obj: VectorObject) -> str:
        """Compute a hash of the object's visual state for cache comparison."""
        h = hashlib.md5(usedforsecurity=False)
        # Transform
        xf = obj.transform
        h.update(f"T{xf.a:.8f},{xf.b:.8f},{xf.c:.8f},{xf.d:.8f},{xf.tx:.8f},{xf.ty:.8f}".encode())
        # Style summary
        s = obj.style
        for i, f in enumerate(s.fills):
            h.update(f"F{i}{f.visible}{f.opacity:.4f}".encode())
            if isinstance(f.paint, SolidPaint):
                h.update(f"S{f.paint.color}".encode())
        for i, st in enumerate(s.strokes):
            h.update(f"K{i}{st.visible}{st.opacity:.4f}{st.width:.4f}{st.cap.value}{st.join.value}".encode())
            if isinstance(st.paint, SolidPaint):
                h.update(f"S{st.paint.color}".encode())
        # Path geometry (hash node positions)
        path = obj.effective_path()
        for sp in path.sub_paths:
            for n in sp.nodes:
                h.update(f"N{n.position.x:.6f},{n.position.y:.6f}".encode())
                if n.in_handle:
                    h.update(f"I{n.in_handle.x:.6f},{n.in_handle.y:.6f}".encode())
                if n.out_handle:
                    h.update(f"O{n.out_handle.x:.6f},{n.out_handle.y:.6f}".encode())
            h.update(f"C{sp.closed}".encode())
        return h.hexdigest()

    # ---- Internal -----------------------------------------------------------

    def _render_object(
        self, buf: np.ndarray, obj: VectorObject, zoom: float,
        origin: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        path = obj.transformed_path()
        ox, oy = origin
        if ox != 0.0 or oy != 0.0:
            path = path.transformed(AffineTransform.translation(-ox, -oy))
        style = obj.style
        h, w = buf.shape[:2]
        tolerance = max(0.25, 0.5 / zoom)

        for fill in style.fills:
            if not fill.visible or fill.opacity <= 0:
                continue
            self._render_fill(buf, path, fill, w, h, tolerance)

        for stroke in style.strokes:
            if not stroke.visible or stroke.opacity <= 0 or stroke.width <= 0:
                continue
            self._render_stroke(buf, path, stroke, w, h, tolerance)

    # ---- Fill ---------------------------------------------------------------

    def _render_fill(
        self, buf: np.ndarray, path: VectorPath, fill: VectorFill,
        w: int, h: int, tolerance: float,
    ) -> None:
        polys = path.flatten(tolerance)
        if not polys:
            return
        bb = path.bbox()
        y0 = max(0, int(math.floor(bb.min_pt.y)))
        y1 = min(h, int(math.ceil(bb.max_pt.y)) + 1)
        x0 = max(0, int(math.floor(bb.min_pt.x)))
        x1 = min(w, int(math.ceil(bb.max_pt.x)) + 1)
        if y0 >= y1 or x0 >= x1:
            return
        coverage = _scanline_coverage(polys, x0, y0, x1, y1, path.fill_rule)
        _apply_paint(buf, coverage, fill, x0, y0, x1, y1, bb)

    # ---- Stroke -------------------------------------------------------------

    def _render_stroke(
        self, buf: np.ndarray, path: VectorPath, stroke: VectorStroke,
        w: int, h: int, tolerance: float,
    ) -> None:
        half_w = stroke.width * 0.5
        if half_w < 0.1:
            return
        stroke_polys = _expand_stroke(path, stroke, tolerance)
        if not stroke_polys:
            return
        all_x: list[float] = []
        all_y: list[float] = []
        for poly in stroke_polys:
            for p in poly:
                all_x.append(p.x)
                all_y.append(p.y)
        if not all_x:
            return
        bb = BBox(Vec2(min(all_x), min(all_y)), Vec2(max(all_x), max(all_y)))
        y0 = max(0, int(math.floor(bb.min_pt.y)))
        y1 = min(h, int(math.ceil(bb.max_pt.y)) + 1)
        x0 = max(0, int(math.floor(bb.min_pt.x)))
        x1 = min(w, int(math.ceil(bb.max_pt.x)) + 1)
        if y0 >= y1 or x0 >= x1:
            return
        coverage = _scanline_coverage(stroke_polys, x0, y0, x1, y1, FillRule.NON_ZERO)
        fill_proxy = VectorFill(paint=stroke.paint, opacity=stroke.opacity)
        _apply_paint(buf, coverage, fill_proxy, x0, y0, x1, y1, bb)


# =========================================================================
#  Vectorised scanline coverage — numpy inner loops
# =========================================================================

def _build_edge_array(polys: list[list[Vec2]]) -> np.ndarray | None:
    """Build a (N, 5) float64 array: [y_min, y_max, x_at_ymin, dx_per_dy, direction]."""
    segs: list[tuple[float, float, float, float, float]] = []
    for poly in polys:
        n = len(poly)
        if n < 2:
            continue
        for i in range(n):
            j = (i + 1) % n
            ay, by = poly[i].y, poly[j].y
            if abs(ay - by) < 1e-6:
                continue
            ax, bx = poly[i].x, poly[j].x
            d = 1.0 if ay < by else -1.0
            if ay > by:
                ay, by = by, ay
                ax, bx = bx, ax
            dx = (bx - ax) / (by - ay)
            segs.append((ay, by, ax, dx, d))
    if not segs:
        return None
    return np.array(segs, dtype=np.float64)


def _scanline_coverage(
    polys: list[list[Vec2]],
    x0: int, y0: int, x1: int, y1: int,
    fill_rule: FillRule,
) -> np.ndarray:
    """Super-sampled scanline fill → (h, w) float32 coverage.

    Uses 4× super-sampling in high-quality mode, 2× in interactive mode.
    """
    cov_h = y1 - y0
    cov_w = x1 - x0
    coverage = np.zeros((cov_h, cov_w), dtype=np.float32)

    edges = _build_edge_array(polys)
    if edges is None:
        return coverage

    ss = 2 if _interactive_mode else _SS
    ss_inv = 1.0 / ss

    e_ymin = edges[:, 0]
    e_ymax = edges[:, 1]
    e_x0 = edges[:, 2]
    e_dx = edges[:, 3]
    e_dir = edges[:, 4]
    use_winding = (fill_rule == FillRule.NON_ZERO)

    for row in range(cov_h):
        y_base = float(y0 + row)

        for si in range(ss):
            y = y_base + (si + 0.5) * ss_inv

            # Vectorised active-edge test
            active = (e_ymin <= y) & (y < e_ymax)
            if not np.any(active):
                continue

            x_cross = e_x0[active] + (y - e_ymin[active]) * e_dx[active]
            order = np.argsort(x_cross)
            x_sorted = x_cross[order]

            if use_winding:
                dirs = e_dir[active][order]
                winding = 0
                fill_start = 0.0
                for k in range(len(x_sorted)):
                    prev_w = winding
                    winding += int(dirs[k])
                    if prev_w == 0 and winding != 0:
                        fill_start = x_sorted[k]
                    elif prev_w != 0 and winding == 0:
                        _add_span_to_row(coverage[row], fill_start - x0, x_sorted[k] - x0, cov_w)
            else:
                # Even-odd: fill between consecutive pairs
                for k in range(0, len(x_sorted) - 1, 2):
                    _add_span_to_row(coverage[row], x_sorted[k] - x0, x_sorted[k + 1] - x0, cov_w)

        coverage[row] *= ss_inv

    np.clip(coverage, 0.0, 1.0, out=coverage)
    return coverage


def _add_span_to_row(row: np.ndarray, xl: float, xr: float, w: int) -> None:
    """Add a horizontal fill span [xl, xr] with sub-pixel accuracy."""
    if xr <= xl or xr <= 0.0 or xl >= w:
        return
    c0 = max(0, int(math.floor(xl)))
    c1 = min(w, int(math.ceil(xr)))
    if c0 >= c1:
        return

    if c1 - c0 == 1:
        row[c0] += min(xr, float(c0 + 1)) - max(xl, float(c0))
        return

    # Left partial pixel
    row[c0] += float(c0 + 1) - max(xl, float(c0))
    # Full interior pixels
    if c0 + 1 < c1 - 1:
        row[c0 + 1: c1 - 1] += 1.0
    # Right partial pixel
    if c1 - 1 > c0:
        row[c1 - 1] += min(xr, float(c1)) - float(c1 - 1)


# =========================================================================
#  Paint application  (fully vectorised — numpy)
# =========================================================================

def _apply_paint(
    buf: np.ndarray,
    coverage: np.ndarray,
    fill: VectorFill,
    x0: int, y0: int, x1: int, y1: int,
    bb: BBox,
) -> None:
    roi = buf[y0:y1, x0:x1]
    cov = coverage[..., np.newaxis]  # (h, w, 1)

    if isinstance(fill.paint, SolidPaint):
        color = np.array(fill.paint.color, dtype=np.float32)
        color[3] *= fill.opacity
        src_a = color[3]
        if src_a < 1e-6:
            return
        src_rgb = color[:3] * src_a
        mask = cov * src_a
        inv_mask = 1.0 - mask
        roi[..., :3] = roi[..., :3] * inv_mask + src_rgb * cov
        roi[..., 3:4] = roi[..., 3:4] * inv_mask + mask
        np.clip(roi, 0.0, 1.0, out=roi)

    elif isinstance(fill.paint, GradientPaint):
        _apply_gradient(roi, coverage, fill, x0, y0, bb)


def _apply_gradient(
    roi: np.ndarray, coverage: np.ndarray, fill: VectorFill,
    x0: int, y0: int, bb: BBox,
) -> None:
    paint = fill.paint
    if not isinstance(paint, GradientPaint):
        return
    h, w = coverage.shape
    lut = paint.sample_to_array(256)

    if paint.gradient_type == GradientType.LINEAR:
        start, end = paint.start, paint.end
        dx = end.x - start.x
        dy = end.y - start.y
        length_sq = dx * dx + dy * dy
        if length_sq < 1e-12:
            return
        yy = np.arange(y0, y0 + h, dtype=np.float32)[:, np.newaxis]
        xx = np.arange(x0, x0 + w, dtype=np.float32)[np.newaxis, :]
        t = ((xx - start.x) * dx + (yy - start.y) * dy) / length_sq
        np.clip(t, 0.0, 1.0, out=t)
        indices = (t * 255).astype(np.int32)
        colors = lut[indices]
        colors[..., 3] *= fill.opacity
        cov = coverage[..., np.newaxis]
        mask = cov * colors[..., 3:4]
        inv_mask = 1.0 - mask
        roi[..., :3] = roi[..., :3] * inv_mask + colors[..., :3] * mask
        roi[..., 3:4] = roi[..., 3:4] * inv_mask + mask
        np.clip(roi, 0.0, 1.0, out=roi)

    elif paint.gradient_type == GradientType.RADIAL:
        cx, cy = paint.start.x, paint.start.y
        radius = max(paint.radius, 1e-6)
        yy = np.arange(y0, y0 + h, dtype=np.float32)[:, np.newaxis]
        xx = np.arange(x0, x0 + w, dtype=np.float32)[np.newaxis, :]
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / radius
        np.clip(dist, 0.0, 1.0, out=dist)
        indices = (dist * 255).astype(np.int32)
        colors = lut[indices]
        colors[..., 3] *= fill.opacity
        cov = coverage[..., np.newaxis]
        mask = cov * colors[..., 3:4]
        inv_mask = 1.0 - mask
        roi[..., :3] = roi[..., :3] * inv_mask + colors[..., :3] * mask
        roi[..., 3:4] = roi[..., 3:4] * inv_mask + mask
        np.clip(roi, 0.0, 1.0, out=roi)


# =========================================================================
#  Stroke expansion  (offset polylines with proper joins)
# =========================================================================

def _expand_stroke(
    path: VectorPath,
    stroke: VectorStroke,
    tolerance: float,
) -> list[list[Vec2]]:
    """Expand a vector path into filled polygon outlines representing the stroke.

    Properly handles miter, round, and bevel joins at corners, as well as
    butt, round, and square end caps for open sub-paths.  For closed
    sub-paths, the join between the last and first segment is also applied.
    """
    half_w = stroke.width * 0.5
    if half_w < 0.1:
        return []
    join = stroke.join
    miter_limit = stroke.miter_limit
    result: list[list[Vec2]] = []

    for sp in path.sub_paths:
        pts = sp.flatten(tolerance)
        # Remove consecutive duplicate points
        clean: list[Vec2] = [pts[0]] if pts else []
        for i in range(1, len(pts)):
            if pts[i].distance_sq_to(clean[-1]) > 1e-12:
                clean.append(pts[i])
        pts = clean
        if len(pts) < 2:
            continue

        # Compute per-segment normals (left-side offset direction)
        seg_count = len(pts) - 1
        normals: list[tuple[float, float]] = []
        for i in range(seg_count):
            dx = pts[i + 1].x - pts[i].x
            dy = pts[i + 1].y - pts[i].y
            ln = math.hypot(dx, dy)
            if ln < 1e-12:
                normals.append((0.0, 1.0))
            else:
                normals.append((-dy / ln, dx / ln))

        left: list[Vec2] = []
        right: list[Vec2] = []

        # First point offset (start of first segment)
        nx0, ny0 = normals[0]
        left.append(Vec2(pts[0].x + nx0 * half_w, pts[0].y + ny0 * half_w))
        right.append(Vec2(pts[0].x - nx0 * half_w, pts[0].y - ny0 * half_w))

        # Interior vertices — apply join
        for i in range(1, seg_count):
            nx_prev, ny_prev = normals[i - 1]
            nx_cur, ny_cur = normals[i]
            pt = pts[i]

            _apply_join_to_side(left, pt, nx_prev, ny_prev, nx_cur, ny_cur,
                                half_w, join, miter_limit, side=1.0)
            _apply_join_to_side(right, pt, nx_prev, ny_prev, nx_cur, ny_cur,
                                half_w, join, miter_limit, side=-1.0)

        # Last point offset (end of last segment)
        nx_last, ny_last = normals[-1]
        left.append(Vec2(pts[-1].x + nx_last * half_w, pts[-1].y + ny_last * half_w))
        right.append(Vec2(pts[-1].x - nx_last * half_w, pts[-1].y - ny_last * half_w))

        if not left or not right:
            continue

        if sp.closed and seg_count >= 2:
            # Apply closing join between last segment and first segment
            nx_prev, ny_prev = normals[-1]
            nx_cur, ny_cur = normals[0]
            pt = pts[0]

            # Replace the first left/right entries with join result
            close_left: list[Vec2] = []
            close_right: list[Vec2] = []
            _apply_join_to_side(close_left, pt, nx_prev, ny_prev, nx_cur, ny_cur,
                                half_w, join, miter_limit, side=1.0)
            _apply_join_to_side(close_right, pt, nx_prev, ny_prev, nx_cur, ny_cur,
                                half_w, join, miter_limit, side=-1.0)

            # Remove duplicated start/end (the first and last points)
            if left:
                left.pop(0)
            if right:
                right.pop(0)
            # Build closed outline: join at start → left side → join at end (same as start)
            left = close_left + left
            right = close_right + right
            result.append(left + list(reversed(right)))
        else:
            # Open path: apply end caps
            outline: list[Vec2] = list(left)
            outline.extend(_make_cap(pts[-1], left[-1], right[-1], stroke.cap))
            outline.extend(reversed(right))
            outline.extend(_make_cap(pts[0], right[0], left[0], stroke.cap))
            result.append(outline)
    return result


def _apply_join_to_side(
    out: list[Vec2],
    pt: Vec2,
    nx_prev: float, ny_prev: float,
    nx_cur: float, ny_cur: float,
    half_w: float,
    join: StrokeJoin,
    miter_limit: float,
    side: float,
) -> None:
    """Compute join geometry for one side (left=+1, right=-1) at a vertex.

    Appends the resulting points to *out*.
    """
    s = side
    # Offset points from the two adjacent segments at this vertex
    prev_pt = Vec2(pt.x + nx_prev * half_w * s, pt.y + ny_prev * half_w * s)
    cur_pt = Vec2(pt.x + nx_cur * half_w * s, pt.y + ny_cur * half_w * s)

    # Cross product determines turn direction
    cross = nx_prev * ny_cur - ny_prev * nx_cur

    # If normals are nearly parallel, just use one point
    if abs(cross) < 1e-6:
        out.append(cur_pt)
        return

    # Determine if this is the outer or inner side of the turn
    is_outer = (cross * s) > 0

    # Tangent direction of each segment (perpendicular to normal)
    t_prev = Vec2(ny_prev, -nx_prev)
    t_cur = Vec2(ny_cur, -nx_cur)

    if not is_outer:
        # Inner side: compute intersection of the two offset lines
        inter = _line_intersection_dir(prev_pt, t_prev, cur_pt, t_cur)
        if inter is not None:
            out.append(inter)
        else:
            out.append(cur_pt)
        return

    # Outer side: apply the requested join type
    if join == StrokeJoin.BEVEL:
        out.append(prev_pt)
        out.append(cur_pt)

    elif join == StrokeJoin.MITER:
        inter = _line_intersection_dir(prev_pt, t_prev, cur_pt, t_cur)
        if inter is not None:
            miter_dist = inter.distance_to(pt)
            if miter_dist <= half_w * miter_limit:
                out.append(inter)
            else:
                # Exceeds miter limit — fall back to bevel
                out.append(prev_pt)
                out.append(cur_pt)
        else:
            out.append(prev_pt)
            out.append(cur_pt)

    elif join == StrokeJoin.ROUND:
        out.append(prev_pt)
        start_angle = math.atan2(prev_pt.y - pt.y, prev_pt.x - pt.x)
        end_angle = math.atan2(cur_pt.y - pt.y, cur_pt.x - pt.x)
        diff = end_angle - start_angle
        if diff > math.pi:
            diff -= 2 * math.pi
        elif diff < -math.pi:
            diff += 2 * math.pi
        steps = max(3, int(abs(diff) / 0.3) + 1)
        for k in range(1, steps):
            t = k / steps
            a = start_angle + diff * t
            out.append(Vec2(pt.x + half_w * math.cos(a), pt.y + half_w * math.sin(a)))
        out.append(cur_pt)

    else:
        out.append(prev_pt)
        out.append(cur_pt)


def _line_intersection_dir(
    p1: Vec2, d1: Vec2, p2: Vec2, d2: Vec2,
) -> Vec2 | None:
    """Intersect two lines given as point + direction vector."""
    det = d1.x * d2.y - d1.y * d2.x
    if abs(det) < 1e-10:
        return None
    dx = p2.x - p1.x
    dy = p2.y - p1.y
    t = (dx * d2.y - dy * d2.x) / det
    return Vec2(p1.x + t * d1.x, p1.y + t * d1.y)


def _make_cap(point: Vec2, from_pt: Vec2, to_pt: Vec2, cap: StrokeCap) -> list[Vec2]:
    if cap == StrokeCap.BUTT:
        return [from_pt, to_pt]
    elif cap == StrokeCap.SQUARE:
        dx = from_pt.x - point.x
        dy = from_pt.y - point.y
        n = Vec2(dy, -dx)
        return [Vec2(from_pt.x + n.x, from_pt.y + n.y),
                Vec2(to_pt.x + n.x, to_pt.y + n.y)]
    else:  # ROUND
        cx, cy = point.x, point.y
        r = from_pt.distance_to(point)
        if r < 1e-9:
            return [from_pt, to_pt]
        start_angle = math.atan2(from_pt.y - cy, from_pt.x - cx)
        pts: list[Vec2] = []
        steps = 8
        for i in range(steps + 1):
            t = i / steps
            angle = start_angle + math.pi * t
            pts.append(Vec2(cx + r * math.cos(angle), cy + r * math.sin(angle)))
        return pts


# =========================================================================
#  Shared tight-bbox rasterise helper
# =========================================================================

# Module-level singleton to avoid re-allocating each call
_shared_rasterizer = VectorRasterizer()

# Global flag: when False, rasterize_vector_layer_tight does nothing.
# The UI toggle in the status bar controls this.
_auto_rasterize_enabled: bool = True


def set_auto_rasterize(enabled: bool) -> None:
    """Set the global auto-rasterize flag for vector layers."""
    global _auto_rasterize_enabled
    _auto_rasterize_enabled = enabled


def get_auto_rasterize() -> bool:
    """Query the global auto-rasterize flag."""
    return _auto_rasterize_enabled


def rasterize_vector_layer_tight(
    doc: object, *, layer: object | None = None, force: bool = False,
) -> None:
    """Rasterize vector data into a tight-bbox pixel buffer.

    When *layer* is given, rasterize that specific layer.  Otherwise fall
    back to ``doc.layers.active_layer``.

    If auto-rasterize is disabled and *force* is False, this is a no-op.
    Pass ``force=True`` to bypass the toggle (e.g. on final release or
    explicit user action).

    Instead of allocating a full canvas-size array, this computes the union
    bounding box of all visible ``VectorObject``s and creates a buffer that
    covers *only* that region.  The layer's ``position`` is set so the
    compositor places the small buffer at the correct location.
    """
    if not force and not _auto_rasterize_enabled:
        return

    if layer is None:
        stack = getattr(doc, "layers", None)
        if stack is not None:
            layer = stack.active_layer
    if layer is None:
        return
    vl = getattr(layer, "_vector_data", None)
    if vl is None:
        return

    # Union bbox of all visible objects
    union = BBox.empty()
    for obj in vl.objects:
        if obj.visible:
            union = union.union(obj.bbox())

    if union.is_empty:
        layer._pixels = np.zeros((1, 1, 4), dtype=np.float32)
        layer.position = (0, 0)
        layer._pixels_dirty = False
        return

    # Integer pixel bounds with 2 px padding (anti-aliasing headroom)
    x0 = max(0, int(math.floor(union.min_pt.x)) - 2)
    y0 = max(0, int(math.floor(union.min_pt.y)) - 2)
    x1 = int(math.ceil(union.max_pt.x)) + 3
    y1 = int(math.ceil(union.max_pt.y)) + 3
    bw = max(1, x1 - x0)
    bh = max(1, y1 - y0)

    pixels = _shared_rasterizer.rasterize_layer(
        vl, bw, bh, origin=(float(x0), float(y0))
    )
    layer._pixels = pixels
    layer.position = (x0, y0)
    layer._pixels_dirty = False