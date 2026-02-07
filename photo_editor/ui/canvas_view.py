"""Zoomable, pannable canvas with selection overlay and tool cursors."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QColor, QCursor, QImage, QMouseEvent, QPainter, QPen,
    QPixmap, QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from ..core.enums import ToolType

# Pre-built checkerboard tile (fast)
_CHECKER_SIZE = 16
_CHECKER_TILE: QPixmap | None = None


def _checker_tile() -> QPixmap:
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


# Cursor shapes per tool type
_CURSORS: dict[ToolType, Qt.CursorShape] = {
    ToolType.BRUSH: Qt.CursorShape.CrossCursor,
    ToolType.ERASER: Qt.CursorShape.CrossCursor,
    ToolType.CLONE_STAMP: Qt.CursorShape.CrossCursor,
    ToolType.HEALING_BRUSH: Qt.CursorShape.CrossCursor,
    ToolType.GRADIENT: Qt.CursorShape.CrossCursor,
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
}


class CanvasView(QWidget):
    """Interactive canvas that displays the composited document."""

    cursor_moved = Signal(int, int)
    tool_pressed = Signal(int, int, float)
    tool_moved = Signal(int, int, float)
    tool_released = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self._last_mouse = QPointF()
        self._panning = False
        self._doc_w = 0
        self._doc_h = 0
        # Selection overlay
        self._sel_mask: np.ndarray | None = None
        self._sel_pixmap: QPixmap | None = None
        # Drag rect feedback for selection tools
        self._drag_rect: QRectF | None = None

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(200, 200)

    # ---- Public API ---------------------------------------------------------

    def set_image(self, rgba: np.ndarray) -> None:
        h, w = rgba.shape[:2]
        self._doc_w, self._doc_h = w, h
        qimg = QImage(rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
        self._pixmap = QPixmap.fromImage(qimg.copy())
        self.update()

    def set_selection_mask(self, mask: np.ndarray | None) -> None:
        """Set the selection mask for overlay rendering."""
        if mask is None:
            self._sel_pixmap = None
            self._sel_mask = None
            self.update()
            return
        self._sel_mask = mask
        h, w = mask.shape[:2]
        overlay = np.zeros((h, w, 4), dtype=np.uint8)
        overlay[..., 0] = 70   # blue tint
        overlay[..., 1] = 130
        overlay[..., 2] = 220
        overlay[..., 3] = (mask * 80).astype(np.uint8)
        qimg = QImage(overlay.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
        self._sel_pixmap = QPixmap.fromImage(qimg.copy())
        self.update()

    def set_drag_rect(self, rect: QRectF | None) -> None:
        self._drag_rect = rect
        self.update()

    def set_tool_cursor(self, tool_type: ToolType) -> None:
        shape = _CURSORS.get(tool_type, Qt.CursorShape.ArrowCursor)
        self.setCursor(QCursor(shape))

    @property
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, z: float) -> None:
        self._zoom = max(0.01, min(z, 32.0))
        self.update()

    def zoom_to_fit(self) -> None:
        if self._doc_w and self._doc_h:
            sx = self.width() / self._doc_w
            sy = self.height() / self._doc_h
            self._zoom = min(sx, sy) * 0.9
            self._pan = QPointF(0, 0)
            self.update()

    def _canvas_to_doc(self, pos: QPointF) -> tuple[int, int]:
        cx = self.width() / 2 + self._pan.x()
        cy = self.height() / 2 + self._pan.y()
        dx = (pos.x() - cx) / self._zoom + self._doc_w / 2
        dy = (pos.y() - cy) / self._zoom + self._doc_h / 2
        return int(dx), int(dy)

    def _doc_rect(self) -> QRectF:
        cx = self.width() / 2 + self._pan.x()
        cy = self.height() / 2 + self._pan.y()
        sw = self._doc_w * self._zoom
        sh = self._doc_h * self._zoom
        return QRectF(cx - sw / 2, cy - sh / 2, sw, sh)

    # ---- Paint --------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(50, 50, 50))

        if self._pixmap is None:
            p.end()
            return

        dr = self._doc_rect()

        # Checkerboard (tiled — fast)
        p.save()
        p.setClipRect(dr.toAlignedRect())
        tile = _checker_tile()
        for y in range(int(dr.top()), int(dr.bottom()), tile.height()):
            for x in range(int(dr.left()), int(dr.right()), tile.width()):
                p.drawPixmap(x, y, tile)
        p.restore()

        # Document image
        p.drawPixmap(dr.toAlignedRect(), self._pixmap)

        # Selection overlay
        if self._sel_pixmap is not None:
            p.setOpacity(0.6)
            p.drawPixmap(dr.toAlignedRect(), self._sel_pixmap)
            p.setOpacity(1.0)

        # Selection drag rectangle
        if self._drag_rect is not None:
            pen = QPen(QColor(100, 180, 255), 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(QColor(100, 180, 255, 30))
            p.drawRect(self._drag_rect)

        p.end()

    # ---- Mouse events -------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        self._zoom = max(0.01, min(self._zoom * factor, 32.0))
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._last_mouse = event.position()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        elif event.button() == Qt.MouseButton.LeftButton:
            dx, dy = self._canvas_to_doc(event.position())
            self.tool_pressed.emit(dx, dy, 1.0)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            delta = event.position() - self._last_mouse
            self._pan += delta
            self._last_mouse = event.position()
            self.update()
            return
        dx, dy = self._canvas_to_doc(event.position())
        self.cursor_moved.emit(dx, dy)
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.tool_moved.emit(dx, dy, 1.0)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            # Restore tool cursor
        elif event.button() == Qt.MouseButton.LeftButton:
            dx, dy = self._canvas_to_doc(event.position())
            self.tool_released.emit(dx, dy)
            self._drag_rect = None
