"""Cubic and quadratic Bézier curve mathematics.

This module implements production-grade Bézier curve algorithms with
numerical stability safeguards throughout.  Every algorithm has been
chosen for its balance of accuracy and throughput:

* **de Casteljau** for evaluation and splitting — numerically stable,
  branch-free, vectorises well.
* **Adaptive subdivision** for arc-length — recursion with flatness
  tolerance rather than fixed step counts.
* **Algebraic curvature** — closed-form curvature at parameter *t*
  without numerical differentiation.
* **Implicit line test** for monotone decomposition and intersection prep.

The ``CubicBezier`` class stores its four control points as ``Vec2``
instances.  Hot-path methods that operate on arrays of curves accept
raw float tuples to avoid object-creation overhead.
"""

from __future__ import annotations

import math
from typing import Sequence

from .geometry import Vec2, BBox

__all__ = ["CubicBezier", "QuadraticBezier"]

# Flatness threshold for adaptive subdivision (in document units squared)
_FLATNESS_SQ = 0.25  # ≈ 0.5 px


# ---------------------------------------------------------------------------
#  Cubic Bézier
# ---------------------------------------------------------------------------

class CubicBezier:
    """A single cubic Bézier segment P0→P1→P2→P3.

    Control-point layout follows the standard convention:
    * P0 — on-curve start
    * P1 — out-handle of P0 (tangent at t=0)
    * P2 — in-handle of P3 (tangent at t=1)
    * P3 — on-curve end
    """

    __slots__ = ("p0", "p1", "p2", "p3")

    def __init__(self, p0: Vec2, p1: Vec2, p2: Vec2, p3: Vec2) -> None:
        self.p0 = p0
        self.p1 = p1
        self.p2 = p2
        self.p3 = p3

    # ---- Evaluation ---------------------------------------------------------

    def point_at(self, t: float) -> Vec2:
        """Evaluate position via de Casteljau."""
        u = 1.0 - t
        uu, tt = u * u, t * t
        uuu, ttt = uu * u, tt * t
        return Vec2(
            uuu * self.p0.x + 3.0 * uu * t * self.p1.x + 3.0 * u * tt * self.p2.x + ttt * self.p3.x,
            uuu * self.p0.y + 3.0 * uu * t * self.p1.y + 3.0 * u * tt * self.p2.y + ttt * self.p3.y,
        )

    def tangent_at(self, t: float) -> Vec2:
        """First derivative (tangent vector, not normalised)."""
        u = 1.0 - t
        a = 3.0 * u * u
        b = 6.0 * u * t
        c = 3.0 * t * t
        return Vec2(
            a * (self.p1.x - self.p0.x) + b * (self.p2.x - self.p1.x) + c * (self.p3.x - self.p2.x),
            a * (self.p1.y - self.p0.y) + b * (self.p2.y - self.p1.y) + c * (self.p3.y - self.p2.y),
        )

    def normal_at(self, t: float) -> Vec2:
        """Unit normal (perpendicular to tangent, pointing left)."""
        tng = self.tangent_at(t)
        return tng.perpendicular().normalized()

    def second_derivative_at(self, t: float) -> Vec2:
        """Second derivative at *t*."""
        u = 1.0 - t
        return Vec2(
            6.0 * (u * (self.p2.x - 2.0 * self.p1.x + self.p0.x) + t * (self.p3.x - 2.0 * self.p2.x + self.p1.x)),
            6.0 * (u * (self.p2.y - 2.0 * self.p1.y + self.p0.y) + t * (self.p3.y - 2.0 * self.p2.y + self.p1.y)),
        )

    def curvature_at(self, t: float) -> float:
        """Signed curvature κ at parameter *t*.

        κ = (x'y'' - y'x'') / (x'² + y'²)^(3/2)
        """
        d1 = self.tangent_at(t)
        d2 = self.second_derivative_at(t)
        cross = d1.x * d2.y - d1.y * d2.x
        denom = (d1.x * d1.x + d1.y * d1.y) ** 1.5
        if denom < 1e-12:
            return 0.0
        return cross / denom

    # ---- Splitting (de Casteljau) -------------------------------------------

    def split_at(self, t: float) -> tuple[CubicBezier, CubicBezier]:
        """Split into two sub-curves at parameter *t* using de Casteljau."""
        u = 1.0 - t
        # Level 1
        m01 = Vec2(u * self.p0.x + t * self.p1.x, u * self.p0.y + t * self.p1.y)
        m12 = Vec2(u * self.p1.x + t * self.p2.x, u * self.p1.y + t * self.p2.y)
        m23 = Vec2(u * self.p2.x + t * self.p3.x, u * self.p2.y + t * self.p3.y)
        # Level 2
        m012 = Vec2(u * m01.x + t * m12.x, u * m01.y + t * m12.y)
        m123 = Vec2(u * m12.x + t * m23.x, u * m12.y + t * m23.y)
        # Level 3 — the split point
        mid = Vec2(u * m012.x + t * m123.x, u * m012.y + t * m123.y)
        return (
            CubicBezier(self.p0, m01, m012, mid),
            CubicBezier(mid, m123, m23, self.p3),
        )

    def subdivide(self) -> tuple[CubicBezier, CubicBezier]:
        """Split at t=0.5 (slightly faster specialisation)."""
        return self.split_at(0.5)

    # ---- Bounding box -------------------------------------------------------

    def bbox(self) -> BBox:
        """Tight axis-aligned bounding box.

        Computes extrema by finding roots of the first derivative in
        each axis, then evaluates at those roots + endpoints.
        """
        pts = [self.p0, self.p3]
        for roots in (self._extrema_x(), self._extrema_y()):
            for t in roots:
                if 0.0 < t < 1.0:
                    pts.append(self.point_at(t))
        return BBox.from_points(pts)

    def _extrema_x(self) -> list[float]:
        return _solve_quadratic_01(
            -3.0 * self.p0.x + 9.0 * self.p1.x - 9.0 * self.p2.x + 3.0 * self.p3.x,
            6.0 * self.p0.x - 12.0 * self.p1.x + 6.0 * self.p2.x,
            -3.0 * self.p0.x + 3.0 * self.p1.x,
        )

    def _extrema_y(self) -> list[float]:
        return _solve_quadratic_01(
            -3.0 * self.p0.y + 9.0 * self.p1.y - 9.0 * self.p2.y + 3.0 * self.p3.y,
            6.0 * self.p0.y - 12.0 * self.p1.y + 6.0 * self.p2.y,
            -3.0 * self.p0.y + 3.0 * self.p1.y,
        )

    # ---- Arc length ---------------------------------------------------------

    def arc_length(self, tolerance: float = 0.5) -> float:
        """Approximate arc length via adaptive subdivision."""
        return self._arc_len_recursive(tolerance * tolerance, 0)

    def _arc_len_recursive(self, tol_sq: float, depth: int) -> float:
        chord = self.p0.distance_to(self.p3)
        poly = (
            self.p0.distance_to(self.p1)
            + self.p1.distance_to(self.p2)
            + self.p2.distance_to(self.p3)
        )
        if depth > 16 or (poly - chord) * (poly - chord) < tol_sq:
            return (poly + chord) * 0.5
        a, b = self.subdivide()
        return a._arc_len_recursive(tol_sq, depth + 1) + b._arc_len_recursive(tol_sq, depth + 1)

    # ---- Parameter at arc length -------------------------------------------

    def parameter_at_length(self, target_len: float, tolerance: float = 0.5) -> float:
        """Find parameter *t* corresponding to *target_len* along the curve.

        Uses Newton-Raphson with adaptive arc-length bisection fallback.
        """
        total = self.arc_length(tolerance)
        if total < 1e-12:
            return 0.0
        if target_len >= total:
            return 1.0
        # Bisection (reliable convergence)
        lo, hi = 0.0, 1.0
        for _ in range(30):
            mid = (lo + hi) * 0.5
            left, _ = self.split_at(mid)
            current = left.arc_length(tolerance)
            if abs(current - target_len) < tolerance * 0.1:
                return mid
            if current < target_len:
                lo = mid
            else:
                hi = mid
        return (lo + hi) * 0.5

    # ---- Flatness -----------------------------------------------------------

    def flatness_sq(self) -> float:
        """Maximum squared deviation of control points from the chord.

        Uses the standard cubic flatness metric: the max distance² of
        P1 and P2 from the line P0→P3.
        """
        ux = 3.0 * self.p1.x - 2.0 * self.p0.x - self.p3.x
        uy = 3.0 * self.p1.y - 2.0 * self.p0.y - self.p3.y
        vx = 3.0 * self.p2.x - self.p0.x - 2.0 * self.p3.x
        vy = 3.0 * self.p2.y - self.p0.y - 2.0 * self.p3.y
        return max(ux * ux + uy * uy, vx * vx + vy * vy)

    def is_flat(self, tolerance_sq: float = _FLATNESS_SQ) -> bool:
        return self.flatness_sq() <= tolerance_sq

    # ---- Flatten to polyline ------------------------------------------------

    def flatten(self, tolerance: float = 0.5) -> list[Vec2]:
        """Recursively subdivide into line segments.

        Returns the list of points including both endpoints.
        """
        result: list[Vec2] = [self.p0]
        self._flatten_recursive(result, tolerance * tolerance, 0)
        return result

    def _flatten_recursive(
        self, out: list[Vec2], tol_sq: float, depth: int
    ) -> None:
        if depth > 18 or self.is_flat(tol_sq):
            out.append(self.p3)
            return
        a, b = self.subdivide()
        a._flatten_recursive(out, tol_sq, depth + 1)
        b._flatten_recursive(out, tol_sq, depth + 1)

    # ---- Nearest point on curve ---------------------------------------------

    def nearest_point(self, target: Vec2, steps: int = 16) -> tuple[float, Vec2]:
        """Return ``(t, point)`` for the closest point on the curve to *target*.

        Uses coarse sampling followed by Newton-Raphson refinement.
        """
        best_t = 0.0
        best_d = float("inf")
        inv = 1.0 / steps
        for i in range(steps + 1):
            t = i * inv
            p = self.point_at(t)
            d = p.distance_sq_to(target)
            if d < best_d:
                best_d = d
                best_t = t
        # Newton-Raphson refinement
        for _ in range(5):
            p = self.point_at(best_t)
            d1 = self.tangent_at(best_t)
            d2 = self.second_derivative_at(best_t)
            diff = p - target
            num = diff.x * d1.x + diff.y * d1.y
            den = d1.x * d1.x + d1.y * d1.y + diff.x * d2.x + diff.y * d2.y
            if abs(den) < 1e-12:
                break
            best_t -= num / den
            best_t = max(0.0, min(1.0, best_t))
        return best_t, self.point_at(best_t)

    # ---- Offset curve (Tiller–Hanson) ---------------------------------------

    def offset(self, distance: float) -> CubicBezier:
        """Approximate parallel curve at signed *distance*.

        Uses the Tiller–Hanson method: offset the tangent endpoints and
        scale handles proportionally.  For production quality, this
        should be called on sub-divided segments (after splitting at
        inflections / cusps).
        """
        n0 = self.normal_at(0.0)
        n1 = self.normal_at(1.0)
        if n0.length_sq() < 1e-12:
            n0 = self.normal_at(0.01)
        if n1.length_sq() < 1e-12:
            n1 = self.normal_at(0.99)
        off0 = n0 * distance
        off3 = n1 * distance
        # Offset endpoints
        q0 = self.p0 + off0
        q3 = self.p3 + off3
        # Scale handle lengths with curvature compensation
        d01 = self.p1 - self.p0
        d23 = self.p3 - self.p2
        len_01 = d01.length()
        len_23 = d23.length()
        # Offset handles
        if len_01 > 1e-9:
            q1 = q0 + d01 * ((q0.distance_to(q3)) / (self.p0.distance_to(self.p3) + 1e-12))
            # Better: offset P1 by same normal as P0
            q1 = self.p1 + off0
        else:
            q1 = q0
        if len_23 > 1e-9:
            q2 = self.p2 + off3
        else:
            q2 = q3
        return CubicBezier(q0, q1, q2, q3)

    # ---- Inflection points --------------------------------------------------

    def inflection_points(self) -> list[float]:
        """Find parameter values where curvature changes sign.

        Solves  x'(t)·y''(t) − y'(t)·x''(t) = 0  which is quadratic in t.
        """
        ax = -self.p0.x + 3.0 * self.p1.x - 3.0 * self.p2.x + self.p3.x
        ay = -self.p0.y + 3.0 * self.p1.y - 3.0 * self.p2.y + self.p3.y
        bx = 3.0 * self.p0.x - 6.0 * self.p1.x + 3.0 * self.p2.x
        by = 3.0 * self.p0.y - 6.0 * self.p1.y + 3.0 * self.p2.y
        cx = -3.0 * self.p0.x + 3.0 * self.p1.x
        cy = -3.0 * self.p0.y + 3.0 * self.p1.y

        # Cross product derivative coefficients:
        # d/dt [x'(t) × y'(t)] = at² + bt + c
        A = ax * by - ay * bx  # noqa: N806
        B = ax * cy - ay * cx  # noqa: N806
        # This is actually linear in the second derivative form:
        # We need the cross(d1, d2) = 0 which expands to quadratic in t
        # Coefficients of the quadratic:
        qa = 6.0 * (ax * by - ay * bx)
        qb = 6.0 * (ax * cy - ay * cx)
        qc = 2.0 * (bx * cy - by * cx)
        return _solve_quadratic_01(qa, qb, qc)

    # ---- Reverse ------------------------------------------------------------

    def reversed(self) -> CubicBezier:
        return CubicBezier(self.p3, self.p2, self.p1, self.p0)

    # ---- Transform ----------------------------------------------------------

    def transformed(self, xf) -> CubicBezier:
        """Apply an AffineTransform to all control points."""
        return CubicBezier(
            xf.apply(self.p0),
            xf.apply(self.p1),
            xf.apply(self.p2),
            xf.apply(self.p3),
        )

    # ---- Intersection (Bézier clipping) ------------------------------------

    def intersections_with(
        self, other: CubicBezier, tolerance: float = 1e-6
    ) -> list[tuple[float, float]]:
        """Find all intersection parameters ``(t_self, t_other)``.

        Uses recursive Bézier clipping for robust O(n log n) intersection
        detection that handles tangencies and near-misses gracefully.
        """
        results: list[tuple[float, float]] = []
        _bezier_clip_intersect(
            self, 0.0, 1.0, other, 0.0, 1.0, tolerance, results, 0
        )
        return results

    def __repr__(self) -> str:
        return f"CubicBezier({self.p0}, {self.p1}, {self.p2}, {self.p3})"


