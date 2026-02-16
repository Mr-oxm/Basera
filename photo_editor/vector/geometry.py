"""Low-level 2D geometry primitives.

All types are immutable value objects backed by ``__slots__`` for minimal
memory overhead and cache-friendly layout.  ``Vec2`` stores coordinates as
Python floats (C doubles) — this avoids numpy overhead for scalar math
while remaining precise enough for sub-pixel vector work.

``AffineTransform`` encodes a 2D affine mapping as a 3×3 matrix stored in
row-major order (a, b, c, d, tx, ty).  The class exposes a fluent API for
chaining transforms and uses direct matrix multiplication (no numpy) for
speed in per-object transform stacking.
"""

from __future__ import annotations

import math
from typing import Iterator, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QTransform

__all__ = ["Vec2", "BBox", "AffineTransform"]

# ---------------------------------------------------------------------------
# 2D Vector
# ---------------------------------------------------------------------------

class Vec2:
    """Immutable 2-component vector / point.

    Uses ``__slots__`` for compact storage.  All arithmetic returns new
    instances — there is no in-place mutation.
    """

    __slots__ = ("x", "y")

    def __init__(self, x: float = 0.0, y: float = 0.0) -> None:
        object.__setattr__(self, "x", float(x))
        object.__setattr__(self, "y", float(y))

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("Vec2 is immutable")

    # ---- Arithmetic --------------------------------------------------------

    def __add__(self, other: Vec2) -> Vec2:
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vec2) -> Vec2:
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Vec2:
        return Vec2(self.x * scalar, self.y * scalar)

    def __rmul__(self, scalar: float) -> Vec2:
        return Vec2(self.x * scalar, self.y * scalar)

    def __truediv__(self, scalar: float) -> Vec2:
        inv = 1.0 / scalar
        return Vec2(self.x * inv, self.y * inv)

    def __neg__(self) -> Vec2:
        return Vec2(-self.x, -self.y)

    # ---- Comparison --------------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Vec2):
            return NotImplemented
        return self.x == other.x and self.y == other.y

    def __hash__(self) -> int:
        return hash((self.x, self.y))

    def __copy__(self) -> "Vec2":
        return self

    def __deepcopy__(self, memo: dict) -> "Vec2":
        return self

    def __repr__(self) -> str:
        return f"Vec2({self.x:.6g}, {self.y:.6g})"

    # ---- Vector operations --------------------------------------------------

    def dot(self, other: Vec2) -> float:
        return self.x * other.x + self.y * other.y

    def cross(self, other: Vec2) -> float:
        """2D cross product (z-component of the 3D cross)."""
        return self.x * other.y - self.y * other.x

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def length_sq(self) -> float:
        return self.x * self.x + self.y * self.y

    def normalized(self) -> Vec2:
        ln = self.length()
        if ln < 1e-12:
            return Vec2(0.0, 0.0)
        return self / ln

    def perpendicular(self) -> Vec2:
        """Counter-clockwise 90° rotation."""
        return Vec2(-self.y, self.x)

    def rotate(self, angle_rad: float) -> Vec2:
        c, s = math.cos(angle_rad), math.sin(angle_rad)
        return Vec2(self.x * c - self.y * s, self.x * s + self.y * c)

    def lerp(self, other: Vec2, t: float) -> Vec2:
        return Vec2(
            self.x + (other.x - self.x) * t,
            self.y + (other.y - self.y) * t,
        )

    def distance_to(self, other: Vec2) -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def distance_sq_to(self, other: Vec2) -> float:
        dx = self.x - other.x
        dy = self.y - other.y
        return dx * dx + dy * dy

    def angle_to(self, other: Vec2) -> float:
        """Angle in radians from *self* to *other*."""
        return math.atan2(other.y - self.y, other.x - self.x)

    def reflect(self, normal: Vec2) -> Vec2:
        d = 2.0 * self.dot(normal)
        return Vec2(self.x - d * normal.x, self.y - d * normal.y)

    def approx_eq(self, other: Vec2, eps: float = 1e-9) -> bool:
        return abs(self.x - other.x) < eps and abs(self.y - other.y) < eps

    def to_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)

    def to_qpoint(self) -> "QPointF":
        """Convert to PySide6 QPointF."""
        from PySide6.QtCore import QPointF
        return QPointF(self.x, self.y)

    @staticmethod
    def from_tuple(t: tuple[float, float]) -> Vec2:
        return Vec2(t[0], t[1])

    @staticmethod
    def from_qpoint(p: "QPointF") -> Vec2:
        return Vec2(p.x(), p.y())


