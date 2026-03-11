"""Overlay widget that paints all drag-drop visual feedback.

This is an absolutely-positioned transparent widget that sits on top of the
layer list viewport.  It is driven by the shared :class:`DragState` ref and
repaints via ``requestUpdate()`` calls from pointermove (through
``requestAnimationFrame``-equivalent QTimer.singleShot(0, ...)``.

Nothing here causes the layer tree to re-render.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPainterPath, QPixmap
from PySide6.QtWidgets import QWidget

from .base import ROW_HEIGHT, THUMB_SIZE, INDENT_WIDTH, GAP_ANIM_MS
from .drag_manager import DragState, DropMode
from ...theme import ThemeManager


class DragOverlay(QWidget):
    """Transparent overlay for drag visuals — insertion line, gap, badges."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._drag: DragState | None = None
        self._row_rects: list[QRectF] = []
        self._row_indent: list[int] = []
        self._gap_y: float = -1        # animated gap centre Y
        self._gap_target_y: float = -1  # target gap centre Y
        self._invalid: bool = False     # red flash for forbidden drops
        self._preview_pixmap: QPixmap | None = None
        self._preview_text: str = ""

    # ---- public API ---------------------------------------------------------

    def set_drag(self, drag: DragState) -> None:
        self._drag = drag

    def set_row_geometry(self, rects: list[QRectF], indents: list[int]) -> None:
        self._row_rects = rects
        self._row_indent = indents

    def set_invalid(self, invalid: bool) -> None:
        self._invalid = invalid
        self.update()

    def set_preview(self, pixmap: QPixmap | None, text: str) -> None:
        self._preview_pixmap = pixmap
        self._preview_text = text

    def schedule_repaint(self) -> None:
        """Called from pointermove to request a repaint on the next frame."""
        self.update()

    # ---- painting -----------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802
        drag = self._drag
        if drag is None or not drag.drag_started:
            return

        palette = ThemeManager.instance().active_palette
        accent = QColor(palette["accent"])
        accent_border = QColor(palette.get("accent_border", palette["accent"]))

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        try:
            self._paint_gap(p, drag, accent_border)
            self._paint_mode_indicators(p, drag, accent, accent_border)
            self._paint_drag_chip(p, drag)
        finally:
            p.end()

    # -- gap between rows ----------------------------------------------------

    def _paint_gap(self, p: QPainter, drag: DragState, accent: QColor) -> None:
        if drag.drop_mode != DropMode.REORDER:
            return
        idx = drag.insert_index
        if idx < 0:
            return
        # Compute Y for the insertion line
        if idx < len(self._row_rects):
            y = self._row_rects[idx].top()
        elif self._row_rects:
            y = self._row_rects[-1].bottom()
        else:
            return

        # Draw gap background (translucent band)
        gap_rect = QRectF(4, y - ROW_HEIGHT / 2, self.width() - 8, ROW_HEIGHT)
        gap_color = QColor(accent)
        gap_color.setAlphaF(0.07)
        p.fillRect(gap_rect, gap_color)

        # Draw insertion line
        pen = QPen(accent, 2)
        p.setPen(pen)
        indent_offset = 0
        if self._row_indent and idx < len(self._row_indent):
            indent_offset = self._row_indent[idx] * INDENT_WIDTH
        x_start = max(4, indent_offset)
        p.drawLine(QPointF(x_start, y), QPointF(self.width() - 4, y))

        # End circles
        p.setBrush(accent)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(x_start, y), 3, 3)
        p.drawEllipse(QPointF(self.width() - 4, y), 3, 3)

    # -- mode indicators (nest highlight, clip glow, etc.) --------------------

    def _paint_mode_indicators(
        self, p: QPainter, drag: DragState, accent: QColor, accent_border: QColor,
    ) -> None:
        row = drag.drop_target_row
        if row < 0 or row >= len(self._row_rects):
            return
        rect = self._row_rects[row]

        if self._invalid:
            # Red flash for forbidden drop
            red = QColor("#ff4444")
            red.setAlphaF(0.25)
            p.fillRect(rect, red)
            pen = QPen(QColor("#ff4444"), 2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 4, 4)
            return

        if drag.drop_mode == DropMode.NEST:
            # Solid rounded highlight border
            pen = QPen(accent_border, 1.5)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 4, 4)

            # "Add as child" badge on right side
            badge_size = 18
            badge_x = rect.right() - badge_size - 8
            badge_y = rect.center().y() - badge_size / 2
            badge_rect = QRectF(badge_x, badge_y, badge_size, badge_size)
            p.setBrush(accent_border)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(badge_rect, 3, 3)
            # Draw ▤ (layer group icon) in badge
            p.setPen(QPen(QColor("#ffffff"), 1))
            font = QFont("Segoe UI Symbol", 9)
            p.setFont(font)
            p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "\u25A4")

        elif drag.drop_mode == DropMode.CLIP:
            # Glow on the thumbnail area
            indent = self._row_indent[row] if row < len(self._row_indent) else 0
            thumb_x = 4 + indent * INDENT_WIDTH + 24  # after arrow space
            thumb_y = rect.top() + (rect.height() - THUMB_SIZE) / 2
            thumb_rect = QRectF(thumb_x, thumb_y, THUMB_SIZE, THUMB_SIZE)

            # Outer glow
            glow = QColor(accent)
            glow.setAlphaF(0.5)
            for i in range(4, 0, -1):
                glow.setAlphaF(0.12 * (5 - i))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(glow)
                p.drawRoundedRect(thumb_rect.adjusted(-i, -i, i, i), 4, 4)

            # Inner accent border
            pen = QPen(accent, 2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(thumb_rect.adjusted(-1, -1, 1, 1), 4, 4)

            # Clip badge on thumbnail corner
            badge_size = 14
            badge_x = thumb_rect.right() - badge_size + 2
            badge_y = thumb_rect.bottom() - badge_size + 2
            badge_rect = QRectF(badge_x, badge_y, badge_size, badge_size)
            p.setBrush(accent)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(badge_rect, 2, 2)
            p.setPen(QPen(QColor("#ffffff"), 1))
            font = QFont("Segoe UI Symbol", 7)
            p.setFont(font)
            p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "\u2310")  # ⌐

    # -- floating drag chip ---------------------------------------------------

    def _paint_drag_chip(self, p: QPainter, drag: DragState) -> None:
        if not drag.drag_started:
            return
        cx = drag.pointer_x
        cy = drag.pointer_y - 28  # offset above cursor

        chip_w = 160
        chip_h = 28
        chip_rect = QRectF(cx - chip_w / 2, cy - chip_h / 2, chip_w, chip_h)

        # Clamp to overlay bounds
        if chip_rect.left() < 0:
            chip_rect.moveLeft(0)
        if chip_rect.right() > self.width():
            chip_rect.moveRight(self.width())

        # Semi-transparent background
        bg = QColor("#333333")
        bg.setAlphaF(0.85)
        p.setBrush(bg)
        p.setPen(QPen(QColor("#555555"), 1))
        p.drawRoundedRect(chip_rect, 6, 6)

        # Icon
        inner = chip_rect.adjusted(6, 4, -6, -4)
        if self._preview_pixmap and not self._preview_pixmap.isNull():
            icon_size = min(20, int(inner.height()))
            p.drawPixmap(
                int(inner.left()), int(inner.top()),
                icon_size, icon_size,
                self._preview_pixmap,
            )
            text_rect = QRectF(inner.left() + icon_size + 4, inner.top(), inner.width() - icon_size - 4, inner.height())
        else:
            text_rect = inner

        # Text
        p.setPen(QColor("#cccccc"))
        font = QFont("Segoe UI", 9)
        p.setFont(font)
        text = self._preview_text
        if len(drag.dragged_ids) > 1:
            text = f"{len(drag.dragged_ids)} layers"
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

    # -- eject affordance (arrow on group rows) --------------------------------

    def paint_eject_indicator(self, p: QPainter, row: int, accent: QColor) -> None:
        if row < 0 or row >= len(self._row_rects):
            return
        rect = self._row_rects[row]
        arrow_x = rect.left() + 2
        arrow_y = rect.center().y()
        p.setPen(QPen(accent, 2))
        # Left-pointing arrow
        p.drawLine(QPointF(arrow_x + 10, arrow_y), QPointF(arrow_x, arrow_y))
        p.drawLine(QPointF(arrow_x, arrow_y), QPointF(arrow_x + 4, arrow_y - 4))
        p.drawLine(QPointF(arrow_x, arrow_y), QPointF(arrow_x + 4, arrow_y + 4))
