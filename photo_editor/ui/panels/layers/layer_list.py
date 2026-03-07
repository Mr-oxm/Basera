"""Custom list widget with drag-drop for layer reorder and reparent."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from .base import (
    ROLE_IS_ADJ_FILTER,
    ROLE_IS_GROUP,
    ROLE_IS_MASK,
    ROLE_IS_SEP,
    ROLE_LAYER_ID,
    ROLE_PARENT_ID,
)
from .layer_delegate import LayerItemDelegate
from photo_editor.ui.theme import ThemeManager
from ...styles import render_qss


class LayerListWidget(QListWidget):
    """QListWidget subclass that handles drag-drop for reorder & reparent."""

    layers_reordered = Signal(list, int)
    layers_dropped_in_group = Signal(list, str)
    layers_unparented = Signal(list)
    mask_dropped_on_layer = Signal(str, str)
    adj_filter_dropped_on_layer = Signal(str, str)
    delete_key_pressed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setItemDelegate(LayerItemDelegate(self))
        self._mask_drop_target: QListWidgetItem | None = None
        self._drop_indicator_y: int = -1

        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._apply_theme(ThemeManager.instance().active_palette)

    def _apply_theme(self, palette: dict) -> None:
        self.setStyleSheet(render_qss("layer_list.qss", palette))

    def _clear_mask_highlight(self) -> None:
        if self._mask_drop_target is not None:
            w = self.itemWidget(self._mask_drop_target)
            if w:
                w.setStyleSheet("background: transparent;")
            self._mask_drop_target = None

    def _is_dragging_mask(self) -> bool:
        for item in self.selectedItems():
            if not item.data(ROLE_IS_MASK):
                return False
        return bool(self.selectedItems())

    def _is_dragging_adj_filter(self) -> bool:
        for item in self.selectedItems():
            if not item.data(ROLE_IS_ADJ_FILTER):
                return False
        return bool(self.selectedItems())

    def _is_dragging_attachable(self) -> bool:
        return self._is_dragging_mask() or self._is_dragging_adj_filter()

    def dragMoveEvent(self, event) -> None:
        if self._is_dragging_attachable():
            self._drop_indicator_y = -1
            self.viewport().update()
            pos = event.position().toPoint()
            target_item = self.itemAt(pos)
            if (target_item
                    and not target_item.data(ROLE_IS_MASK)
                    and not target_item.data(ROLE_IS_ADJ_FILTER)
                    and not target_item.data(ROLE_IS_SEP)):
                if target_item is not self._mask_drop_target:
                    self._clear_mask_highlight()
                    self._mask_drop_target = target_item
                    w = self.itemWidget(target_item)
                    palette = ThemeManager.instance().active_palette
                    border_color = palette['accent'] if self._is_dragging_mask() else palette['accent_border']
                    if w:
                        w.setStyleSheet(
                            "background: transparent;"
                            f"border: 2px solid {border_color};"
                            "border-radius: 4px;"
                        )
                super().dragMoveEvent(event)
                return
            else:
                self._clear_mask_highlight()
        else:
            self._clear_mask_highlight()
            pos = event.position().toPoint()
            target_item = self.itemAt(pos)
            if target_item:
                rect = self.visualItemRect(target_item)
                rel_y = pos.y() - rect.top()
                if rel_y < rect.height() / 2:
                    self._drop_indicator_y = rect.top()
                else:
                    self._drop_indicator_y = rect.bottom()
            else:
                if self.count() > 0:
                    last_rect = self.visualItemRect(self.item(self.count() - 1))
                    self._drop_indicator_y = last_rect.bottom()
                else:
                    self._drop_indicator_y = -1
            self.viewport().update()
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event) -> None:
        self._clear_mask_highlight()
        self._drop_indicator_y = -1
        self.viewport().update()
        super().dragLeaveEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._drop_indicator_y >= 0:
            p = QPainter(self.viewport())
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            palette = ThemeManager.instance().active_palette
            pen = QPen(QColor(palette['accent_border']), 2)
            p.setPen(pen)
            y = self._drop_indicator_y
            p.drawLine(4, y, self.viewport().width() - 4, y)
            p.setBrush(QColor(palette['accent_border']))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(4, y), 3, 3)
            p.drawEllipse(QPointF(self.viewport().width() - 4, y), 3, 3)
            p.end()

    def dropEvent(self, event) -> None:
        self._clear_mask_highlight()
        self._drop_indicator_y = -1
        self.viewport().update()
        source_items = self.selectedItems()
        if not source_items:
            event.ignore()
            return

        source_ids = [item.data(ROLE_LAYER_ID) for item in source_items]
        source_parent_ids = [item.data(ROLE_PARENT_ID) for item in source_items]
        any_in_group = any(pid for pid in source_parent_ids)

        pos = event.position().toPoint()
        target_item = self.itemAt(pos)

        if target_item and self._is_dragging_mask():
            target_id = target_item.data(ROLE_LAYER_ID)
            if (not target_item.data(ROLE_IS_MASK)
                    and not target_item.data(ROLE_IS_SEP)
                    and target_id not in source_ids):
                for sid in source_ids:
                    self.mask_dropped_on_layer.emit(sid, target_id)
                event.ignore()
                return

        if target_item and self._is_dragging_adj_filter():
            target_id = target_item.data(ROLE_LAYER_ID)
            if (not target_item.data(ROLE_IS_MASK)
                    and not target_item.data(ROLE_IS_ADJ_FILTER)
                    and not target_item.data(ROLE_IS_SEP)
                    and target_id not in source_ids):
                for sid in source_ids:
                    self.adj_filter_dropped_on_layer.emit(sid, target_id)
                event.ignore()
                return

        pos = event.position().toPoint()
        target_item = self.itemAt(pos)

        if target_item:
            target_id = target_item.data(ROLE_LAYER_ID)
            is_group = target_item.data(ROLE_IS_GROUP)
            parent_id = target_item.data(ROLE_PARENT_ID)

            if target_item.data(ROLE_IS_SEP):
                drop_row = self.row(target_item)
                self.layers_reordered.emit(source_ids, drop_row)
                event.ignore()
                return

            item_rect = self.visualItemRect(target_item)
            rel_y = pos.y() - item_rect.top()

            if is_group and 0.25 * item_rect.height() < rel_y < 0.75 * item_rect.height():
                if target_id not in source_ids:
                    self.layers_dropped_in_group.emit(source_ids, target_id)
                event.ignore()
                return

            if parent_id and not is_group:
                if target_id not in source_ids:
                    self.layers_dropped_in_group.emit(source_ids, parent_id)
                event.ignore()
                return

            if any_in_group and not parent_id:
                self.layers_unparented.emit(source_ids)
                event.ignore()
                return

            drop_row = self.row(target_item)
            if rel_y > 0.5 * item_rect.height():
                drop_row += 1
            self.layers_reordered.emit(source_ids, drop_row)
        else:
            if any_in_group:
                self.layers_unparented.emit(source_ids)
                event.ignore()
                return
            self.layers_reordered.emit(source_ids, self.count())

        event.ignore()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_key_pressed.emit()
            return
        super().keyPressEvent(event)
