"""HSV Color Wheel with Saturation-Value triangle — Affinity-style.

The outer ring selects Hue; the inner triangle selects Saturation & Value.
High-performance rendering caches the wheel/triangle as QImages and only
regenerates when the widget resizes or hue changes.
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from ...core.color import Color
from ...core.color_engine import hsv_to_rgb, rgb_to_hsv


class ColorWheel(QWidget):
    """HSV colour wheel with inner SV triangle (Affinity / Krita style).

    Signals
    -------
    color_changed(Color)
        Emitted continuously as the user drags.
    color_committed(Color)
        Emitted on mouse-release (final pick).
    """

    color_changed = Signal(object)
    color_committed = Signal(object)

    # Layout constants
    _RING_WIDTH_RATIO = 0.13  # ring width as fraction of radius
    _TRIANGLE_MARGIN = 4      # px gap between ring and triangle

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(180, 180)
        self._hue: float = 0.0       # 0-360
        self._sat: float = 1.0       # 0-1
        self._val: float = 1.0       # 0-1
        self._alpha: float = 1.0

        self._dragging_ring = False
        self._dragging_triangle = False

        # Cached renders
        self._wheel_pixmap: QPixmap | None = None
        self._triangle_image: QImage | None = None
        self._last_size: int = 0
        self._last_hue_for_tri: float = -1.0

    # ---- Public API ---------------------------------------------------------

    def color(self) -> Color:
        r, g, b = hsv_to_rgb(self._hue, self._sat, self._val)
        return Color(r, g, b, self._alpha)

    def set_color(self, c: Color, *, emit: bool = False) -> None:
        h, s, v = rgb_to_hsv(c.r, c.g, c.b)
        changed = (h != self._hue or s != self._sat or v != self._val or c.a != self._alpha)
        # Only update hue if the color has meaningful saturation/value
        if s > 0.001 and v > 0.001:
            self._hue = h
        self._sat = s
        self._val = v
        self._alpha = c.a
        if changed:
            self._triangle_image = None  # invalidate cached triangle
            self.update()
            if emit:
                self.color_changed.emit(self.color())

    def set_hue(self, hue: float) -> None:
        self._hue = hue % 360
        self._triangle_image = None
        self.update()

    # ---- Geometry helpers ---------------------------------------------------

    def _metrics(self):
        size = min(self.width(), self.height())
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        outer_r = size / 2.0 - 2
        ring_w = max(12, outer_r * self._RING_WIDTH_RATIO)
        inner_r = outer_r - ring_w
        tri_r = inner_r - self._TRIANGLE_MARGIN
        return cx, cy, outer_r, inner_r, ring_w, tri_r

    def _triangle_vertices(self) -> list[QPointF]:
        """Three vertices of the SV triangle, rotated by hue.

        QConicalGradient angle 0 = 3-o'clock, grows counter-clockwise.
        We convert hue to the same Qt screen coordinate system so the
        pure-hue vertex always sits under the ring indicator.
        """
        cx, cy, _, _, _, tri_r = self._metrics()
        # Qt screen coords: Y grows downward.  QConicalGradient 0deg = right, CCW.
        # hue 0 = red at 3-o'clock.  Negate for CW screen convention.
        angle_rad = math.radians(-self._hue)
        pts = []
        for i in range(3):
            a = angle_rad + i * (2 * math.pi / 3)
            pts.append(QPointF(cx + tri_r * math.cos(a), cy + tri_r * math.sin(a)))
        return pts

    # ---- Rendering ----------------------------------------------------------

    def _ensure_wheel(self, size: int) -> None:
        """Cache the hue ring as a pixmap."""
        if self._wheel_pixmap is not None and self._last_size == size:
            return
        self._last_size = size
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        _, _, outer_r, inner_r, ring_w, _ = self._metrics()

        pix = QPixmap(self.width(), self.height())
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Conical gradient for hue ring
        grad = QConicalGradient(cx, cy, 0)
        for i in range(361):
            r, g, b = hsv_to_rgb(float(i), 1.0, 1.0)
            grad.setColorAt(i / 360.0, QColor.fromRgbF(r, g, b))

        ring_path = QPainterPath()
        ring_path.addEllipse(QRectF(cx - outer_r, cy - outer_r, outer_r * 2, outer_r * 2))
        inner_path = QPainterPath()
        inner_path.addEllipse(QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2))
        ring_path = ring_path.subtracted(inner_path)

        p.setBrush(grad)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(ring_path)
        p.end()
        self._wheel_pixmap = pix

    def _ensure_triangle(self) -> None:
        """Cache the SV triangle raster — fully vectorised via numpy."""
        if self._triangle_image is not None and self._last_hue_for_tri == self._hue:
            return
        self._last_hue_for_tri = self._hue

        w, h = self.width(), self.height()
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)

        pts = self._triangle_vertices()
        if len(pts) < 3:
            self._triangle_image = img
            return

        p0, p1, p2 = pts  # p0=hue vertex, p1=white vertex, p2=black vertex
        x0, y0 = p0.x(), p0.y()
        x1, y1 = p1.x(), p1.y()
        x2, y2 = p2.x(), p2.y()

        # Bounding box
        min_x = max(0, int(min(x0, x1, x2) - 1))
        max_x = min(w - 1, int(max(x0, x1, x2) + 2))
        min_y = max(0, int(min(y0, y1, y2) - 1))
        max_y = min(h - 1, int(max(y0, y1, y2) + 2))

        # Use half-pixel offset for centre-of-pixel sampling (reduces aliasing)
        xs = np.arange(min_x, max_x + 1, dtype=np.float64) + 0.5
        ys = np.arange(min_y, max_y + 1, dtype=np.float64) + 0.5
        gx, gy = np.meshgrid(xs, ys)

        # Barycentric coordinates (float64 for precision)
        denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(denom) < 1e-6:
            self._triangle_image = img
            return

        inv_denom = 1.0 / denom
        l0 = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) * inv_denom
        l1 = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) * inv_denom
        l2 = 1.0 - l0 - l1

        # Edge softness — 1px anti-alias feather at the boundary
        edge_dist = np.minimum(np.minimum(l0, l1), l2)
        mask = edge_dist >= -0.01
        alpha_f = np.clip(edge_dist * 100.0 + 1.0, 0.0, 1.0)  # smooth 0→1 in ~1px

        # SV mapping
        V = np.clip(l0 + l1, 0, 1)
        safe_V = np.where(V > 0.001, V, 1.0)
        S = np.where(V > 0.001, np.clip(l0 / safe_V, 0, 1), 0.0)

        # Vectorised HSV→RGB (constant hue)
        hue_norm = self._hue
        c_val = V * S
        h_sector = int(hue_norm / 60) % 6
        x_val = c_val * (1.0 - abs((hue_norm / 60.0) % 2 - 1.0))
        m_val = V - c_val

        if h_sector == 0:
            r_f, g_f, b_f = c_val + m_val, x_val + m_val, m_val
        elif h_sector == 1:
            r_f, g_f, b_f = x_val + m_val, c_val + m_val, m_val
        elif h_sector == 2:
            r_f, g_f, b_f = m_val, c_val + m_val, x_val + m_val
        elif h_sector == 3:
            r_f, g_f, b_f = m_val, x_val + m_val, c_val + m_val
        elif h_sector == 4:
            r_f, g_f, b_f = x_val + m_val, m_val, c_val + m_val
        else:
            r_f, g_f, b_f = c_val + m_val, m_val, x_val + m_val

        rows = max_y - min_y + 1
        cols = max_x - min_x + 1

        # Build ARGB32 buffer — format is 0xAARRGGBB (little-endian → BGRA bytes)
        # Compute alpha per pixel (0 outside, feathered at edges, 255 inside)
        a_f = np.where(mask, alpha_f, 0.0)
        a_arr = np.clip(a_f * 255, 0, 255).astype(np.uint8)
        r_arr = np.clip(r_f * 255, 0, 255).astype(np.uint8)
        g_arr = np.clip(g_f * 255, 0, 255).astype(np.uint8)
        b_arr = np.clip(b_f * 255, 0, 255).astype(np.uint8)

        # Pack into ARGB32 uint32 array: 0xAARRGGBB
        argb = (a_arr.astype(np.uint32) << 24) | \
               (r_arr.astype(np.uint32) << 16) | \
               (g_arr.astype(np.uint32) << 8) | \
               (b_arr.astype(np.uint32))

        # Write scanlines into QImage in bulk
        for iy in range(rows):
            src_line = argb[iy].tobytes()
            # Get pointer to target scanline and copy bytes
            dest_ptr = img.scanLine(min_y + iy)
            # numpy → bytes, write at correct x offset
            # Each pixel is 4 bytes in ARGB32_Premultiplied
            full_line = bytearray(dest_ptr)
            offset = min_x * 4
            full_line[offset:offset + cols * 4] = src_line
            # Write back (PySide6 scanLine returns memoryview)
            dest_ptr[offset:offset + cols * 4] = src_line

        self._triangle_image = img

    def paintEvent(self, event) -> None:
        size = min(self.width(), self.height())
        if size < 20:
            return

        self._ensure_wheel(size)
        self._ensure_triangle()

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw cached wheel
        if self._wheel_pixmap:
            p.drawPixmap(0, 0, self._wheel_pixmap)

        # Draw cached triangle
        if self._triangle_image:
            p.drawImage(0, 0, self._triangle_image)

        # Draw triangle border — subtle rounded edge feel
        pts = self._triangle_vertices()
        if pts:
            tri_path = QPainterPath()
            tri_path.moveTo(pts[0])
            tri_path.lineTo(pts[1])
            tri_path.lineTo(pts[2])
            tri_path.closeSubpath()
            p.setPen(QPen(QColor(0, 0, 0, 80), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(tri_path)

        # ---- Hue indicator on ring (modern pill / capsule style) ----
        cx, cy, outer_r, inner_r, ring_w, _ = self._metrics()
        mid_r = (outer_r + inner_r) / 2.0
        hue_rad = math.radians(-self._hue)  # match QConicalGradient CW convention
        hx = cx + mid_r * math.cos(hue_rad)
        hy = cy + mid_r * math.sin(hue_rad)
        indicator_r = ring_w / 2.0 - 1

        # Shadow
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawEllipse(QPointF(hx, hy + 1), indicator_r + 1.5, indicator_r + 1.5)

        # Outer ring (dark)
        p.setPen(QPen(QColor(30, 30, 30), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(hx, hy), indicator_r + 0.5, indicator_r + 0.5)

        # Inner white ring
        p.setPen(QPen(QColor(255, 255, 255), 2.0))
        p.drawEllipse(QPointF(hx, hy), indicator_r - 0.5, indicator_r - 0.5)

        # ---- SV indicator in triangle (modern circle with color fill) ----
        sv_pos = self._sv_to_point()
        if sv_pos:
            # Shadow
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 50))
            p.drawEllipse(sv_pos + QPointF(0, 1), 7, 7)

            # Fill with current color
            r, g, b = hsv_to_rgb(self._hue, self._sat, self._val)
            p.setBrush(QColor.fromRgbF(r, g, b))
            p.setPen(QPen(QColor(30, 30, 30), 1.5))
            p.drawEllipse(sv_pos, 5.5, 5.5)
            p.setPen(QPen(QColor(255, 255, 255), 2.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(sv_pos, 5, 5)

        p.end()

    def _sv_to_point(self) -> QPointF | None:
        """Map current S, V to a point inside the triangle."""
        pts = self._triangle_vertices()
        if len(pts) < 3:
            return None
        p0, p1, p2 = pts
        # Inverse of the barycentric mapping used in rendering:
        # l0 = S * V, l1 = V - S*V = V*(1-S), l2 = 1 - V
        l0 = self._sat * self._val
        l1 = self._val * (1 - self._sat)
        l2 = 1.0 - self._val
        x = l0 * p0.x() + l1 * p1.x() + l2 * p2.x()
        y = l0 * p0.y() + l1 * p1.y() + l2 * p2.y()
        return QPointF(x, y)

    # ---- Mouse interaction --------------------------------------------------

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        cx, cy, outer_r, inner_r, _, tri_r = self._metrics()
        dx = ev.position().x() - cx
        dy = ev.position().y() - cy
        dist = math.sqrt(dx * dx + dy * dy)

        if inner_r <= dist <= outer_r:
            self._dragging_ring = True
            self._update_hue_from_pos(ev.position())
        else:
            self._dragging_triangle = True
            self._update_sv_from_pos(ev.position())

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        if self._dragging_ring:
            self._update_hue_from_pos(ev.position())
        elif self._dragging_triangle:
            self._update_sv_from_pos(ev.position())

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        if self._dragging_ring or self._dragging_triangle:
            self.color_committed.emit(self.color())
        self._dragging_ring = False
        self._dragging_triangle = False

    def _update_hue_from_pos(self, pos: QPointF) -> None:
        cx, cy, *_ = self._metrics()
        dx = pos.x() - cx
        dy = pos.y() - cy  # screen Y (down = positive)
        angle = (-math.degrees(math.atan2(dy, dx))) % 360  # CW from right = hue
        self._hue = angle
        self._triangle_image = None
        self.update()
        self.color_changed.emit(self.color())

    def _update_sv_from_pos(self, pos: QPointF) -> None:
        pts = self._triangle_vertices()
        if len(pts) < 3:
            return
        p0, p1, p2 = pts
        x, y = pos.x(), pos.y()
        x0, y0 = p0.x(), p0.y()
        x1, y1 = p1.x(), p1.y()
        x2, y2 = p2.x(), p2.y()

        denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(denom) < 1e-6:
            return
        inv = 1.0 / denom
        l0 = ((y1 - y2) * (x - x2) + (x2 - x1) * (y - y2)) * inv
        l1 = ((y2 - y0) * (x - x2) + (x0 - x2) * (y - y2)) * inv
        l2 = 1.0 - l0 - l1

        # Clamp to triangle
        l0 = max(0.0, min(1.0, l0))
        l1 = max(0.0, min(1.0, l1))
        l2 = max(0.0, min(1.0, l2))
        total = l0 + l1 + l2
        if total > 0:
            l0 /= total
            l1 /= total
            l2 /= total

        V = l0 + l1
        S = l0 / V if V > 0.001 else 0.0
        self._sat = max(0.0, min(1.0, S))
        self._val = max(0.0, min(1.0, V))
        self.update()
        self.color_changed.emit(self.color())

    # ---- Resize invalidation -----------------------------------------------

    def resizeEvent(self, event) -> None:
        self._wheel_pixmap = None
        self._triangle_image = None
        super().resizeEvent(event)
