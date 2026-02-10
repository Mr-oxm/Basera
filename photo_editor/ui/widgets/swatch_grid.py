"""Swatch palette grid with click-to-pick, right-click-to-set, and recent colours.

Modern design: rounded cells, hover glow, clean spacing.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize, QRectF
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from ...core.color import Color
from ...core.color_engine import SwatchPalette, ColorManager


# ============================================================================
# Individual swatch cell — rounded with hover highlight
# ============================================================================

class _SwatchCell(QWidget):
    clicked = Signal(object)       # Color
    right_clicked = Signal(int)    # index

    def __init__(self, color: Color, index: int, size: int = 18, parent=None) -> None:
        super().__init__(parent)
        self._color = color
        self._index = index
        self._hovered = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(color.to_hex())
        self.setMouseTracking(True)

    @property
    def color(self) -> Color:
        return self._color

    @color.setter
    def color(self, c: Color) -> None:
        self._color = c
        self.setToolTip(c.to_hex())
        self.update()

    def paintEvent(self, ev: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = 3.0

        # Clip to rounded rect
        clip = QPainterPath()
        clip.addRoundedRect(rect, radius, radius)
        p.setClipPath(clip)

        # Checkerboard for alpha
        cs = 4
        for y in range(int(rect.top()), int(rect.bottom()) + 1, cs):
            for x in range(int(rect.left()), int(rect.right()) + 1, cs):
                ix = (x - int(rect.left())) // cs
                iy = (y - int(rect.top())) // cs
                c = QColor(68, 68, 68) if (ix + iy) % 2 == 0 else QColor(88, 88, 88)
                p.fillRect(x, y, cs, cs, c)

        # Color fill
        r, g, b, a = self._color.to_rgb8()
        p.setBrush(QColor(r, g, b, a))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, radius, radius)
        p.setClipping(False)

        # Border
        if self._hovered:
            p.setPen(QPen(QColor(180, 210, 255), 1.5))
        else:
            p.setPen(QPen(QColor(55, 55, 55), 0.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, radius, radius)
        p.end()

    def enterEvent(self, ev) -> None:
        self._hovered = True
        self.update()

    def leaveEvent(self, ev) -> None:
        self._hovered = False
        self.update()

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._color)
        elif ev.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(self._index)


# ============================================================================
# Grid of swatches
# ============================================================================

class SwatchGrid(QWidget):
    """Scrollable swatch palette grid.

    Signals
    -------
    color_picked(Color)
    """

    color_picked = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cells: list[_SwatchCell] = []
        self._cols = 14
        self._cell_size = 18

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # Recent colours row
        self._recent_label = QLabel("Recent")
        self._recent_label.setStyleSheet(
            "color: #777; font-size: 10px; font-weight: 600;"
            "font-family: 'Segoe UI', 'Inter', sans-serif;"
        )
        outer.addWidget(self._recent_label)
        self._recent_row = QHBoxLayout()
        self._recent_row.setSpacing(3)
        self._recent_row.setContentsMargins(0, 0, 0, 0)
        self._recent_widgets: list[_SwatchCell] = []
        outer.addLayout(self._recent_row)

        # Palette label
        self._palette_label = QLabel("Swatches")
        self._palette_label.setStyleSheet(
            "color: #777; font-size: 10px; font-weight: 600;"
            "font-family: 'Segoe UI', 'Inter', sans-serif;"
        )
        outer.addWidget(self._palette_label)

        # Scrollable grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(100)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical {"
            "  background: #2e2e2e; width: 6px; border-radius: 3px;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: #555; border-radius: 3px; min-height: 20px;"
            "}"
            "QScrollBar::handle:vertical:hover { background: #666; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(2)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self._grid_widget)
        outer.addWidget(scroll)

        self.load_palette(SwatchPalette.default_palette())
        self._update_recent()

    def load_palette(self, palette: SwatchPalette) -> None:
        # Clear existing
        for cell in self._cells:
            cell.setParent(None)
            cell.deleteLater()
        self._cells.clear()

        for i, color in enumerate(palette.colors):
            cell = _SwatchCell(color, i, self._cell_size)
            cell.clicked.connect(self._on_cell_click)
            self._grid_layout.addWidget(cell, i // self._cols, i % self._cols)
            self._cells.append(cell)

    def _update_recent(self) -> None:
        # Clear old
        for w in self._recent_widgets:
            w.setParent(None)
            w.deleteLater()
        self._recent_widgets.clear()

        mgr = ColorManager.instance()
        for i, c in enumerate(mgr.history[:12]):
            cell = _SwatchCell(c, i, self._cell_size)
            cell.clicked.connect(self._on_cell_click)
            self._recent_row.addWidget(cell)
            self._recent_widgets.append(cell)
        # Pad with spacer
        self._recent_row.addStretch()

    def refresh_recent(self) -> None:
        self._update_recent()

    def _on_cell_click(self, c: Color) -> None:
        self.color_picked.emit(c)
