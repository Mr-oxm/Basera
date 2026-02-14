"""PDF vector export.

Generates PDF files with native vector content (not rasterised images).
Uses raw PDF operators so there are **no external dependencies** beyond
the Python standard library.

The module produces valid single-page PDF 1.4 documents.  All vector
objects are rendered using the PDF path-construction and painting
operators (``m``, ``l``, ``c``, ``h``, ``W``, ``f``, ``S``, etc.).

Typical usage::

    from photo_editor.vector.pdf import export_pdf
    export_pdf(my_objects, "output.pdf", width=800, height=600)
"""

from __future__ import annotations

import struct
from typing import Sequence

from .geometry import Vec2
from .path import VectorPath, SubPath
from .scene import VectorObject
from .style import (
    VectorStyle, VectorFill, VectorStroke,
    SolidPaint, GradientPaint,
    StrokeCap, StrokeJoin,
)

__all__ = ["export_pdf", "export_pdf_bytes"]


def export_pdf(
    objects: Sequence[VectorObject],
    filepath: str,
    width: float = 800,
    height: float = 600,
) -> None:
    """Write vector objects to a PDF file."""
    data = export_pdf_bytes(objects, width, height)
    with open(filepath, "wb") as f:
        f.write(data)


def export_pdf_bytes(
    objects: Sequence[VectorObject],
    width: float = 800,
    height: float = 600,
) -> bytes:
    """Generate PDF file content as bytes."""
    writer = _PDFWriter(width, height)
    for obj in objects:
        if obj.visible:
            writer.draw_object(obj)
    return writer.finish()


# ---------------------------------------------------------------------------
#  Low-level PDF writer
# ---------------------------------------------------------------------------

class _PDFWriter:
    """Minimal PDF 1.4 writer with vector path support."""

    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height
        self._objects: list[bytes] = []
        self._offsets: list[int] = []
        self._stream_parts: list[str] = []

    # -- Public API ---------------------------------------------------------

    def draw_object(self, obj: VectorObject) -> None:
        path = obj.transformed_path()
        style = obj.style

        # PDF coordinate system has origin at bottom-left; flip Y
        self._stream_parts.append("q\n")  # save graphics state

        # Apply Y-flip transform: scale(1,-1) translate(0,-height)
        self._stream_parts.append(
            f"1 0 0 -1 0 {self.height:.4f} cm\n"
        )

        # Draw fills
        for fill in style.fills:
            if not fill.visible or fill.opacity <= 0:
                continue
            self._set_fill_color(fill)
            self._emit_path(path)
            self._stream_parts.append("f\n")  # fill

        # Draw strokes
        for stroke in style.strokes:
            if not stroke.visible or stroke.opacity <= 0 or stroke.width <= 0:
                continue
            self._set_stroke_style(stroke)
            self._emit_path(path)
            self._stream_parts.append("S\n")  # stroke

        self._stream_parts.append("Q\n")  # restore graphics state

    def finish(self) -> bytes:
        """Build the complete PDF bytestream."""
        stream_content = "".join(self._stream_parts).encode("latin-1")
        out = bytearray()

        # Header
        out.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

        # Object 1: Catalog
        self._offsets.append(len(out))
        out.extend(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

        # Object 2: Pages
        self._offsets.append(len(out))
        out.extend(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")

        # Object 3: Page
        self._offsets.append(len(out))
        page = (
            f"3 0 obj\n<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 {self.width:.2f} {self.height:.2f}] "
            f"/Contents 4 0 R >>\nendobj\n"
        )
        out.extend(page.encode("latin-1"))

        # Object 4: Content stream
        self._offsets.append(len(out))
        stream_header = (
            f"4 0 obj\n<< /Length {len(stream_content)} >>\nstream\n"
        )
        out.extend(stream_header.encode("latin-1"))
        out.extend(stream_content)
        out.extend(b"\nendstream\nendobj\n")

        n_objects = 4

        # Cross-reference table
        xref_offset = len(out)
        out.extend(f"xref\n0 {n_objects + 1}\n".encode("latin-1"))
        out.extend(b"0000000000 65535 f \n")
        for off in self._offsets:
            out.extend(f"{off:010d} 00000 n \n".encode("latin-1"))

        # Trailer
        out.extend(
            f"trailer\n<< /Size {n_objects + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n".encode("latin-1")
        )

        return bytes(out)

    # -- Private helpers ----------------------------------------------------

    def _emit_path(self, path: VectorPath) -> None:
        """Write PDF path operators for a VectorPath."""
        from .path import SegmentType

        for sp in path.sub_paths:
            if not sp.nodes:
                continue
            origin = sp.nodes[0].position
            self._stream_parts.append(f"{origin.x:.4f} {origin.y:.4f} m\n")
            for seg in sp.segments:
                if seg.seg_type == SegmentType.LINE:
                    self._stream_parts.append(
                        f"{seg.end.x:.4f} {seg.end.y:.4f} l\n"
                    )
                elif seg.seg_type == SegmentType.CUBIC:
                    self._stream_parts.append(
                        f"{seg.cp1.x:.4f} {seg.cp1.y:.4f} "
                        f"{seg.cp2.x:.4f} {seg.cp2.y:.4f} "
                        f"{seg.end.x:.4f} {seg.end.y:.4f} c\n"
                    )
                elif seg.seg_type == SegmentType.CLOSE:
                    self._stream_parts.append("h\n")

    def _set_fill_color(self, fill: VectorFill) -> None:
        if isinstance(fill.paint, SolidPaint):
            r, g, b, a = fill.paint.color
            self._stream_parts.append(f"{r:.4f} {g:.4f} {b:.4f} rg\n")
        elif isinstance(fill.paint, GradientPaint):
            # Approximate gradient with first stop colour
            if fill.paint.stops:
                r, g, b, a = fill.paint.stops[0].color
                self._stream_parts.append(f"{r:.4f} {g:.4f} {b:.4f} rg\n")

    def _set_stroke_style(self, stroke: VectorStroke) -> None:
        if isinstance(stroke.paint, SolidPaint):
            r, g, b, a = stroke.paint.color
            self._stream_parts.append(f"{r:.4f} {g:.4f} {b:.4f} RG\n")
        elif isinstance(stroke.paint, GradientPaint):
            if stroke.paint.stops:
                r, g, b, a = stroke.paint.stops[0].color
                self._stream_parts.append(f"{r:.4f} {g:.4f} {b:.4f} RG\n")

        self._stream_parts.append(f"{stroke.width:.4f} w\n")

        # Line cap
        cap_map = {StrokeCap.BUTT: 0, StrokeCap.ROUND: 1, StrokeCap.SQUARE: 2}
        self._stream_parts.append(f"{cap_map.get(stroke.cap, 1)} J\n")

        # Line join
        join_map = {StrokeJoin.MITER: 0, StrokeJoin.ROUND: 1, StrokeJoin.BEVEL: 2}
        self._stream_parts.append(f"{join_map.get(stroke.join, 1)} j\n")

        # Dash pattern
        if not stroke.dash.is_solid:
            dash_str = " ".join(f"{v:.2f}" for v in stroke.dash.dashes)
            self._stream_parts.append(f"[{dash_str}] 0 d\n")
