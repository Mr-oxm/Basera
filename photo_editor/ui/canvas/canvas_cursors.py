"""Cursor builders and tool-to-cursor mapping."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QCursor, QLinearGradient, QPainter, QPen, QPixmap

from ...core.enums import ToolType

# Pre-built checkerboard tile (fast)
_CHECKER_SIZE = 16
_CHECKER_TILE: QPixmap | None = None

# Custom gradient cursor (built lazily)
_GRADIENT_CURSOR: QCursor | None = None

# Rotation cursor cache
_ROTATE_CURSOR_CACHE: QCursor | None = None


def _make_gradient_cursor() -> QCursor:
    """Build a crosshair cursor with a tiny gradient swatch indicator."""
    size = 32
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy = size // 2, size // 2

    pen = QPen(QColor(0, 0, 0, 160), 1.4)
    pen.setCosmetic(True)
    p.setPen(pen)
    gap = 4
    arm = 10
    p.drawLine(cx, cy - arm, cx, cy - gap)
    p.drawLine(cx, cy + gap, cx, cy + arm)
    p.drawLine(cx - arm, cy, cx - gap, cy)
    p.drawLine(cx + gap, cy, cx + arm, cy)

    pen2 = QPen(QColor(255, 255, 255, 230), 1.0)
    pen2.setCosmetic(True)
    p.setPen(pen2)
    p.drawLine(cx, cy - arm, cx, cy - gap)
    p.drawLine(cx, cy + gap, cx, cy + arm)
    p.drawLine(cx - arm, cy, cx - gap, cy)
    p.drawLine(cx + gap, cy, cx + arm, cy)

    gx, gy, gw, gh = cx + 3, cy + 3, 9, 7
    grad = QLinearGradient(gx, gy, gx + gw, gy)
    grad.setColorAt(0.0, QColor(0, 0, 0))
    grad.setColorAt(1.0, QColor(255, 255, 255))
    p.setPen(QPen(QColor(160, 160, 160), 0.8))
    p.setBrush(grad)
    p.drawRoundedRect(gx, gy, gw, gh, 1.5, 1.5)

    p.end()
    return QCursor(pm, cx, cy)


def gradient_cursor() -> QCursor:
    """Return the gradient tool cursor (lazy-built)."""
    global _GRADIENT_CURSOR
    if _GRADIENT_CURSOR is None:
        _GRADIENT_CURSOR = _make_gradient_cursor()
    return _GRADIENT_CURSOR


def checker_tile() -> QPixmap:
    """Return the checkerboard tile for transparency (lazy-built)."""
    global _CHECKER_TILE
    if _CHECKER_TILE is None:
        s = _CHECKER_SIZE
        _CHECKER_TILE = QPixmap(s * 2, s * 2)
        p = QPainter(_CHECKER_TILE)
        p.fillRect(0, 0, s * 2, s * 2, QColor(204, 204, 204))
        p.fillRect(0, 0, s, s, Qt.GlobalColor.white)
        p.fillRect(s, s, s, s, Qt.GlobalColor.white)
        p.end()
    return _CHECKER_TILE


CURSORS: dict[ToolType, Qt.CursorShape | None] = {
    ToolType.BRUSH: Qt.CursorShape.CrossCursor,
    ToolType.ERASER: Qt.CursorShape.CrossCursor,
    ToolType.CLONE_STAMP: Qt.CursorShape.CrossCursor,
    ToolType.HEALING_BRUSH: Qt.CursorShape.CrossCursor,
    ToolType.GRADIENT: None,  # handled separately with custom pixmap cursor
    ToolType.PAINT_BUCKET: Qt.CursorShape.CrossCursor,
    ToolType.RECT_SELECT: Qt.CursorShape.CrossCursor,
    ToolType.ELLIPSE_SELECT: Qt.CursorShape.CrossCursor,
    ToolType.LASSO: Qt.CursorShape.CrossCursor,
    ToolType.MAGIC_WAND: Qt.CursorShape.CrossCursor,
    ToolType.TEXT: Qt.CursorShape.IBeamCursor,
    ToolType.SHAPE: Qt.CursorShape.CrossCursor,
    ToolType.TRANSFORM: Qt.CursorShape.SizeAllCursor,
    ToolType.MOVE: Qt.CursorShape.SizeAllCursor,
    ToolType.ZOOM: Qt.CursorShape.PointingHandCursor,
    ToolType.PAN: Qt.CursorShape.OpenHandCursor,
    ToolType.EYEDROPPER: Qt.CursorShape.CrossCursor,
    ToolType.CROP: Qt.CursorShape.CrossCursor,
    ToolType.PEN: Qt.CursorShape.CrossCursor,
    ToolType.NODE: Qt.CursorShape.ArrowCursor,
    ToolType.VECTOR_SHAPE: Qt.CursorShape.CrossCursor,
}

HANDLE_CURSORS: dict[str, Qt.CursorShape] = {
    "TL": Qt.CursorShape.SizeFDiagCursor,
    "TR": Qt.CursorShape.SizeBDiagCursor,
    "BL": Qt.CursorShape.SizeBDiagCursor,
    "BR": Qt.CursorShape.SizeFDiagCursor,
    "T": Qt.CursorShape.SizeVerCursor,
    "B": Qt.CursorShape.SizeVerCursor,
    "L": Qt.CursorShape.SizeHorCursor,
    "R": Qt.CursorShape.SizeHorCursor,
}

HANDLE_HIT = 12  # pixels radius on screen for handle hit-testing


def build_rotate_cursor() -> QCursor:
    """Build a custom rotation cursor (circular arrow)."""
    global _ROTATE_CURSOR_CACHE
    if _ROTATE_CURSOR_CACHE is not None:
        return _ROTATE_CURSOR_CACHE
    size = 24
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    center = size / 2
    radius = 8.0
    from PySide6.QtCore import QRectF as _QRectF
    arc_rect = _QRectF(center - radius, center - radius, radius * 2, radius * 2)
    pen = QPen(QColor(0, 0, 0), 2.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawArc(arc_rect, 30 * 16, 270 * 16)
    pen2 = QPen(QColor(255, 255, 255), 1.2)
    pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen2)
    p.drawArc(arc_rect, 30 * 16, 270 * 16)
    end_angle = math.radians(30)
    ex = center + radius * math.cos(end_angle)
    ey = center - radius * math.sin(end_angle)
    p.setPen(QPen(QColor(0, 0, 0), 2.5))
    p.setBrush(QColor(0, 0, 0))
    from PySide6.QtGui import QPolygonF as _QPolyF
    arrow = _QPolyF()
    arrow.append(QPointF(ex, ey))
    arrow.append(QPointF(ex + 4, ey - 3))
    arrow.append(QPointF(ex + 1, ey + 4))
    p.drawPolygon(arrow)
    p.end()
    _ROTATE_CURSOR_CACHE = QCursor(pm, size // 2, size // 2)
    return _ROTATE_CURSOR_CACHE


_SOURCE_CURSOR_CACHE: QCursor | None = None


def build_source_cursor() -> QCursor:
    """Build a target/bullseye cursor for clone/heal source selection."""
    global _SOURCE_CURSOR_CACHE
    if _SOURCE_CURSOR_CACHE is not None:
        return _SOURCE_CURSOR_CACHE
    size = 32
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy = size // 2, size // 2

    pen = QPen(QColor(0, 0, 0, 180), 1.6)
    pen.setCosmetic(True)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(cx - 10, cy - 10, 20, 20)
    pen2 = QPen(QColor(0, 220, 255, 240), 1.0)
    pen2.setCosmetic(True)
    p.setPen(pen2)
    p.drawEllipse(cx - 10, cy - 10, 20, 20)
    p.drawEllipse(cx - 4, cy - 4, 8, 8)

    gap = 5
    arm = 12
    p.setPen(QPen(QColor(0, 0, 0, 180), 1.4))
    p.drawLine(cx, cy - arm, cx, cy - gap)
    p.drawLine(cx, cy + gap, cx, cy + arm)
    p.drawLine(cx - arm, cy, cx - gap, cy)
    p.drawLine(cx + arm, cy, cx + gap, cy)
    p.setPen(QPen(QColor(0, 220, 255, 240), 1.0))
    p.drawLine(cx, cy - arm, cx, cy - gap)
    p.drawLine(cx, cy + gap, cx, cy + arm)
    p.drawLine(cx - arm, cy, cx - gap, cy)
    p.drawLine(cx + arm, cy, cx + gap, cy)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 220, 255, 220))
    p.drawEllipse(cx - 1, cy - 1, 3, 3)

    p.end()
    _SOURCE_CURSOR_CACHE = QCursor(pm, cx, cy)
    return _SOURCE_CURSOR_CACHE