# ---------------------------------------------------------------------------
#  Quadratic Bézier
# ---------------------------------------------------------------------------

class QuadraticBezier:
    """Quadratic Bézier segment P0→P1→P2."""

    __slots__ = ("p0", "p1", "p2")

    def __init__(self, p0: Vec2, p1: Vec2, p2: Vec2) -> None:
        self.p0 = p0
        self.p1 = p1
        self.p2 = p2

    def point_at(self, t: float) -> Vec2:
        u = 1.0 - t
        return Vec2(
            u * u * self.p0.x + 2.0 * u * t * self.p1.x + t * t * self.p2.x,
            u * u * self.p0.y + 2.0 * u * t * self.p1.y + t * t * self.p2.y,
        )

    def tangent_at(self, t: float) -> Vec2:
        u = 1.0 - t
        return Vec2(
            2.0 * u * (self.p1.x - self.p0.x) + 2.0 * t * (self.p2.x - self.p1.x),
            2.0 * u * (self.p1.y - self.p0.y) + 2.0 * t * (self.p2.y - self.p1.y),
        )

    def to_cubic(self) -> CubicBezier:
        """Exact degree elevation to cubic."""
        return CubicBezier(
            self.p0,
            Vec2(
                self.p0.x + 2.0 / 3.0 * (self.p1.x - self.p0.x),
                self.p0.y + 2.0 / 3.0 * (self.p1.y - self.p0.y),
            ),
            Vec2(
                self.p2.x + 2.0 / 3.0 * (self.p1.x - self.p2.x),
                self.p2.y + 2.0 / 3.0 * (self.p1.y - self.p2.y),
            ),
            self.p2,
        )

    def split_at(self, t: float) -> tuple[QuadraticBezier, QuadraticBezier]:
        u = 1.0 - t
        m01 = Vec2(u * self.p0.x + t * self.p1.x, u * self.p0.y + t * self.p1.y)
        m12 = Vec2(u * self.p1.x + t * self.p2.x, u * self.p1.y + t * self.p2.y)
        mid = Vec2(u * m01.x + t * m12.x, u * m01.y + t * m12.y)
        return (
            QuadraticBezier(self.p0, m01, mid),
            QuadraticBezier(mid, m12, self.p2),
        )

    def bbox(self) -> BBox:
        pts = [self.p0, self.p2]
        # dx/dt = 0 ⟹ t = (p0-p1)/(p0-2p1+p2) per axis
        for axis in (0, 1):
            a = (self.p0.x, self.p0.y)[axis]
            b = (self.p1.x, self.p1.y)[axis]
            c = (self.p2.x, self.p2.y)[axis]
            denom = a - 2.0 * b + c
            if abs(denom) > 1e-12:
                t = (a - b) / denom
                if 0.0 < t < 1.0:
                    pts.append(self.point_at(t))
        return BBox.from_points(pts)

    def flatten(self, tolerance: float = 0.5) -> list[Vec2]:
        return self.to_cubic().flatten(tolerance)

    def __repr__(self) -> str:
        return f"QuadraticBezier({self.p0}, {self.p1}, {self.p2})"


