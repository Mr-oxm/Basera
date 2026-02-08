"""Zoomable, pannable canvas with selection overlay, transform box, and tool cursors."""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QColor, QCursor, QImage, QMouseEvent, QPainter,
    QPen, QPixmap, QWheelEvent,
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

# Cursor shapes for bounding-box handles
_HANDLE_CURSORS: dict[str, Qt.CursorShape] = {
    "TL": Qt.CursorShape.SizeFDiagCursor,
    "TR": Qt.CursorShape.SizeBDiagCursor,
    "BL": Qt.CursorShape.SizeBDiagCursor,
    "BR": Qt.CursorShape.SizeFDiagCursor,
    "T": Qt.CursorShape.SizeVerCursor,
    "B": Qt.CursorShape.SizeVerCursor,
    "L": Qt.CursorShape.SizeHorCursor,
    "R": Qt.CursorShape.SizeHorCursor,
}

_HANDLE_HIT = 8  # pixels radius on screen for handle hit-testing


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
        # Transform bounding box (x, y, w, h) in document coordinates
        self._transform_box: tuple[int, int, int, int] | None = None
        self._transform_angle: float = 0.0  # rotation angle in degrees
        # Brush cursor / live dab preview
        self._brush_size: int = 0       # diameter in document pixels (0 = hidden)
        self._brush_cursor_pos: QPointF = QPointF()   # last mouse widget pos
        self._brush_cursor_visible: bool = False
        self._dab_pixmap: QPixmap | None = None       # pre-computed dab (brush or eraser)
        self._dab_is_eraser: bool = False

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

    def set_transform_box(self, box: tuple[int, int, int, int] | None,
                          angle: float = 0.0) -> None:
        """Set the bounding box for the active layer (doc coords: x, y, w, h)."""
        self._transform_box = box
        self._transform_angle = angle
        self.update()

    def set_tool_cursor(self, tool_type: ToolType) -> None:
        shape = _CURSORS.get(tool_type, Qt.CursorShape.ArrowCursor)
        self.setCursor(QCursor(shape))

    # ---- Brush cursor / live dab preview ------------------------------------

    def set_brush_dab(self, dab_rgba: np.ndarray | None,
                      is_eraser: bool = False) -> None:
        """Set the pre-computed dab preview (RGBA uint8).

        For a **brush** the dab is drawn directly (paint colour + hardness).
        For an **eraser** the dab's alpha channel is used to shape a
        checkerboard pattern that previews the transparency to be created.
        """
        if dab_rgba is None or dab_rgba.size == 0:
            self._dab_pixmap = None
            self._brush_size = 0
            self._dab_is_eraser = False
            self.update()
            return

        h, w = dab_rgba.shape[:2]
        self._brush_size = w  # diameter in doc pixels
        self._dab_is_eraser = is_eraser

        if is_eraser:
            # Build a checkerboard image shaped by the eraser's alpha mask.
            # This shows exactly the transparency pattern the eraser will
            # create, following the tool's hardness / opacity / future shapes.
            alpha = dab_rgba[..., 3]  # uint8, 0-255
            cs = max(2, w // 8)       # checker square size
            yy, xx = np.mgrid[0:h, 0:w]
            parity = ((yy // cs) + (xx // cs)) % 2
            checker = np.zeros((h, w, 4), dtype=np.uint8)
            checker[..., :3] = np.where(parity[..., None] == 0, 230, 180)
            checker[..., 3] = alpha   # shaped by the eraser dab
            qimg = QImage(checker.data, w, h, w * 4,
                          QImage.Format.Format_RGBA8888)
            self._dab_pixmap = QPixmap.fromImage(qimg.copy())
        else:
            # Convert the RGBA dab straight into a QPixmap
            qimg = QImage(dab_rgba.data, w, h, w * 4,
                          QImage.Format.Format_RGBA8888)
            self._dab_pixmap = QPixmap.fromImage(qimg.copy())

        self.update()

    def hide_brush_preview(self) -> None:
        self._dab_pixmap = None
        self._brush_size = 0
        self._brush_cursor_visible = False
        self.update()

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

        # Transform bounding box with handles
        if self._transform_box is not None:
            self._draw_transform_box(p, dr)

        # Brush cursor preview circle
        if self._brush_size > 0 and self._brush_cursor_visible:
            self._draw_brush_cursor(p)

        p.end()

    # ---- Transform box -------------------------------------------------------

    def _box_widget_rect(self, dr: QRectF) -> QRectF | None:
        """Return the transform box rectangle in widget coordinates."""
        if self._transform_box is None or self._doc_w == 0 or self._doc_h == 0:
            return None
        x, y, w, h = self._transform_box
        sx = dr.width() / self._doc_w
        sy = dr.height() / self._doc_h
        return QRectF(dr.left() + x * sx, dr.top() + y * sy, w * sx, h * sy)

    def _handle_positions(self, br: QRectF) -> list[tuple[str, float, float]]:
        """Return handle (name, cx, cy) in widget coordinates."""
        x, y = br.x(), br.y()
        w, h = br.width(), br.height()
        return [
            ("TL", x, y), ("T", x + w / 2, y), ("TR", x + w, y),
            ("L", x, y + h / 2), ("R", x + w, y + h / 2),
            ("BL", x, y + h), ("B", x + w / 2, y + h), ("BR", x + w, y + h),
        ]

    def _draw_transform_box(self, p: QPainter, dr: QRectF) -> None:
        br = self._box_widget_rect(dr)
        if br is None:
            return

        cx = br.x() + br.width() / 2
        cy = br.y() + br.height() / 2
        hw, hh = br.width() / 2, br.height() / 2

        p.save()
        p.translate(cx, cy)
        if self._transform_angle != 0.0:
            # QPainter rotates clockwise for positive angles;
            # TransformEngine (cv2) rotates counter-clockwise for positive.
            p.rotate(-self._transform_angle)

        # Outer rectangle (centered at origin)
        p.setPen(QPen(QColor(0, 150, 255), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(-hw, -hh, br.width(), br.height()))

        # Handle squares
        hs = 7
        handle_pts = [
            (-hw, -hh), (0, -hh), (hw, -hh),
            (-hw, 0), (hw, 0),
            (-hw, hh), (0, hh), (hw, hh),
        ]
        p.setPen(QPen(QColor(0, 150, 255), 1))
        p.setBrush(QColor(255, 255, 255))
        for hx, hy in handle_pts:
            p.drawRect(QRectF(hx - hs / 2, hy - hs / 2, hs, hs))

        p.restore()

    def _update_transform_cursor(self, pos: QPointF) -> None:
        """Adjust cursor shape when hovering over the transform box / handles."""
        dr = self._doc_rect()
        br = self._box_widget_rect(dr)
        if br is None:
            return

        cx = br.x() + br.width() / 2
        cy = br.y() + br.height() / 2
        hw, hh = br.width() / 2, br.height() / 2

        # Inverse-rotate the mouse position into the box's local frame
        px, py = pos.x() - cx, pos.y() - cy
        if self._transform_angle != 0.0:
            rad = math.radians(self._transform_angle)
            rx = px * math.cos(rad) - py * math.sin(rad)
            ry = px * math.sin(rad) + py * math.cos(rad)
            px, py = rx, ry

        # Hit-test against centered handle positions
        local_handles = [
            ("TL", -hw, -hh), ("T", 0, -hh), ("TR", hw, -hh),
            ("L", -hw, 0), ("R", hw, 0),
            ("BL", -hw, hh), ("B", 0, hh), ("BR", hw, hh),
        ]
        for name, hx, hy in local_handles:
            if abs(px - hx) <= _HANDLE_HIT and abs(py - hy) <= _HANDLE_HIT:
                self.setCursor(QCursor(_HANDLE_CURSORS[name]))
                return

        if -hw <= px <= hw and -hh <= py <= hh:
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    # ---- Brush cursor drawing -----------------------------------------------

    def _draw_brush_cursor(self, p: QPainter) -> None:
        """Draw a live preview of the actual dab that will be applied."""
        pos = self._brush_cursor_pos
        radius_screen = (self._brush_size / 2) * self._zoom

        # Don't draw if it's tiny (< 2px on screen) — crosshair suffices
        if radius_screen < 1.5:
            return

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        dab_screen = radius_screen * 2  # full diameter on screen
        target = QRectF(pos.x() - radius_screen, pos.y() - radius_screen,
                        dab_screen, dab_screen)

        # ---- Draw the actual dab preview ----
        if self._dab_pixmap is not None:
            p.drawPixmap(target.toAlignedRect(), self._dab_pixmap)

        # ---- Outline ring (thin, clean) ----
        pen_outer = QPen(QColor(0, 0, 0, 160), 1.0)
        pen_outer.setCosmetic(True)
        p.setPen(pen_outer)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(pos, radius_screen, radius_screen)

        pen_inner = QPen(QColor(255, 255, 255, 180), 1.0)
        pen_inner.setCosmetic(True)
        pen_inner.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen_inner)
        p.drawEllipse(pos, radius_screen, radius_screen)

        # Crosshair at center
        ch = max(3.0, min(radius_screen * 0.12, 6.0))
        p.setPen(QPen(QColor(255, 255, 255, 200), 1.0))
        p.drawLine(QPointF(pos.x() - ch, pos.y()), QPointF(pos.x() + ch, pos.y()))
        p.drawLine(QPointF(pos.x(), pos.y() - ch), QPointF(pos.x(), pos.y() + ch))

        p.restore()

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

        # Update brush cursor position and visibility
        if self._brush_size > 0:
            self._brush_cursor_pos = event.position()
            self._brush_cursor_visible = True
            self.update()

        if event.buttons() & Qt.MouseButton.LeftButton:
            self.tool_moved.emit(dx, dy, 1.0)
        elif self._transform_box is not None:
            self._update_transform_cursor(event.position())

    def leaveEvent(self, _event) -> None:
        self._brush_cursor_visible = False
        self.update()

    def enterEvent(self, _event) -> None:
        if self._brush_size > 0:
            self._brush_cursor_visible = True
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            # Restore tool cursor
        elif event.button() == Qt.MouseButton.LeftButton:
            dx, dy = self._canvas_to_doc(event.position())
            self.tool_released.emit(dx, dy)
            self._drag_rect = None
