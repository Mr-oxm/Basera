"""Professional-grade vector graphics engine.

Architecture Overview
=====================
This package implements a complete vector graphics system designed for
real-time interactive editing of complex vector documents.  The design
draws on the same principles used in Affinity Designer and Adobe
Illustrator's rendering cores.

Module layout
-------------
- **geometry**  — Low-level 2D primitives: `Vec2`, `BBox`, `AffineTransform`
- **bezier**    — Cubic Bézier mathematics: evaluation, splitting, arc-length,
                  curvature, inflections, offset curves
- **path**      — `VectorPath`: sequence of `PathSegment` (line / cubic) with
                  winding-rule fills, open/closed sub-paths
- **shapes**    — Live-parameter shape primitives (rect, ellipse, polygon, star)
                  that emit `VectorPath` on demand
- **spatial**   — R-tree spatial index for O(log n) hit-testing and culling
- **boolean**   — Path boolean operations (union, subtract, intersect, divide,
                  exclude) using Greiner–Hormann + Weiler–Atherton
- **boolean_ops** — Higher-level document-layer boolean operations returning new layers
- **pick_segments** — Interactive path fragment selection and contour stitching
- **style**     — `VectorStyle`: multi-fill / multi-stroke paint stacks,
                  gradient meshes, dash patterns, variable-width strokes
- **scene**     — `VectorObject` scene-graph node wrapping path + style +
                  transform, `VectorLayer` container
- **rasterizer**— Scanline + signed-distance-field rasteriser with sub-pixel
                  anti-aliasing, outputs numpy RGBA float32 tiles
- **svg**       — SVG import / export
- **pdf**       — PDF vector export via `reportlab`
- **tools**     — `PenTool`, `NodeTool`, `VectorShapeTool`

Performance strategy
--------------------
* All hot paths are written in pure NumPy with pre-allocated buffers.
* Spatial queries use an R-tree with bulk-loading.
* Bézier subdivision uses de Casteljau with SIMD-friendly memory layout.
* Rasterisation is tile-based (256×256) with LRU caching.
* Intersection detection uses a sweep-line with monotone decomposition.
"""

from .geometry import Vec2, BBox, AffineTransform
from .bezier import CubicBezier, QuadraticBezier
from .path import VectorPath, PathSegment, SegmentType, FillRule
from .shapes import (
    RectangleShape, EllipseShape, PolygonShape, StarShape, LineShape,
)
from .style import (
    VectorStyle, VectorFill, VectorStroke, FillPaint,
    GradientPaint, PatternPaint, StrokeCap, StrokeJoin,
    DashPattern,
)
from .scene import VectorObject, VectorLayer
from .spatial import RTree, RTreeEntry
from .rasterizer import VectorRasterizer
from .svg import export_svg, import_svg, path_to_svg_d, svg_d_to_path
from .pdf import export_pdf, export_pdf_bytes

__all__ = [
    # geometry
    "Vec2", "BBox", "AffineTransform",
    # bezier
    "CubicBezier", "QuadraticBezier",
    # path
    "VectorPath", "PathSegment", "SegmentType", "FillRule",
    # shapes
    "RectangleShape", "EllipseShape", "PolygonShape", "StarShape", "LineShape",
    # style
    "VectorStyle", "VectorFill", "VectorStroke", "FillPaint",
    "GradientPaint", "PatternPaint", "StrokeCap", "StrokeJoin",
    "DashPattern",
    # scene
    "VectorObject", "VectorLayer",
    # spatial
    "RTree", "RTreeEntry",
    # rasterizer
    "VectorRasterizer",
    # svg
    "export_svg", "import_svg", "path_to_svg_d", "svg_d_to_path",
    # pdf
    "export_pdf", "export_pdf_bytes",
]