# ---------------------------------------------------------------------------
# Axis-Aligned Bounding Box
# ---------------------------------------------------------------------------

class BBox:
    """Axis-aligned bounding box (min/max representation).

    Invariant: ``min_pt.x <= max_pt.x`` and ``min_pt.y <= max_pt.y`` for
    non-empty boxes.  An *empty* box has ``min > max`` on at least one axis.
    """

    __slots__ = ("min_pt", "max_pt")

    def __init__(self, min_pt: Vec2, max_pt: Vec2) -> None:
        object.__setattr__(self, "min_pt", min_pt)
        object.__setattr__(self, "max_pt", max_pt)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("BBox is immutable")

    @staticmethod
    def empty() -> BBox:
        return BBox(Vec2(math.inf, math.inf), Vec2(-math.inf, -math.inf))

    @staticmethod
    def from_points(pts: Sequence[Vec2]) -> BBox:
        if not pts:
            return BBox.empty()
        xs = [p.x for p in pts]
        ys = [p.y for p in pts]
        return BBox(Vec2(min(xs), min(ys)), Vec2(max(xs), max(ys)))

    @staticmethod
    def from_rect(x: float, y: float, w: float, h: float) -> BBox:
        return BBox(Vec2(x, y), Vec2(x + w, y + h))

    # ---- Properties ---------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        return self.min_pt.x > self.max_pt.x or self.min_pt.y > self.max_pt.y

    @property
    def width(self) -> float:
        return max(0.0, self.max_pt.x - self.min_pt.x)

    @property
    def height(self) -> float:
        return max(0.0, self.max_pt.y - self.min_pt.y)

    @property
    def center(self) -> Vec2:
        return Vec2(
            (self.min_pt.x + self.max_pt.x) * 0.5,
            (self.min_pt.y + self.max_pt.y) * 0.5,
        )

    @property
    def area(self) -> float:
        return self.width * self.height

    # ---- Queries ------------------------------------------------------------

    def contains_point(self, p: Vec2) -> bool:
        return (
            self.min_pt.x <= p.x <= self.max_pt.x
            and self.min_pt.y <= p.y <= self.max_pt.y
        )

    def contains_bbox(self, other: BBox) -> bool:
        return (
            self.min_pt.x <= other.min_pt.x
            and self.min_pt.y <= other.min_pt.y
            and self.max_pt.x >= other.max_pt.x
            and self.max_pt.y >= other.max_pt.y
        )

    def intersects(self, other: BBox) -> bool:
        return not (
            self.max_pt.x < other.min_pt.x
            or other.max_pt.x < self.min_pt.x
            or self.max_pt.y < other.min_pt.y
            or other.max_pt.y < self.min_pt.y
        )

    def intersection(self, other: BBox) -> BBox:
        return BBox(
            Vec2(max(self.min_pt.x, other.min_pt.x), max(self.min_pt.y, other.min_pt.y)),
            Vec2(min(self.max_pt.x, other.max_pt.x), min(self.max_pt.y, other.max_pt.y)),
        )

    def union(self, other: BBox) -> BBox:
        if self.is_empty:
            return other
        if other.is_empty:
            return self
        return BBox(
            Vec2(min(self.min_pt.x, other.min_pt.x), min(self.min_pt.y, other.min_pt.y)),
            Vec2(max(self.max_pt.x, other.max_pt.x), max(self.max_pt.y, other.max_pt.y)),
        )

    def expanded(self, margin: float) -> BBox:
        return BBox(
            Vec2(self.min_pt.x - margin, self.min_pt.y - margin),
            Vec2(self.max_pt.x + margin, self.max_pt.y + margin),
        )

    def transformed(self, xf: AffineTransform) -> BBox:
        """Return the AABB of this box after applying *xf*."""
        corners = [
            xf.apply(self.min_pt),
            xf.apply(Vec2(self.max_pt.x, self.min_pt.y)),
            xf.apply(self.max_pt),
            xf.apply(Vec2(self.min_pt.x, self.max_pt.y)),
        ]
        return BBox.from_points(corners)

    def __repr__(self) -> str:
        return f"BBox({self.min_pt}, {self.max_pt})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BBox):
            return NotImplemented
        return self.min_pt == other.min_pt and self.max_pt == other.max_pt

    def __hash__(self) -> int:
        return hash((self.min_pt, self.max_pt))

    def __copy__(self) -> "BBox":
        return self

    def __deepcopy__(self, memo: dict) -> "BBox":
        return self


