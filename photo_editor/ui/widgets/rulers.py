"""Affinity-style rulers with interactive guide dragging.

Provides horizontal and vertical rulers that sit along the edges of the canvas,
showing tick marks and numbers that update in real time as the user zooms and pans.
Rulers are unit-aware: they display values in px, in, cm, mm, or pt depending on
the active document's unit setting.  Dragging from a ruler creates a guide line
that can be repositioned or deleted.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import (
    QColor, QFont, QMouseEvent, QPainter, QPen,
)
from PySide6.QtWidgets import QWidget

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RULER_SIZE = 22          # pixels width/height of the ruler bar
_GUIDE_COLOR = QColor(74, 179, 255)  # cyan / blue guide line
_GUIDE_DRAG_COLOR = QColor(74, 179, 255, 140)
_CURSOR_COLOR = QColor(74, 111, 165, 200)  # #4a6fa5 — position indicator
_LAYER_BOUNDS_COLOR = QColor(255, 165, 0, 120)  # orange layer extents

_FONT = QFont("Segoe UI", 8)
_FONT.setStyleHint(QFont.StyleHint.SansSerif)

_SNAP_PX = 6  # pixel distance to snap when dragging a guide


# ---------------------------------------------------------------------------
# Unit helpers  (mirrors new_project_dialog.px_per_unit — no circular import)
# ---------------------------------------------------------------------------

def _px_per_unit(unit: str, dpi: int) -> float:
    """Return how many document pixels equal one display unit."""
    if unit == "in":
        return float(dpi)
    if unit == "cm":
        return dpi / 2.54
    if unit == "mm":
        return dpi / 25.4
    if unit == "pt":
        return dpi / 72.0
    return 1.0  # "px" default


def _label_for(value_px: float, unit: str, dpi: int) -> str:
    """Convert a pixel coordinate to a human-readable label in *unit*."""
    ppu = _px_per_unit(unit, dpi)
    v = value_px / ppu
    if unit == "px":
        return str(int(v))
    if unit in ("in", "cm"):
        return f"{v:.2f}"
    if unit == "mm":
        return f"{v:.1f}"
    if unit == "pt":
        return f"{v:.0f}"
    return str(int(v))


# ---------------------------------------------------------------------------
# Guide data
# ---------------------------------------------------------------------------

class Guide:
    """A single horizontal or vertical guide."""

    __slots__ = ("orientation", "position")

    def __init__(self, orientation: Qt.Orientation, position: float) -> None:
        self.orientation = orientation  # Horizontal → y position, Vertical → x position
        self.position = position        # document-space coordinate


# ---------------------------------------------------------------------------
# Base ruler widget
# ---------------------------------------------------------------------------

class _RulerBase(QWidget):
    """Abstract base for horizontal and vertical rulers."""

    guide_created = Signal(object)   # Guide
    guide_moved = Signal(object, float)  # Guide, new_position
    guide_deleted = Signal(object)   # Guide

    def __init__(self, orientation: Qt.Orientation, parent=None) -> None:
        super().__init__(parent)
        self._orientation = orientation
        self._zoom = 1.0
        self._pan = 0.0        # pan offset in widget pixels
        self._origin = 0.0     # widget pixel position of doc coord 0
        self._doc_size = 0     # width or height in doc-pixels
        self._cursor_pos: float | None = None   # widget-space cursor indicator
        self._guides: list[Guide] = []
        self._dragging_guide: Guide | None = None
        self._creating_guide = False
        # Perpendicular axis params (needed for guide creation)
        self._perp_zoom = 1.0
        self._perp_origin = 0.0
        self._perp_doc_size = 0
        # Layer bounds in doc coords  (start, end)
        self._layer_start: float | None = None
        self._layer_end: float | None = None
        # Unit / DPI state
        self._unit: str = "px"
        self._dpi: int = 72

        if orientation == Qt.Orientation.Horizontal:
            self.setFixedHeight(_RULER_SIZE)
            self.setCursor(Qt.CursorShape.SplitVCursor)
        else:
            self.setFixedWidth(_RULER_SIZE)
            self.setCursor(Qt.CursorShape.SplitHCursor)
        self.setMouseTracking(True)

    # ---- Public API --------------------------------------------------------

    def set_view_params(self, zoom: float, origin: float, doc_size: int) -> None:
        """Update from the canvas view's zoom/pan state."""
        self._zoom = zoom
        self._origin = origin
        self._doc_size = doc_size
        self.update()

    def set_perp_view_params(self, zoom: float, origin: float, doc_size: int) -> None:
        """Update the perpendicular axis params (for guide creation)."""
        self._perp_zoom = zoom
        self._perp_origin = origin
        self._perp_doc_size = doc_size

    def set_cursor_position(self, widget_pos: float | None) -> None:
        """Show mouse position indicator on the ruler."""
        self._cursor_pos = widget_pos
        self.update()

    def set_guides(self, guides: list[Guide]) -> None:
        self._guides = guides
        self.update()

    def set_layer_bounds(self, start: float | None, end: float | None) -> None:
        """Set the active layer's extent in document coordinates."""
        self._layer_start = start
        self._layer_end = end
        self.update()

    def set_unit(self, unit: str, dpi: int) -> None:
        """Set the display unit and DPI for tick labels (e.g. 'cm', 300)."""
        if unit != self._unit or dpi != self._dpi:
            self._unit = unit
            self._dpi = dpi
            self.update()

    # ---- Coordinate helpers ------------------------------------------------

    def _doc_to_widget(self, doc_coord: float) -> float:
        return self._origin + doc_coord * self._zoom

    def _widget_to_doc(self, widget_coord: float) -> float:
        if self._zoom == 0:
            return 0.0
        return (widget_coord - self._origin) / self._zoom

    def _perp_widget_to_doc(self, widget_coord: float) -> float:
        """Convert a perpendicular-axis widget coordinate to doc space."""
        if self._perp_zoom == 0:
            return 0.0
        return (widget_coord - self._perp_origin) / self._perp_zoom

    # ---- Tick spacing logic ------------------------------------------------

    @staticmethod
    def _nice_step(rough: float) -> float:
        """Return a human-friendly step size (1, 2, 5, 10, 20, 50, ...)."""
        if rough <= 0:
            return 1.0
        magnitude = 1.0
        while magnitude * 10 < rough:
            magnitude *= 10
        if rough <= magnitude * 1:
            return magnitude
        if rough <= magnitude * 2:
            return magnitude * 2
        if rough <= magnitude * 5:
            return magnitude * 5
        return magnitude * 10

    # ---- Paint --------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        from ..theme import ThemeManager
        palette = ThemeManager.instance().active_palette
        bg = QColor(palette["bg3"])
        tick_color = QColor(palette["fg_dim"])
        text_color = QColor(palette["fg"])
        subtick_color = QColor(palette["border_light"])
        border_color = QColor(palette["border"])

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.fillRect(self.rect(), bg)

        if self._doc_size <= 0 or self._zoom <= 0:
            p.end()
            return

        horiz = self._orientation == Qt.Orientation.Horizontal
        length = self.width() if horiz else self.height()

        # Unit conversion factor: doc pixels per display unit
        ppu = _px_per_unit(self._unit, self._dpi)

        # Compute nice tick spacing in *display-unit* space so labels never overlap.
        # zoom_unit = widget pixels per display unit
        zoom_unit = self._zoom * ppu
        min_label_px = 60
        rough_step_unit = min_label_px / max(zoom_unit, 0.001)
        step_unit = self._nice_step(rough_step_unit)
        step_doc = step_unit * ppu          # step in document pixels

        sub_divs = 5 if step_unit >= 10 else 4
        sub_step_doc = step_doc / sub_divs

        # Range of doc coords visible
        doc_start = self._widget_to_doc(0)
        doc_end = self._widget_to_doc(length)
        if doc_start > doc_end:
            doc_start, doc_end = doc_end, doc_start

        first_tick_doc = (int(doc_start / step_doc) - 1) * step_doc
        last_tick_doc = doc_end + step_doc

        p.setFont(_FONT)

        # Draw sub-ticks
        p.setPen(QPen(subtick_color, 1))
        st = first_tick_doc
        while st <= last_tick_doc:
            for i in range(1, sub_divs):
                sub_doc = st + i * sub_step_doc
                wp = self._doc_to_widget(sub_doc)
                if 0 <= wp <= length:
                    if horiz:
                        p.drawLine(int(wp), _RULER_SIZE - 4, int(wp), _RULER_SIZE)
                    else:
                        p.drawLine(_RULER_SIZE - 4, int(wp), _RULER_SIZE, int(wp))
            st += step_doc

        # Draw major ticks + labels
        p.setPen(QPen(tick_color, 1))
        tick = first_tick_doc
        while tick <= last_tick_doc:
            wp = self._doc_to_widget(tick)
            if 0 <= wp <= length:
                label = _label_for(tick, self._unit, self._dpi)
                if horiz:
                    p.drawLine(int(wp), _RULER_SIZE - 8, int(wp), _RULER_SIZE)
                    p.setPen(QPen(text_color, 1))
                    p.drawText(int(wp) + 2, _RULER_SIZE - 9, label)
                    p.setPen(QPen(tick_color, 1))
                else:
                    p.drawLine(_RULER_SIZE - 8, int(wp), _RULER_SIZE, int(wp))
                    p.save()
                    p.setPen(QPen(text_color, 1))
                    p.translate(int(_RULER_SIZE - 10), int(wp) + 2)
                    p.rotate(-90)
                    p.drawText(0, 0, label)
                    p.restore()
                    p.setPen(QPen(tick_color, 1))
            tick += step_doc

        # Draw layer bounds indicators
        if self._layer_start is not None and self._layer_end is not None:
            ws = self._doc_to_widget(self._layer_start)
            we = self._doc_to_widget(self._layer_end)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_LAYER_BOUNDS_COLOR)
            if horiz:
                p.drawRect(QRectF(ws, _RULER_SIZE - 3, we - ws, 3))
            else:
                p.drawRect(QRectF(_RULER_SIZE - 3, ws, 3, we - ws))

        # Draw guides
        guide_pen = QPen(_GUIDE_COLOR, 1, Qt.PenStyle.DashLine)
        for g in self._guides:
            if g.orientation != (Qt.Orientation.Vertical if horiz else Qt.Orientation.Horizontal):
                continue
            wp = self._doc_to_widget(g.position)
            p.setPen(guide_pen)
            if horiz:
                p.drawLine(int(wp), 0, int(wp), _RULER_SIZE)
            else:
                p.drawLine(0, int(wp), _RULER_SIZE, int(wp))

        # Draw cursor position indicator
        if self._cursor_pos is not None:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_CURSOR_COLOR)
            cp = self._cursor_pos
            if horiz:
                # Small triangle at cursor x
                p.drawPolygon([
                    QPointF(cp - 4, _RULER_SIZE),
                    QPointF(cp + 4, _RULER_SIZE),
                    QPointF(cp, _RULER_SIZE - 6),
                ])
            else:
                p.drawPolygon([
                    QPointF(_RULER_SIZE, cp - 4),
                    QPointF(_RULER_SIZE, cp + 4),
                    QPointF(_RULER_SIZE - 6, cp),
                ])

        # Bottom / right edge line
        p.setPen(QPen(border_color, 1))
        if horiz:
            p.drawLine(0, _RULER_SIZE - 1, self.width(), _RULER_SIZE - 1)
        else:
            p.drawLine(_RULER_SIZE - 1, 0, _RULER_SIZE - 1, self.height())

        p.end()

    # ---- Mouse handling — guide creation / dragging -----------------------

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        horiz = self._orientation == Qt.Orientation.Horizontal
        # Along-ruler coordinate (for matching existing guide positions)
        pos = ev.position().x() if horiz else ev.position().y()

        # Check if clicking an existing guide shown on this ruler.
        # The horizontal ruler displays Vertical guides (x-positions);
        # the vertical ruler displays Horizontal guides (y-positions).
        shown_orient = Qt.Orientation.Vertical if horiz else Qt.Orientation.Horizontal
        for g in self._guides:
            if g.orientation == shown_orient:
                gw = self._doc_to_widget(g.position)
                if abs(pos - gw) < _SNAP_PX:
                    self._dragging_guide = g
                    return

        # Start creating a new guide.
        # Dragging FROM the horizontal ruler creates a Horizontal guide
        # (a horizontal line whose position is a Y coordinate).
        # Dragging FROM the vertical ruler creates a Vertical guide
        # (a vertical line whose position is an X coordinate).
        new_orient = Qt.Orientation.Horizontal if horiz else Qt.Orientation.Vertical
        # Use the perpendicular coordinate for the guide position
        perp_pos = ev.position().y() if horiz else ev.position().x()
        doc_pos = self._perp_widget_to_doc(perp_pos)
        self._creating_guide = True
        self._dragging_guide = Guide(new_orient, doc_pos)

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        horiz = self._orientation == Qt.Orientation.Horizontal
        if self._dragging_guide is not None:
            g = self._dragging_guide
            if self._creating_guide:
                # New guide uses perpendicular coordinate
                perp_pos = ev.position().y() if horiz else ev.position().x()
                g.position = self._perp_widget_to_doc(perp_pos)
            else:
                # Existing guide being repositioned along its own axis
                pos = ev.position().x() if horiz else ev.position().y()
                g.position = self._widget_to_doc(pos)
            self.update()
            self.guide_moved.emit(g, g.position)

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        if self._dragging_guide is not None:
            horiz = self._orientation == Qt.Orientation.Horizontal

            if self._creating_guide:
                # Check perpendicular distance — if released too close to
                # the ruler (didn't drag far enough), discard the guide.
                perp_pos = ev.position().y() if horiz else ev.position().x()
                doc_pos = self._perp_widget_to_doc(perp_pos)
                self._dragging_guide.position = doc_pos
                # Only create if dragged at least past the ruler edge
                if (horiz and ev.position().y() > _RULER_SIZE) or \
                   (not horiz and ev.position().x() > _RULER_SIZE):
                    self.guide_created.emit(self._dragging_guide)
                else:
                    # Didn't drag far enough — signal deletion to clear preview
                    self.guide_deleted.emit(self._dragging_guide)
            else:
                # Update position along the guide's own axis
                pos = ev.position().x() if horiz else ev.position().y()
                doc_pos = self._widget_to_doc(pos)

                # If dragged far off the ruler → delete guide
                cross = ev.position().y() if horiz else ev.position().x()
                if cross < -10 or cross > _RULER_SIZE + 200:
                    self.guide_deleted.emit(self._dragging_guide)
                else:
                    self._dragging_guide.position = doc_pos
                    self.guide_moved.emit(self._dragging_guide, doc_pos)

            self._dragging_guide = None
            self._creating_guide = False
            self.update()


# ---------------------------------------------------------------------------
# Corner widget (where H and V rulers meet)
# ---------------------------------------------------------------------------

class RulerCorner(QWidget):
    """Small square at the intersection of the two rulers."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(_RULER_SIZE, _RULER_SIZE)

    def paintEvent(self, _event) -> None:
        from ..theme import ThemeManager
        palette = ThemeManager.instance().active_palette
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(palette["bg2"]))
        p.setPen(QPen(QColor(palette["border"]), 1))
        p.drawLine(0, _RULER_SIZE - 1, _RULER_SIZE, _RULER_SIZE - 1)
        p.drawLine(_RULER_SIZE - 1, 0, _RULER_SIZE - 1, _RULER_SIZE)
        p.end()


# ---------------------------------------------------------------------------
# Public ruler classes
# ---------------------------------------------------------------------------

class HorizontalRuler(_RulerBase):
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)


class VerticalRuler(_RulerBase):
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Vertical, parent)


# ---------------------------------------------------------------------------
# Convenience: get ruler bar size for layout calculations
# ---------------------------------------------------------------------------

RULER_SIZE = _RULER_SIZE