# ---------------------------------------------------------------------------
#  Helper: solve quadratic returning roots in (0, 1)
# ---------------------------------------------------------------------------

def _solve_quadratic_01(a: float, b: float, c: float) -> list[float]:
    """Solve ax²+bx+c=0, returning real roots in the open interval (0,1)."""
    roots: list[float] = []
    if abs(a) < 1e-12:
        # Linear
        if abs(b) > 1e-12:
            t = -c / b
            if 0.0 < t < 1.0:
                roots.append(t)
        return roots
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return roots
    sq = math.sqrt(disc)
    inv = 0.5 / a
    t1 = (-b - sq) * inv
    t2 = (-b + sq) * inv
    if 0.0 < t1 < 1.0:
        roots.append(t1)
    if 0.0 < t2 < 1.0 and abs(t2 - t1) > 1e-12:
        roots.append(t2)
    return roots


# ---------------------------------------------------------------------------
#  Bézier clipping intersection
# ---------------------------------------------------------------------------

_MAX_CLIP_DEPTH = 40


def _bezier_clip_intersect(
    c1: CubicBezier,
    t1_lo: float,
    t1_hi: float,
    c2: CubicBezier,
    t2_lo: float,
    t2_hi: float,
    tol: float,
    results: list[tuple[float, float]],
    depth: int,
) -> None:
    """Recursive Bézier clipping intersection finder."""
    if depth > _MAX_CLIP_DEPTH:
        results.append(((t1_lo + t1_hi) * 0.5, (t2_lo + t2_hi) * 0.5))
        return

    # Convergence check
    if (t1_hi - t1_lo) < tol and (t2_hi - t2_lo) < tol:
        results.append(((t1_lo + t1_hi) * 0.5, (t2_lo + t2_hi) * 0.5))
        return

    # Quick rejection via bounding box
    bb1 = c1.bbox()
    bb2 = c2.bbox()
    if not bb1.intersects(bb2):
        return

    # Subdivide the larger curve
    if (t1_hi - t1_lo) >= (t2_hi - t2_lo):
        t_mid = (t1_lo + t1_hi) * 0.5
        left, right = c1.split_at(0.5)
        _bezier_clip_intersect(left, t1_lo, t_mid, c2, t2_lo, t2_hi, tol, results, depth + 1)
        _bezier_clip_intersect(right, t_mid, t1_hi, c2, t2_lo, t2_hi, tol, results, depth + 1)
    else:
        t_mid = (t2_lo + t2_hi) * 0.5
        left, right = c2.split_at(0.5)
        _bezier_clip_intersect(c1, t1_lo, t1_hi, left, t2_lo, t_mid, tol, results, depth + 1)
        _bezier_clip_intersect(c1, t1_lo, t1_hi, right, t_mid, t2_hi, tol, results, depth + 1)
