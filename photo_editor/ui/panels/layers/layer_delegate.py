"""Custom delegate for layer list selection highlight."""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem, QStyledItemDelegate

from .base import ROLE_IS_SEP
from photo_editor.ui.theme import ThemeManager


class LayerItemDelegate(QStyledItemDelegate):
    """Draw a rounded purple selection rectangle behind the item widget."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        if index.data(ROLE_IS_SEP):
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = option.rect.adjusted(1, 1, -1, -1)

        if option.state & QStyle.StateFlag.State_Selected:
            palette = ThemeManager.instance().active_palette
            painter.setBrush(QColor(palette['accent']))
            painter.setPen(QPen(QColor(palette['accent_border']), 1))
            painter.drawRoundedRect(QRectF(rect), 4, 4)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(rect)

        painter.restore()
