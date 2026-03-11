"""Shared constants and helpers for the layers panel."""

from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QPushButton, QWidget

# ---- Palette constants ----
BG = "#2b2b2b"
BG_HEADER = "#3a3a3a"
BG_LIST = "#262626"
SEL_PURPLE = "#5c2d82"
SEL_BORDER = "#7a3da8"
BORDER = "#444444"
TEXT = "#cccccc"
TEXT_DIM = "#888888"
ICON_ACTIVE = "#cccccc"
ICON_INACTIVE = "#555555"
BTN_BG = "#333333"
BTN_HOVER = "#444444"

# ---- Custom data roles ----
ROLE_LAYER_ID = Qt.ItemDataRole.UserRole
ROLE_IS_GROUP = Qt.ItemDataRole.UserRole + 1
ROLE_INDENT = Qt.ItemDataRole.UserRole + 2
ROLE_PARENT_ID = Qt.ItemDataRole.UserRole + 3
ROLE_IS_MASK = Qt.ItemDataRole.UserRole + 4
ROLE_IS_ADJ_FILTER = Qt.ItemDataRole.UserRole + 5
ROLE_IS_SEP = Qt.ItemDataRole.UserRole + 6
ROLE_IS_CLIPPED = Qt.ItemDataRole.UserRole + 7

SEP_HEIGHT = 6
THUMB_SIZE = 36
ROW_HEIGHT = 48
INDENT_WIDTH = 20
MAX_INDENT_DEPTH = 5
OVERSCAN_ROWS = 5
GAP_ANIM_MS = 120
EJECT_HOLD_MS = 400


def draw_icon(size: int, draw_fn) -> QIcon:
    """Helper to create a QIcon by calling *draw_fn(QPainter, size)*."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_fn(p, size)
    p.end()
    return QIcon(pm)


def h_separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"color: {BORDER};")
    line.setFixedHeight(1)
    return line


def toolbar_btn(icon: QIcon, tooltip: str, signal) -> QPushButton:
    b = QPushButton()
    b.setIcon(icon)
    b.setIconSize(QSize(16, 16))
    b.setFixedSize(24, 24)
    b.setFlat(True)
    b.setToolTip(tooltip)
    b.setStyleSheet(f"""
        QPushButton {{
            background: transparent; border: none; border-radius: 3px;
        }}
        QPushButton:hover {{
            background: {BTN_HOVER};
        }}
    """)
    b.clicked.connect(lambda: signal.emit())
    return b
