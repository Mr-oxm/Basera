"""Zoomable, pannable canvas with selection overlay, transform box, tool cursors,
and in-canvas text editing overlay (cursor, selection highlight, text box).

Uses ``QOpenGLWidget`` when available so all QPainter operations are
GPU-accelerated.  Falls back to the software ``QWidget`` path
transparently.
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF, QTimer, Signal
from PySide6.QtGui import (
    QColor, QCursor, QImage, QKeyEvent, QLinearGradient, QMouseEvent,
    QPainter, QPainterPath, QPen, QPixmap, QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QWidget

try:
    from PySide6.QtOpenGLWidgets import QOpenGLWidget
    _BASE_CLASS = QOpenGLWidget
except ImportError:
    _BASE_CLASS = QWidget

from ..core.enums import ToolType

# Pre-built checkerboard tile (fast)
_CHECKER_SIZE = 16
_CHECKER_TILE: QPixmap | None = None

# Custom gradient cursor (built lazily)
_GRADIENT_CURSOR: QCursor | None = None


def _make_gradient_cursor() -> QCursor:
    """Build a crosshair cursor with a tiny gradient swatch indicator."""
    size = 32
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy = size // 2, size // 2

    # Outer thin crosshair (black shadow)
    pen = QPen(QColor(0, 0, 0, 160), 1.4)
    pen.setCosmetic(True)
    p.setPen(pen)
    gap = 4
    arm = 10
    p.drawLine(cx, cy - arm, cx, cy - gap)
    p.drawLine(cx, cy + gap, cx, cy + arm)
    p.drawLine(cx - arm, cy, cx - gap, cy)
    p.drawLine(cx + gap, cy, cx + arm, cy)

    # Inner white crosshair
    pen2 = QPen(QColor(255, 255, 255, 230), 1.0)
    pen2.setCosmetic(True)
    p.setPen(pen2)
    p.drawLine(cx, cy - arm, cx, cy - gap)
    p.drawLine(cx, cy + gap, cx, cy + arm)
    p.drawLine(cx - arm, cy, cx - gap, cy)
    p.drawLine(cx + gap, cy, cx + arm, cy)

    # Small gradient rectangle at bottom-right
    gx, gy, gw, gh = cx + 3, cy + 3, 9, 7
    grad = QLinearGradient(gx, gy, gx + gw, gy)
    grad.setColorAt(0.0, QColor(0, 0, 0))
    grad.setColorAt(1.0, QColor(255, 255, 255))
    p.setPen(QPen(QColor(160, 160, 160), 0.8))
    p.setBrush(grad)
    p.drawRoundedRect(gx, gy, gw, gh, 1.5, 1.5)

    p.end()
    return QCursor(pm, cx, cy)


def _gradient_cursor() -> QCursor:
    global _GRADIENT_CURSOR
    if _GRADIENT_CURSOR is None:
        _GRADIENT_CURSOR = _make_gradient_cursor()
    return _GRADIENT_CURSOR


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


class CanvasView(_BASE_CLASS):
    """Interactive canvas that displays the composited document.

    Inherits from QOpenGLWidget when available (GPU-accelerated QPainter),
    otherwise falls back to QWidget (software rasterizer).
    """

    cursor_moved = Signal(int, int)
    tool_pressed = Signal(int, int, float)
    tool_moved = Signal(int, int, float)
    tool_released = Signal(int, int)
    # Widget-coordinate signals (for pan tool / raw screen deltas)
    widget_pressed = Signal(float, float)
    widget_moved = Signal(float, float)
    widget_released = Signal()
    # Emitted whenever zoom or pan changes (for ruler sync)
    view_changed = Signal()
    # Guide interaction on canvas
    guide_grabbed = Signal(object)          # Guide
    guide_drag_moved = Signal(object, float)  # Guide, new doc position
    guide_drag_released = Signal(object, float, bool)  # Guide, pos, delete?

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self._last_mouse = QPointF()
        self._panning = False
        self._doc_w = 0
        self._doc_h = 0
        # Selection overlay — marching ants
        self._sel_mask: np.ndarray | None = None
        self._sel_contours: list | None = None  # list of QPolygonF for marching ants
        self._march_offset: int = 0               # animated dash offset
        self._march_timer = QTimer(self)
        self._march_timer.setInterval(100)         # ~10 fps animation
        self._march_timer.timeout.connect(self._march_tick)
        # Drag rect feedback for selection tools
        self._drag_rect: QRectF | None = None
        self._drag_is_ellipse: bool = False  # True → draw ellipse instead of rect
        # Lasso path preview (list of (x, y) doc coords)
        self._lasso_points: list[tuple[int, int]] | None = None
        # Transform bounding box (x, y, w, h) in document coordinates
        self._transform_box: tuple[int, int, int, int] | None = None
        self._transform_angle: float = 0.0  # rotation angle in degrees
        # Brush cursor / live dab preview
        self._brush_size: int = 0       # diameter in document pixels (0 = hidden)
        self._brush_cursor_pos: QPointF = QPointF()   # last mouse widget pos
        self._brush_cursor_visible: bool = False
        self._dab_pixmap: QPixmap | None = None       # pre-computed dab (brush or eraser)
        self._dab_is_eraser: bool = False
        # Cache identity of last rgba buffer to skip redundant QPixmap builds
        self._last_rgba: np.ndarray | None = None

        # Text editing overlay state
        self._text_cursor_pos: tuple[int, int] | None = None   # (x, y) in doc coords
        self._text_cursor_height: int = 20
        self._text_cursor_visible: bool = False     # blink state
        self._text_editing: bool = False
        self._text_box: tuple[int, int, int, int] | None = None  # (x, y, w, h)
        self._text_box_angle: float = 0.0
        self._text_draw_rect: tuple[int, int, int, int] | None = None  # drawing preview
        self._text_selection_rects: list[tuple[int, int, int, int]] = []  # selection highlight
        # Cursor blink timer
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(530)
        self._blink_timer.timeout.connect(self._blink_cursor)
        # Key event forwarding for text editing
        self._key_handler = None  # callable(key, text, modifiers) -> bool

        # Gradient handle overlay state
        self._grad_start: tuple[int, int] | None = None   # doc coords
        self._grad_end: tuple[int, int] | None = None
        self._grad_stops: list = []                        # GradientStop list
        self._grad_handles_visible: bool = False

        # Clone / Heal source overlay state
        self._current_tool_type: ToolType | None = None
        self._source_pos: tuple[int, int] | None = None    # doc coords of source
        self._source_offset: tuple[int, int] | None = None  # (ox, oy) offset locked
        self._source_drawing: bool = False                  # True while painting
        self._clone_preview_pixmap: QPixmap | None = None   # live preview of source patch
        self._alt_held: bool = False                         # Alt modifier is held

        # Crop bounding box overlay state
        self._crop_box: tuple[int, int, int, int] | None = None  # (x, y, w, h) doc coords

        # Guide lines (list of guide objects with .orientation and .position)
        self._guide_lines: list = []
        # Preview guide (shown while dragging from ruler before release)
        self._preview_guide = None   # Guide or None
        # Guide dragging on canvas
        self._dragging_canvas_guide = None  # Guide being dragged on canvas
        self._guide_snap_px = 6  # pixel hit-test distance for guides

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(200, 200)

    # ---- Public API ---------------------------------------------------------

    def set_image(self, rgba: np.ndarray, force: bool = False) -> None:
        # Skip redundant QPixmap creation when the buffer is identical
        if not force and rgba is self._last_rgba:
            return
        self._last_rgba = rgba
        h, w = rgba.shape[:2]
        self._doc_w, self._doc_h = w, h
        # Use the buffer directly without .copy() — QPixmap.fromImage
        # copies the data internally so we don't need a second copy.
        qimg = QImage(rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
        self._pixmap = QPixmap.fromImage(qimg)
        self.update()

    def set_selection_mask(self, mask: np.ndarray | None) -> None:
        """Set the selection mask for marching-ants overlay rendering."""
        if mask is None:
            if self._sel_mask is None:
                return  # already cleared
            self._sel_mask = None
            self._sel_contours = None
            self._march_timer.stop()
            self.update()
            return
        self._sel_mask = mask
        # Extract contours from the binary mask for marching ants
        import cv2
        mask_u8 = (np.clip(mask, 0, 1) * 255).astype(np.uint8)
        contours, _ = cv2.findContours(mask_u8, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        from PySide6.QtGui import QPolygonF
        polys = []
        for c in contours:
            if len(c) < 2:
                continue
            pts = [QPointF(float(pt[0][0]), float(pt[0][1])) for pt in c]
            pts.append(pts[0])  # close the polygon
            polys.append(QPolygonF(pts))
        self._sel_contours = polys
        if polys:
            self._march_timer.start()
        else:
            self._march_timer.stop()
        self.update()

    def _march_tick(self) -> None:
        """Advance marching ants animation by one step."""
        self._march_offset = (self._march_offset + 1) % 16
        self.update()

    def set_drag_rect(self, rect: QRectF | None, ellipse: bool = False) -> None:
        self._drag_rect = rect
        self._drag_is_ellipse = ellipse
        self.update()

    def set_lasso_points(self, points: list[tuple[int, int]] | None) -> None:
        """Set lasso path preview points (doc coords) or None to clear."""
        self._lasso_points = points
        self.update()

    def set_transform_box(self, box: tuple[int, int, int, int] | None,
                          angle: float = 0.0) -> None:
        """Set the bounding box for the active layer (doc coords: x, y, w, h)."""
        self._transform_box = box
        self._transform_angle = angle
        self.update()

    def set_tool_cursor(self, tool_type: ToolType) -> None:
        self._current_tool_type = tool_type
        if tool_type == ToolType.GRADIENT:
            self.setCursor(_gradient_cursor())
            return
        shape = _CURSORS.get(tool_type, Qt.CursorShape.ArrowCursor)
        self.setCursor(QCursor(shape))

    # ---- Crop bounding box overlay API ------------------------------------

    def set_crop_box(self, box: tuple[int, int, int, int] | None) -> None:
        """Set / clear the crop bounding box overlay (doc coords: x, y, w, h)."""
        self._crop_box = box
        self.update()

    def set_guides(self, guides: list) -> None:
        """Set the guide lines to draw (objects with .orientation and .position)."""
        self._guide_lines = list(guides)
        self.update()

    def set_preview_guide(self, guide) -> None:
        """Set a temporary preview guide (or None to clear)."""
        self._preview_guide = guide
        self.update()

    # ---- Clone / Heal source overlay API ------------------------------------

    def set_source_position(self, pos: tuple[int, int] | None) -> None:
        """Set/clear the clone/heal source position (doc coords)."""
        self._source_pos = pos
        self.update()

    def set_source_offset(self, offset: tuple[int, int] | None) -> None:
        """Set the locked source offset (ox, oy) during a paint stroke."""
        self._source_offset = offset

    def set_source_drawing(self, drawing: bool) -> None:
        """Toggle whether a clone/heal stroke is in progress."""
        self._source_drawing = drawing
        if not drawing:
            self._clone_preview_pixmap = None

    def set_clone_preview(self, preview_rgba: np.ndarray | None) -> None:
        """Set the live clone/heal preview patch (RGBA uint8)."""
        if preview_rgba is None or preview_rgba.size == 0:
            self._clone_preview_pixmap = None
            self.update()
            return
        h, w = preview_rgba.shape[:2]
        qimg = QImage(preview_rgba.data, w, h, w * 4,
                      QImage.Format.Format_RGBA8888)
        self._clone_preview_pixmap = QPixmap.fromImage(qimg.copy())
        self.update()

    # ---- Text editing overlay API -------------------------------------------

    def set_text_editing(self, editing: bool) -> None:
        """Enable / disable text editing overlay."""
        self._text_editing = editing
        if editing:
            self._text_cursor_visible = True
            self._blink_timer.start()
        else:
            self._blink_timer.stop()
            self._text_cursor_visible = False
            self._text_cursor_pos = None
            self._text_box = None
            self._text_draw_rect = None
            self._text_selection_rects = []
        self.update()

    def set_text_cursor(self, x: int, y: int, height: int) -> None:
        """Set the text cursor position in document coordinates."""
        self._text_cursor_pos = (x, y)
        self._text_cursor_height = height
        self._text_cursor_visible = True
        self._blink_timer.start()
        self.update()

    def set_text_box(self, box: tuple[int, int, int, int] | None,
                     angle: float = 0.0) -> None:
        """Set the text bounding box (doc coords) for overlay drawing."""
        self._text_box = box
        self._text_box_angle = angle
        self.update()

    def set_text_draw_rect(self, rect: tuple[int, int, int, int] | None) -> None:
        """Set the text box drawing preview rectangle (doc coords)."""
        self._text_draw_rect = rect
        self.update()

    def set_text_selection_rects(self, rects: list[tuple[int, int, int, int]]) -> None:
        """Set selection highlight rectangles (doc coords relative to text box)."""
        self._text_selection_rects = rects
        self.update()

    def set_key_handler(self, handler) -> None:
        """Set the key event handler for text editing.
        handler(key: int, text: str, modifiers: Qt.KeyboardModifier) -> bool"""
        self._key_handler = handler

    def _blink_cursor(self) -> None:
        self._text_cursor_visible = not self._text_cursor_visible
        self.update()

    # ---- Gradient handle overlay API ----------------------------------------

    def set_gradient_handles(
        self,
        start: tuple[int, int] | None,
        end: tuple[int, int] | None,
        stops: list,
        visible: bool,
    ) -> None:
        """Set / clear the gradient control-line overlay (doc coords)."""
        self._grad_start = start
        self._grad_end = end
        self._grad_stops = list(stops) if stops else []
        self._grad_handles_visible = visible
        self.update()

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
        self.view_changed.emit()

    def zoom_to_fit(self) -> None:
        if self._doc_w and self._doc_h:
            sx = self.width() / self._doc_w
            sy = self.height() / self._doc_h
            self._zoom = min(sx, sy) * 0.9
            self._pan = QPointF(0, 0)
            self.update()
            self.view_changed.emit()

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

        # Checkerboard — single hardware-accelerated tiled draw
        p.save()
        p.setClipRect(dr.toAlignedRect())
        p.drawTiledPixmap(dr.toAlignedRect(), _checker_tile())
        p.restore()

        # Document image
        p.drawPixmap(dr.toAlignedRect(), self._pixmap)

        # Selection overlay — marching ants
        if self._sel_contours:
            self._draw_marching_ants(p, dr)

        # Selection drag rectangle / ellipse
        if self._drag_rect is not None:
            pen = QPen(QColor(100, 180, 255), 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(QColor(100, 180, 255, 30))
            if self._drag_is_ellipse:
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.drawEllipse(self._drag_rect)
            else:
                p.drawRect(self._drag_rect)

        # Lasso path preview
        if self._lasso_points and len(self._lasso_points) > 1 and self._doc_w > 0:
            from PySide6.QtGui import QPolygonF as _QPolyF
            pen = QPen(QColor(100, 180, 255), 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            poly = _QPolyF()
            for lx, ly in self._lasso_points:
                sx = dr.left() + (lx / self._doc_w) * dr.width()
                sy = dr.top() + (ly / self._doc_h) * dr.height()
                poly.append(QPointF(sx, sy))
            # Close back to start
            lx0, ly0 = self._lasso_points[0]
            poly.append(QPointF(
                dr.left() + (lx0 / self._doc_w) * dr.width(),
                dr.top() + (ly0 / self._doc_h) * dr.height(),
            ))
            p.drawPolyline(poly)

        # Transform bounding box with handles
        if self._transform_box is not None:
            self._draw_transform_box(p, dr)

        # Text editing overlays
        if self._text_draw_rect is not None:
            self._draw_text_draw_rect(p, dr)
        if self._text_box is not None:
            self._draw_text_box(p, dr)
        if self._text_selection_rects:
            self._draw_text_selection(p, dr)
        if self._text_cursor_pos is not None and self._text_cursor_visible and self._text_editing:
            self._draw_text_cursor(p, dr)

        # Brush cursor preview circle
        if self._brush_size > 0 and self._brush_cursor_visible:
            self._draw_brush_cursor(p)

        # Clone / Heal source crosshair and live preview
        if (self._source_pos is not None
                and self._current_tool_type in (ToolType.CLONE_STAMP, ToolType.HEALING_BRUSH)):
            self._draw_source_overlay(p, dr)

        # Crop bounding box with dimmed surround
        if self._crop_box is not None:
            self._draw_crop_box(p, dr)

        # Gradient control line + stop handles
        if self._grad_handles_visible:
            self._draw_gradient_handles(p, dr)

        # Guide lines overlay (including preview guide)
        if self._guide_lines or self._preview_guide is not None:
            self._draw_guides(p, dr)

        p.end()

    # ---- Marching ants (selection contour) -----------------------------------

    def _draw_marching_ants(self, p: QPainter, dr: QRectF) -> None:
        """Draw animated marching-ants contour from the selection mask."""
        if not self._sel_contours or self._doc_w == 0 or self._doc_h == 0:
            return
        sx = dr.width() / self._doc_w
        sy = dr.height() / self._doc_h

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Background stroke (white) so ants are visible on any colour
        bg_pen = QPen(QColor(255, 255, 255), 1.0, Qt.PenStyle.SolidLine)
        bg_pen.setCosmetic(True)
        p.setPen(bg_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for poly in self._sel_contours:
            mapped = self._map_polygon_to_screen(poly, dr, sx, sy)
            p.drawPolyline(mapped)

        # Foreground stroke (black dashes) animated
        fg_pen = QPen(QColor(0, 0, 0), 1.0, Qt.PenStyle.DashLine)
        fg_pen.setCosmetic(True)
        fg_pen.setDashOffset(float(self._march_offset))
        p.setPen(fg_pen)
        for poly in self._sel_contours:
            mapped = self._map_polygon_to_screen(poly, dr, sx, sy)
            p.drawPolyline(mapped)

        p.restore()

    def _map_polygon_to_screen(self, poly, dr: QRectF,
                                sx: float, sy: float):
        """Map a QPolygonF from document coords to screen coords."""
        from PySide6.QtGui import QPolygonF
        pts = []
        for i in range(poly.count()):
            pt = poly.at(i)
            pts.append(QPointF(dr.left() + pt.x() * sx,
                               dr.top() + pt.y() * sy))
        return QPolygonF(pts)

    # ---- Crop box drawing ----------------------------------------------------

    def _draw_crop_box(self, p: QPainter, dr: QRectF) -> None:
        """Draw the crop bounding box with dimmed outside area and handles."""
        if self._crop_box is None or self._doc_w == 0 or self._doc_h == 0:
            return
        x, y, w, h = self._crop_box
        sx = dr.width() / self._doc_w
        sy = dr.height() / self._doc_h
        crop_rect = QRectF(dr.left() + x * sx, dr.top() + y * sy, w * sx, h * sy)

        p.save()

        # -- Dim the area outside the crop region --
        dim_path = QPainterPath()
        dim_path.addRect(dr)
        inner_path = QPainterPath()
        inner_path.addRect(crop_rect)
        dim_path = dim_path.subtracted(inner_path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 140))
        p.drawPath(dim_path)

        # -- Crop rectangle outline --
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(220, 50, 50, 230), 1.5)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(crop_rect)

        # -- Rule-of-thirds grid lines --
        pen_grid = QPen(QColor(220, 50, 50, 80), 1.0)
        pen_grid.setCosmetic(True)
        pen_grid.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen_grid)
        for i in (1, 2):
            gx = crop_rect.left() + crop_rect.width() * i / 3
            p.drawLine(QPointF(gx, crop_rect.top()), QPointF(gx, crop_rect.bottom()))
            gy = crop_rect.top() + crop_rect.height() * i / 3
            p.drawLine(QPointF(crop_rect.left(), gy), QPointF(crop_rect.right(), gy))

        # -- Corner and edge handles --
        hs = 7
        handle_pts = [
            (crop_rect.left(), crop_rect.top()),
            (crop_rect.left() + crop_rect.width() / 2, crop_rect.top()),
            (crop_rect.right(), crop_rect.top()),
            (crop_rect.left(), crop_rect.top() + crop_rect.height() / 2),
            (crop_rect.right(), crop_rect.top() + crop_rect.height() / 2),
            (crop_rect.left(), crop_rect.bottom()),
            (crop_rect.left() + crop_rect.width() / 2, crop_rect.bottom()),
            (crop_rect.right(), crop_rect.bottom()),
        ]
        p.setPen(QPen(QColor(220, 50, 50, 230), 1))
        p.setBrush(QColor(255, 255, 255))
        for hx, hy in handle_pts:
            p.drawRect(QRectF(hx - hs / 2, hy - hs / 2, hs, hs))

        p.restore()

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

        # ---- Live clone/heal preview (translucent source patch) ----
        if self._clone_preview_pixmap is not None:
            p.setOpacity(1.0)
            p.drawPixmap(target.toAlignedRect(), self._clone_preview_pixmap)
            p.setOpacity(1.0)

        p.restore()

    # ---- Clone / Heal source overlay drawing --------------------------------

    def _draw_source_overlay(self, p: QPainter, dr: QRectF) -> None:
        """Draw a crosshair at the clone/heal source position.

        The source crosshair always tracks the cursor with the offset so the
        user can see exactly which region will be sampled.
        """
        if self._source_pos is None or self._doc_w == 0 or self._doc_h == 0:
            return

        sx_scale = dr.width() / self._doc_w
        sy_scale = dr.height() / self._doc_h

        # Always compute source position relative to the current cursor
        if self._source_offset is not None and self._brush_cursor_visible:
            doc_pos = self._canvas_to_doc(self._brush_cursor_pos)
            src_x = doc_pos[0] + self._source_offset[0]
            src_y = doc_pos[1] + self._source_offset[1]
        else:
            src_x, src_y = self._source_pos

        # Convert to widget coords
        wx = dr.left() + src_x * sx_scale
        wy = dr.top() + src_y * sy_scale

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        arm = 12.0
        gap = 4.0

        # Outer black crosshair
        pen_outer = QPen(QColor(0, 0, 0, 200), 1.6)
        pen_outer.setCosmetic(True)
        p.setPen(pen_outer)
        p.drawLine(QPointF(wx, wy - arm), QPointF(wx, wy - gap))
        p.drawLine(QPointF(wx, wy + gap), QPointF(wx, wy + arm))
        p.drawLine(QPointF(wx - arm, wy), QPointF(wx - gap, wy))
        p.drawLine(QPointF(wx + arm, wy), QPointF(wx + gap, wy))

        # Inner coloured crosshair (cyan for visibility)
        pen_inner = QPen(QColor(0, 220, 255, 230), 1.0)
        pen_inner.setCosmetic(True)
        p.setPen(pen_inner)
        p.drawLine(QPointF(wx, wy - arm), QPointF(wx, wy - gap))
        p.drawLine(QPointF(wx, wy + gap), QPointF(wx, wy + arm))
        p.drawLine(QPointF(wx - arm, wy), QPointF(wx - gap, wy))
        p.drawLine(QPointF(wx + arm, wy), QPointF(wx + gap, wy))

        # Small circle at center
        p.setPen(QPen(QColor(0, 220, 255, 200), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(wx, wy), 3.0, 3.0)

        # If brush size is known, also draw the source circle outline
        if self._brush_size > 0:
            src_radius = (self._brush_size / 2) * self._zoom
            pen_src = QPen(QColor(0, 220, 255, 120), 1.0)
            pen_src.setCosmetic(True)
            pen_src.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen_src)
            p.drawEllipse(QPointF(wx, wy), src_radius, src_radius)

        p.restore()

    # ---- Gradient handle overlay drawing ------------------------------------

    def _draw_gradient_handles(self, p: QPainter, dr: QRectF) -> None:
        """Draw the gradient control line with coloured stop circles."""
        if not self._grad_start or not self._grad_end:
            return
        if self._doc_w == 0 or self._doc_h == 0:
            return

        sx = dr.width() / self._doc_w
        sy = dr.height() / self._doc_h

        s = QPointF(dr.left() + self._grad_start[0] * sx,
                     dr.top() + self._grad_start[1] * sy)
        e = QPointF(dr.left() + self._grad_end[0] * sx,
                     dr.top() + self._grad_end[1] * sy)

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ---- Control line (dark shadow + bright inner) ----
        pen_shadow = QPen(QColor(0, 0, 0, 100), 3.0)
        pen_shadow.setCosmetic(True)
        p.setPen(pen_shadow)
        p.drawLine(s, e)

        pen_line = QPen(QColor(255, 255, 255, 200), 1.4)
        pen_line.setCosmetic(True)
        p.setPen(pen_line)
        p.drawLine(s, e)

        # ---- Intermediate stop circles (small) ----
        for stop in self._grad_stops:
            if stop.position <= 0.0 or stop.position >= 1.0:
                continue
            cx = s.x() + (e.x() - s.x()) * stop.position
            cy = s.y() + (e.y() - s.y()) * stop.position
            r, g, b, a = stop.color.to_rgb8()
            p.setPen(QPen(QColor(255, 255, 255, 220), 1.4))
            p.setBrush(QColor(r, g, b, a))
            p.drawEllipse(QPointF(cx, cy), 5.0, 5.0)

        # ---- Start endpoint handle ----
        if self._grad_stops:
            r0, g0, b0, a0 = self._grad_stops[0].color.to_rgb8()
        else:
            r0, g0, b0, a0 = 0, 0, 0, 255
        # Shadow ring
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawEllipse(s, 10.0, 10.0)
        # Fill + border
        p.setPen(QPen(QColor(255, 255, 255), 2.0))
        p.setBrush(QColor(r0, g0, b0, a0))
        p.drawEllipse(s, 8.0, 8.0)

        # ---- End endpoint handle ----
        if self._grad_stops:
            r1, g1, b1, a1 = self._grad_stops[-1].color.to_rgb8()
        else:
            r1, g1, b1, a1 = 255, 255, 255, 255
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawEllipse(e, 10.0, 10.0)
        p.setPen(QPen(QColor(255, 255, 255), 2.0))
        p.setBrush(QColor(r1, g1, b1, a1))
        p.drawEllipse(e, 8.0, 8.0)

        p.restore()

    # ---- Guide lines overlay ------------------------------------------------

    def _draw_guides(self, p: QPainter, dr: QRectF) -> None:
        """Draw horizontal and vertical guide lines across the full canvas."""
        all_guides = list(self._guide_lines)
        preview = self._preview_guide
        if not all_guides and preview is None:
            return
        if self._doc_w == 0 or self._doc_h == 0:
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        guide_pen = QPen(QColor(74, 179, 255, 180), 1.0, Qt.PenStyle.DashLine)
        guide_pen.setCosmetic(True)
        preview_pen = QPen(QColor(74, 179, 255, 100), 1.0, Qt.PenStyle.DashLine)
        preview_pen.setCosmetic(True)
        p.setBrush(Qt.BrushStyle.NoBrush)

        sx = dr.width() / self._doc_w
        sy = dr.height() / self._doc_h

        def _draw_one(g, pen):
            p.setPen(pen)
            if g.orientation == Qt.Orientation.Vertical:
                wx = dr.left() + g.position * sx
                p.drawLine(QPointF(wx, 0), QPointF(wx, self.height()))
            else:  # Horizontal
                wy = dr.top() + g.position * sy
                p.drawLine(QPointF(0, wy), QPointF(self.width(), wy))

        for g in all_guides:
            _draw_one(g, guide_pen)

        if preview is not None:
            _draw_one(preview, preview_pen)

        p.restore()

    def _hit_test_guide(self, pos: QPointF):
        """Return the Guide object near *pos* (widget coords), or None."""
        if not self._guide_lines or self._doc_w == 0 or self._doc_h == 0:
            return None
        dr = self._doc_rect()
        sx = dr.width() / self._doc_w
        sy = dr.height() / self._doc_h
        snap = self._guide_snap_px
        for g in self._guide_lines:
            if g.orientation == Qt.Orientation.Horizontal:
                wy = dr.top() + g.position * sy
                if abs(pos.y() - wy) <= snap:
                    return g
            else:  # Vertical
                wx = dr.left() + g.position * sx
                if abs(pos.x() - wx) <= snap:
                    return g
        return None

    # ---- Text overlay drawing -----------------------------------------------

    def _doc_to_widget(self, dr: QRectF, dx: float, dy: float) -> QPointF:
        """Convert document coords to widget coords."""
        sx = dr.width() / self._doc_w if self._doc_w else 1
        sy = dr.height() / self._doc_h if self._doc_h else 1
        return QPointF(dr.left() + dx * sx, dr.top() + dy * sy)

    def _draw_text_cursor(self, p: QPainter, dr: QRectF) -> None:
        """Draw the blinking text cursor."""
        if self._text_cursor_pos is None:
            return
        cx, cy = self._text_cursor_pos
        h = self._text_cursor_height

        # If there's a text box with rotation, apply rotation
        if self._text_box is not None and self._text_box_angle != 0.0:
            bx, by, bw, bh = self._text_box
            box_cx = bx + bw / 2.0
            box_cy = by + bh / 2.0
            wc = self._doc_to_widget(dr, box_cx, box_cy)
            p.save()
            p.translate(wc.x(), wc.y())
            p.rotate(-self._text_box_angle)
            # Draw cursor relative to box center
            sx = dr.width() / self._doc_w if self._doc_w else 1
            sy = dr.height() / self._doc_h if self._doc_h else 1
            lcx = (bx + cx - box_cx) * sx
            lcy = (by + cy - box_cy) * sy
            lh = h * sy
            p.setPen(QPen(QColor(255, 255, 255), 2))
            p.drawLine(QPointF(lcx, lcy), QPointF(lcx, lcy + lh))
            p.setPen(QPen(QColor(0, 0, 0), 1))
            p.drawLine(QPointF(lcx, lcy), QPointF(lcx, lcy + lh))
            p.restore()
        else:
            # No rotation
            top = self._doc_to_widget(dr, cx + (self._text_box[0] if self._text_box else 0),
                                      cy + (self._text_box[1] if self._text_box else 0))
            bot = self._doc_to_widget(dr, cx + (self._text_box[0] if self._text_box else 0),
                                      cy + h + (self._text_box[1] if self._text_box else 0))
            p.setPen(QPen(QColor(255, 255, 255), 2))
            p.drawLine(top, bot)
            p.setPen(QPen(QColor(0, 0, 0), 1))
            p.drawLine(top, bot)

    def _draw_text_box(self, p: QPainter, dr: QRectF) -> None:
        """Draw the text bounding box with resize handles."""
        if self._text_box is None or self._doc_w == 0:
            return
        x, y, w, h = self._text_box
        sx = dr.width() / self._doc_w
        sy = dr.height() / self._doc_h

        p.save()
        if self._text_box_angle != 0.0:
            cx = x + w / 2.0
            cy = y + h / 2.0
            wc = self._doc_to_widget(dr, cx, cy)
            p.translate(wc.x(), wc.y())
            p.rotate(-self._text_box_angle)
            hw, hh = w * sx / 2, h * sy / 2
        else:
            tl = self._doc_to_widget(dr, x, y)
            p.translate(tl.x() + w * sx / 2, tl.y() + h * sy / 2)
            hw, hh = w * sx / 2, h * sy / 2

        # Dashed box
        pen = QPen(QColor(0, 150, 255), 1.5, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(-hw, -hh, hw * 2, hh * 2))

        # Handles
        hs = 6
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

    def _draw_text_draw_rect(self, p: QPainter, dr: QRectF) -> None:
        """Draw the text box creation preview rectangle."""
        if self._text_draw_rect is None or self._doc_w == 0:
            return
        x, y, w, h = self._text_draw_rect
        tl = self._doc_to_widget(dr, x, y)
        br = self._doc_to_widget(dr, x + w, y + h)
        pen = QPen(QColor(0, 150, 255), 2.0, Qt.PenStyle.SolidLine)
        p.setPen(pen)
        p.setBrush(QColor(0, 150, 255, 40))
        p.drawRect(QRectF(tl, br))

    def _draw_text_selection(self, p: QPainter, dr: QRectF) -> None:
        """Draw text selection highlight rectangles."""
        if not self._text_selection_rects or not self._text_box:
            return
        bx, by = self._text_box[0], self._text_box[1]
        sx = dr.width() / self._doc_w if self._doc_w else 1
        sy = dr.height() / self._doc_h if self._doc_h else 1

        p.save()
        if self._text_box_angle != 0.0:
            bw, bh = self._text_box[2], self._text_box[3]
            cx = bx + bw / 2.0
            cy = by + bh / 2.0
            wc = self._doc_to_widget(dr, cx, cy)
            p.translate(wc.x(), wc.y())
            p.rotate(-self._text_box_angle)
            offset_x = -bw / 2.0 * sx
            offset_y = -bh / 2.0 * sy
        else:
            tl = self._doc_to_widget(dr, bx, by)
            offset_x = tl.x()
            offset_y = tl.y()
            p.translate(0, 0)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(60, 130, 220, 80))
        for rx, ry, rw, rh in self._text_selection_rects:
            if self._text_box_angle != 0.0:
                p.drawRect(QRectF(offset_x + rx * sx, offset_y + ry * sy,
                                  rw * sx, rh * sy))
            else:
                p.drawRect(QRectF(offset_x + rx * sx, offset_y + ry * sy,
                                  rw * sx, rh * sy))
        p.restore()

    # ---- Key events (text editing + Alt source mode) -----------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # Alt held → switch to source-selection cursor for clone/heal tools
        if event.key() == Qt.Key.Key_Alt:
            if self._current_tool_type in (ToolType.CLONE_STAMP, ToolType.HEALING_BRUSH):
                self._alt_held = True
                self.setCursor(self._make_source_cursor())
                event.accept()
                return
        if self._key_handler is not None and self._text_editing:
            consumed = self._key_handler(
                event.key(), event.text(), event.modifiers())
            if consumed:
                event.accept()
                return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Alt and self._alt_held:
            self._alt_held = False
            # Restore blank cursor when brush preview is active
            if self._brush_size > 0:
                self.setCursor(Qt.CursorShape.BlankCursor)
            else:
                shape = _CURSORS.get(self._current_tool_type, Qt.CursorShape.ArrowCursor)
                self.setCursor(QCursor(shape))
            event.accept()
            return
        super().keyReleaseEvent(event)

    @staticmethod
    def _make_source_cursor() -> QCursor:
        """Build a distinctive target/bullseye cursor for source selection."""
        size = 32
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = size // 2, size // 2

        # Outer circle
        pen = QPen(QColor(0, 0, 0, 180), 1.6)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx - 10, cy - 10, 20, 20)
        pen2 = QPen(QColor(0, 220, 255, 240), 1.0)
        pen2.setCosmetic(True)
        p.setPen(pen2)
        p.drawEllipse(cx - 10, cy - 10, 20, 20)

        # Inner circle
        p.drawEllipse(cx - 4, cy - 4, 8, 8)

        # Crosshair lines
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

        # Center dot
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 220, 255, 220))
        p.drawEllipse(cx - 1, cy - 1, 3, 3)

        p.end()
        return QCursor(pm, cx, cy)

    # ---- Mouse events -------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        self._zoom = max(0.01, min(self._zoom * factor, 32.0))
        self.update()
        self.view_changed.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._last_mouse = event.position()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        elif event.button() == Qt.MouseButton.LeftButton:
            # Check for guide hit first
            hit_guide = self._hit_test_guide(event.position())
            if hit_guide is not None:
                self._dragging_canvas_guide = hit_guide
                self.guide_grabbed.emit(hit_guide)
                self.setCursor(QCursor(
                    Qt.CursorShape.SplitVCursor if hit_guide.orientation == Qt.Orientation.Horizontal
                    else Qt.CursorShape.SplitHCursor))
                return
            pos = event.position()
            self.widget_pressed.emit(pos.x(), pos.y())
            dx, dy = self._canvas_to_doc(pos)
            self.tool_pressed.emit(dx, dy, 1.0)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            delta = event.position() - self._last_mouse
            self._pan += delta
            self._last_mouse = event.position()
            self.update()
            self.view_changed.emit()
            return

        # Guide dragging on canvas
        if self._dragging_canvas_guide is not None:
            g = self._dragging_canvas_guide
            dr = self._doc_rect()
            if g.orientation == Qt.Orientation.Horizontal:
                sy = dr.height() / self._doc_h if self._doc_h else 1
                doc_pos = (event.position().y() - dr.top()) / sy if sy else 0
            else:
                sx = dr.width() / self._doc_w if self._doc_w else 1
                doc_pos = (event.position().x() - dr.left()) / sx if sx else 0
            g.position = doc_pos
            self.guide_drag_moved.emit(g, doc_pos)
            self.update()
            return

        dx, dy = self._canvas_to_doc(event.position())
        self.cursor_moved.emit(dx, dy)

        # Update brush cursor position and visibility
        if self._brush_size > 0:
            self._brush_cursor_pos = event.position()
            self._brush_cursor_visible = True
            # If source overlay is active, do a full repaint so the source
            # crosshair tracks the cursor; otherwise just repaint brush area.
            if (self._source_pos is not None
                    and self._current_tool_type in (ToolType.CLONE_STAMP, ToolType.HEALING_BRUSH)):
                self.update()
            else:
                radius = int((self._brush_size / 2) * self._zoom) + 4
                cx, cy = int(event.position().x()), int(event.position().y())
                self.update(cx - radius, cy - radius, radius * 2, radius * 2)

        if event.buttons() & Qt.MouseButton.LeftButton:
            self.widget_moved.emit(event.position().x(), event.position().y())
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
            # Guide drag release on canvas
            if self._dragging_canvas_guide is not None:
                g = self._dragging_canvas_guide
                dr = self._doc_rect()
                if g.orientation == Qt.Orientation.Horizontal:
                    sy = dr.height() / self._doc_h if self._doc_h else 1
                    doc_pos = (event.position().y() - dr.top()) / sy if sy else 0
                    # Delete if dragged to ruler area (top edge)
                    delete = event.position().y() < dr.top() - 20
                else:
                    sx = dr.width() / self._doc_w if self._doc_w else 1
                    doc_pos = (event.position().x() - dr.left()) / sx if sx else 0
                    # Delete if dragged to ruler area (left edge)
                    delete = event.position().x() < dr.left() - 20
                g.position = doc_pos
                self.guide_drag_released.emit(g, doc_pos, delete)
                self._dragging_canvas_guide = None
                self.unsetCursor()
                return
            self.widget_released.emit()
            dx, dy = self._canvas_to_doc(event.position())
            self.tool_released.emit(dx, dy)
            self._drag_rect = None