# ---------------------------------------------------------------------------
# 2D Affine Transform
# ---------------------------------------------------------------------------

class AffineTransform:
    """2D affine transform stored as a 3×3 matrix in row-major order.

    ::

        | a  b  tx |     | m00  m01  m02 |
        | c  d  ty |  =  | m10  m11  m12 |
        | 0  0  1  |     |  0    0    1  |

    Provides a fluent API: ``xf.translate(10, 0).rotate(0.5).scale(2, 2)``
    """

    __slots__ = ("a", "b", "c", "d", "tx", "ty")

    def __init__(
        self,
        a: float = 1.0,
        b: float = 0.0,
        c: float = 0.0,
        d: float = 1.0,
        tx: float = 0.0,
        ty: float = 0.0,
    ) -> None:
        object.__setattr__(self, "a", a)
        object.__setattr__(self, "b", b)
        object.__setattr__(self, "c", c)
        object.__setattr__(self, "d", d)
        object.__setattr__(self, "tx", tx)
        object.__setattr__(self, "ty", ty)

    def __setattr__(self, _n: str, _v: object) -> None:
        raise AttributeError("AffineTransform is immutable")

    # ---- Factories ----------------------------------------------------------

    @staticmethod
    def identity() -> AffineTransform:
        return AffineTransform()

    @staticmethod
    def translation(dx: float, dy: float) -> AffineTransform:
        return AffineTransform(tx=dx, ty=dy)

    @staticmethod
    def scaling(sx: float, sy: float | None = None) -> AffineTransform:
        if sy is None:
            sy = sx
        return AffineTransform(a=sx, d=sy)

    @staticmethod
    def rotation(angle_rad: float) -> AffineTransform:
        co, si = math.cos(angle_rad), math.sin(angle_rad)
        return AffineTransform(a=co, b=-si, c=si, d=co)

    @staticmethod
    def rotation_around(angle_rad: float, center: Vec2) -> AffineTransform:
        return (
            AffineTransform.translation(center.x, center.y)
            .concat(AffineTransform.rotation(angle_rad))
            .concat(AffineTransform.translation(-center.x, -center.y))
        )

    @staticmethod
    def skewing(sx_rad: float, sy_rad: float) -> AffineTransform:
        return AffineTransform(b=math.tan(sx_rad), c=math.tan(sy_rad))

    # ---- Operations ---------------------------------------------------------

    def concat(self, other: AffineTransform) -> AffineTransform:
        """Return ``self @ other`` (self applied AFTER other)."""
        return AffineTransform(
            a=self.a * other.a + self.b * other.c,
            b=self.a * other.b + self.b * other.d,
            c=self.c * other.a + self.d * other.c,
            d=self.c * other.b + self.d * other.d,
            tx=self.a * other.tx + self.b * other.ty + self.tx,
            ty=self.c * other.tx + self.d * other.ty + self.ty,
        )

    def apply(self, p: Vec2) -> Vec2:
        return Vec2(
            self.a * p.x + self.b * p.y + self.tx,
            self.c * p.x + self.d * p.y + self.ty,
        )

    def apply_direction(self, v: Vec2) -> Vec2:
        """Transform a direction vector (ignores translation)."""
        return Vec2(self.a * v.x + self.b * v.y, self.c * v.x + self.d * v.y)

    def determinant(self) -> float:
        return self.a * self.d - self.b * self.c

    def max_scale_factor(self) -> float:
        """Calculate the maximum scaling factor of the transform."""
        # For M = [[a, b], [c, d]], we want sqrt(max_eigenvalue(M^T M)).
        # M^T M = [[a^2+c^2, ab+cd], [ab+cd, b^2+d^2]]
        # Let A = a^2 + c^2, B = b^2 + d^2, C = ab + cd
        # Tr = A + B
        # Det = AB - C^2 = (ad - bc)^2
        # lambda = (Tr + sqrt(Tr^2 - 4*Det)) / 2
        
        aa = self.a * self.a
        bb = self.b * self.b
        cc = self.c * self.c
        dd = self.d * self.d
        
        trace = aa + bb + cc + dd
        det = self.a * self.d - self.b * self.c
        det_sq = det * det
        
        # Discriminant of characteristic equation
        # (Tr)^2 - 4*Det_sq
        disc = trace * trace - 4 * det_sq
        if disc < 0:
            disc = 0  # Should not happen for symmetric matrix
            
        lambda_max = (trace + math.sqrt(disc)) * 0.5
        return math.sqrt(lambda_max)

    def inverse(self) -> AffineTransform:
        det = self.determinant()
        if abs(det) < 1e-15:
            raise ValueError("Singular transform — cannot invert")
        inv_det = 1.0 / det
        return AffineTransform(
            a=self.d * inv_det,
            b=-self.b * inv_det,
            c=-self.c * inv_det,
            d=self.a * inv_det,
            tx=(self.b * self.ty - self.d * self.tx) * inv_det,
            ty=(self.c * self.tx - self.a * self.ty) * inv_det,
        )

    def translate(self, dx: float, dy: float) -> AffineTransform:
        return self.concat(AffineTransform.translation(dx, dy))

    def scale(self, sx: float, sy: float | None = None) -> AffineTransform:
        return self.concat(AffineTransform.scaling(sx, sy))

    def rotate(self, angle_rad: float) -> AffineTransform:
        return self.concat(AffineTransform.rotation(angle_rad))

    @property
    def is_identity(self) -> bool:
        return (
            abs(self.a - 1.0) < 1e-12
            and abs(self.b) < 1e-12
            and abs(self.c) < 1e-12
            and abs(self.d - 1.0) < 1e-12
            and abs(self.tx) < 1e-12
            and abs(self.ty) < 1e-12
        )

    def decompose(self) -> dict:
        """Decompose into translation, rotation, scale, skew."""
        sx = math.hypot(self.a, self.c)
        sy = math.hypot(self.b, self.d)
        det = self.determinant()
        if det < 0:
            sx = -sx
        rotation = math.atan2(self.c, self.a)
        return {
            "translate": Vec2(self.tx, self.ty),
            "rotate": rotation,
            "scale": Vec2(sx, sy),
        }

    def to_tuple(self) -> tuple[float, float, float, float, float, float]:
        return (self.a, self.b, self.c, self.d, self.tx, self.ty)

    def to_qtransform(self) -> "QTransform":
        """Convert to PySide6 QTransform.

        Qt uses: x' = m11*x + m21*y + dx, y' = m12*x + m22*y + dy.
        Our AffineTransform: x' = a*x + b*y + tx, y' = c*x + d*y + ty.
        So m11=a, m21=b, m12=c, m22=d. QTransform(m11, m12, m21, m22, dx, dy).
        """
        from PySide6.QtGui import QTransform
        return QTransform(self.a, self.c, self.b, self.d, self.tx, self.ty)

    @staticmethod
    def from_tuple(t: tuple[float, ...]) -> AffineTransform:
        return AffineTransform(t[0], t[1], t[2], t[3], t[4], t[5])

    @staticmethod
    def from_qtransform(t: "QTransform") -> AffineTransform:
        """Extract AffineTransform from QTransform (inverse of to_qtransform)."""
        return AffineTransform(
            t.m11(), t.m21(), t.m12(), t.m22(), t.dx(), t.dy()
        )

    def __repr__(self) -> str:
        return (
            f"AffineTransform(a={self.a:.6g}, b={self.b:.6g}, "
            f"c={self.c:.6g}, d={self.d:.6g}, "
            f"tx={self.tx:.6g}, ty={self.ty:.6g})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AffineTransform):
            return NotImplemented
        return (
            self.a == other.a
            and self.b == other.b
            and self.c == other.c
            and self.d == other.d
            and self.tx == other.tx
            and self.ty == other.ty
        )

    def __hash__(self) -> int:
        return hash((self.a, self.b, self.c, self.d, self.tx, self.ty))

    def __copy__(self) -> "AffineTransform":
        return self

    def __deepcopy__(self, memo: dict) -> "AffineTransform":
        return self
