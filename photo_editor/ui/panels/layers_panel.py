"""Layers panel — visibility toggles, lock buttons, opacity, blend mode, groups."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSlider,
    QVBoxLayout, QWidget,
)

from ...core.document import Document
from ...core.enums import BlendMode, LayerType


# ---- Custom data roles ------------------------------------------------------

_ROLE_LAYER_ID = Qt.ItemDataRole.UserRole
_ROLE_IS_GROUP = Qt.ItemDataRole.UserRole + 1
_ROLE_INDENT = Qt.ItemDataRole.UserRole + 2
_ROLE_PARENT_ID = Qt.ItemDataRole.UserRole + 3


# ---- Vector icon helpers ---------------------------------------------------

def _icon_eye(visible: bool) -> QIcon:
    s = 18
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy = s / 2, s / 2
    col = QColor(200, 200, 200) if visible else QColor(90, 90, 90)
    p.setPen(QPen(col, 1.4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    eye = QPainterPath()
    eye.moveTo(2, cy)
    eye.quadTo(cx, 3, s - 2, cy)
    eye.quadTo(cx, s - 3, 2, cy)
    p.drawPath(eye)
    if visible:
        p.setBrush(col)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), 2.5, 2.5)
    else:
        p.setPen(QPen(QColor(170, 70, 70), 1.5))
        p.drawLine(QPointF(4, s - 4), QPointF(s - 4, 4))
    p.end()
    return QIcon(pm)


def _icon_lock(locked: bool) -> QIcon:
    s = 18
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    col = QColor(200, 200, 200) if locked else QColor(90, 90, 90)
    cx = s / 2
    p.setPen(QPen(col, 1.4))
    bw, bh = 10.0, 6.0
    bx = (s - bw) / 2
    by = s - bh - 2
    p.setBrush(col if locked else Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(bx, by, bw, bh), 1.5, 1.5)
    p.setBrush(Qt.BrushStyle.NoBrush)
    sw = 6.0
    sx = (s - sw) / 2
    shackle = QPainterPath()
    if locked:
        shackle.moveTo(sx, by)
        shackle.lineTo(sx, by - 3)
        shackle.quadTo(sx, by - 6, cx, by - 6)
        shackle.quadTo(sx + sw, by - 6, sx + sw, by - 3)
        shackle.lineTo(sx + sw, by)
    else:
        shackle.moveTo(sx, by)
        shackle.lineTo(sx, by - 3)
        shackle.quadTo(sx, by - 6, cx, by - 6)
        shackle.quadTo(sx + sw, by - 6, sx + sw, by - 3)
        shackle.lineTo(sx + sw, by - 5)
    p.drawPath(shackle)
    p.end()
    return QIcon(pm)


def _icon_mask(has_mask: bool) -> QIcon:
    s = 18
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)
    if not has_mask:
        return QIcon(pm)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(180, 180, 180), 1.2))
    p.setBrush(QColor(180, 180, 180, 50))
    p.drawEllipse(QRectF(2, 2, s - 4, s - 4))
    p.end()
    return QIcon(pm)


# ---- Layer item widget -----------------------------------------------------

class _LayerItemWidget(QWidget):
    """Custom widget for a single row in the layers list."""

    visibility_clicked = Signal(str)
    lock_clicked = Signal(str)
    collapse_clicked = Signal(str)
    rename_finished = Signal(str, str)  # layer_id, new_name

    def __init__(
        self,
        layer_id: str,
        name: str,
        visible: bool,
        locked: bool,
        indent: int = 0,
        is_group: bool = False,
        is_collapsed: bool = False,
        has_mask: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._layer_id = layer_id
        self._orig_name = name
        self._edit: QLineEdit | None = None
        self._rename_done = False

        layout = QHBoxLayout(self)
        left_margin = 6 + indent * 20
        layout.setContentsMargins(left_margin, 1, 4, 1)
        layout.setSpacing(4)

        # Group expand/collapse toggle
        if is_group:
            arrow_text = "\u25B6" if is_collapsed else "\u25BC"
            self._arrow_btn = QPushButton(arrow_text)
            self._arrow_btn.setFixedSize(20, 22)
            self._arrow_btn.setFlat(True)
            self._arrow_btn.setStyleSheet("font-size: 10px; padding: 0;")
            self._arrow_btn.setToolTip("Collapse" if not is_collapsed else "Expand")
            self._arrow_btn.clicked.connect(
                lambda: self.collapse_clicked.emit(layer_id),
            )
            layout.addWidget(self._arrow_btn)

        # Layer name label
        self._name_label = QLabel(name)
        if is_group:
            self._name_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._name_label, 1)

        # Mask badge
        if has_mask:
            mask_lbl = QLabel()
            mask_lbl.setPixmap(_icon_mask(True).pixmap(14, 14))
            mask_lbl.setToolTip("Layer has mask")
            layout.addWidget(mask_lbl)

        # Visibility button
        self._vis_btn = QPushButton()
        self._vis_btn.setIcon(_icon_eye(visible))
        self._vis_btn.setFixedSize(24, 22)
        self._vis_btn.setFlat(True)
        self._vis_btn.setToolTip("Toggle visibility")
        self._vis_btn.clicked.connect(
            lambda: self.visibility_clicked.emit(layer_id),
        )
        layout.addWidget(self._vis_btn)

        # Lock button
        self._lock_btn = QPushButton()
        self._lock_btn.setIcon(_icon_lock(locked))
        self._lock_btn.setFixedSize(24, 22)
        self._lock_btn.setFlat(True)
        self._lock_btn.setToolTip("Toggle lock")
        self._lock_btn.clicked.connect(
            lambda: self.lock_clicked.emit(layer_id),
        )
        layout.addWidget(self._lock_btn)

    # ---- Inline rename -------------------------------------------------------

    def start_rename(self) -> None:
        """Switch the name label to an editable QLineEdit."""
        if self._edit is not None:
            return
        self._rename_done = False
        self._edit = QLineEdit(self._orig_name)
        self._edit.selectAll()

        lay = self.layout()
        idx = lay.indexOf(self._name_label)
        self._name_label.hide()
        lay.insertWidget(idx, self._edit, 1)
        self._edit.setFocus()
        self._edit.returnPressed.connect(self._commit_rename)
        self._edit.editingFinished.connect(self._commit_rename)

    def _commit_rename(self) -> None:
        if self._rename_done or self._edit is None:
            return
        self._rename_done = True
        new_name = self._edit.text().strip()
        self._edit.hide()
        self._edit.deleteLater()
        self._edit = None
        if new_name and new_name != self._orig_name:
            self._name_label.setText(new_name)
            self.rename_finished.emit(self._layer_id, new_name)
        self._name_label.show()


# ---- Custom QListWidget with drag-drop support ----------------------------

class _LayerListWidget(QListWidget):
    """QListWidget subclass that handles drag-drop for reorder & reparent."""

    layers_reordered = Signal(list, int)
    layers_dropped_in_group = Signal(list, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def dropEvent(self, event) -> None:
        source_items = self.selectedItems()
        if not source_items:
            event.ignore()
            return

        source_ids = [item.data(_ROLE_LAYER_ID) for item in source_items]

        pos = event.position().toPoint()
        target_item = self.itemAt(pos)

        if target_item:
            target_id = target_item.data(_ROLE_LAYER_ID)
            is_group = target_item.data(_ROLE_IS_GROUP)
            parent_id = target_item.data(_ROLE_PARENT_ID)

            item_rect = self.visualItemRect(target_item)
            rel_y = pos.y() - item_rect.top()

            # Drop ON a group header: reparent into that group
            if is_group and 0.25 * item_rect.height() < rel_y < 0.75 * item_rect.height():
                if target_id not in source_ids:
                    self.layers_dropped_in_group.emit(source_ids, target_id)
                event.accept()
                return

            # Drop ON a child of a group: reparent into the child's group
            if parent_id and not is_group:
                if target_id not in source_ids:
                    self.layers_dropped_in_group.emit(source_ids, parent_id)
                event.accept()
                return

            # Reorder
            drop_row = self.row(target_item)
            if rel_y > 0.5 * item_rect.height():
                drop_row += 1
            self.layers_reordered.emit(source_ids, drop_row)
        else:
            self.layers_reordered.emit(source_ids, self.count())

        event.accept()


class _BlendModeCombo(QComboBox):
    hover_preview = Signal(object)
    hover_ended = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._orig_idx: int = -1
        self._popup_open = False
        self.highlighted.connect(self._on_highlighted)

    def showPopup(self) -> None:
        self._orig_idx = self.currentIndex()
        self._popup_open = True
        super().showPopup()

    def hidePopup(self) -> None:
        self._popup_open = False
        super().hidePopup()
        QTimer.singleShot(0, self._on_popup_closed)

    def _on_highlighted(self, index: int) -> None:
        if self._popup_open:
            mode = self.itemData(index)
            if mode is not None:
                self.hover_preview.emit(mode)

    def _on_popup_closed(self) -> None:
        if self.currentIndex() == self._orig_idx:
            self.hover_ended.emit()


class LayersPanel(QWidget):
    """Dockable panel for managing the layer stack."""

    layer_selected = Signal(int)
    visibility_toggled = Signal(str)
    lock_toggled = Signal(str)
    opacity_changed = Signal(float)
    blend_mode_changed = Signal(BlendMode)
    blend_mode_hovered = Signal(object)
    blend_mode_hover_ended = Signal()
    add_requested = Signal()
    delete_requested = Signal()
    duplicate_requested = Signal()
    group_requested = Signal()
    mask_requested = Signal()
    merge_down_requested = Signal()
    flatten_requested = Signal()
    rename_requested = Signal(str, str)   # layer_id, new_name
    styles_requested = Signal()             # open layer-styles dialog
    layers_reordered = Signal(list, int)
    layers_reparented = Signal(list, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._doc: Document | None = None
        self._refreshing = False
        self._row_layer_ids: list[str] = []
        self._collapsed_groups: set[str] = set()
        self._build_ui()

    # ---- Build UI -----------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Blend mode
        r1 = QHBoxLayout()
        self._blend_combo = _BlendModeCombo()
        for mode in BlendMode:
            self._blend_combo.addItem(mode.name.replace("_", " ").title(), mode)
        self._blend_combo.currentIndexChanged.connect(self._on_blend_changed)
        self._blend_combo.hover_preview.connect(self.blend_mode_hovered.emit)
        self._blend_combo.hover_ended.connect(self.blend_mode_hover_ended.emit)
        r1.addWidget(self._blend_combo, 1)
        root.addLayout(r1)

        # Opacity
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Opacity"))
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setValue(100)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        r2.addWidget(self._opacity_slider, 1)
        self._opacity_label = QLabel("100 %")
        self._opacity_label.setFixedWidth(40)
        self._opacity_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        r2.addWidget(self._opacity_label)
        root.addLayout(r2)

        # Layer list
        self._list = _LayerListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list.layers_reordered.connect(self.layers_reordered.emit)
        self._list.layers_dropped_in_group.connect(self.layers_reparented.emit)
        root.addWidget(self._list, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(2)
        for label, tip, sig in [
            ("+", "New layer", self.add_requested),
            ("Grp", "New group / group selected", self.group_requested),
            ("Dup", "Duplicate", self.duplicate_requested),
            ("Msk", "Add mask", self.mask_requested),
            ("fx", "Layer styles", self.styles_requested),
            ("Del", "Delete layer", self.delete_requested),
        ]:
            b = QPushButton(label)
            b.setToolTip(tip)
            b.setFixedHeight(26)
            b.clicked.connect(sig.emit)
            btn_row.addWidget(b)
        root.addLayout(btn_row)

    # ---- Public API ---------------------------------------------------------

    def refresh(self, document: Document) -> None:
        self._doc = document
        self._refreshing = True

        self._list.clear()
        self._row_layer_ids = []

        display_order = self._build_display_order(document, self._collapsed_groups)

        for layer, indent in display_order:
            is_group = layer.layer_type == LayerType.GROUP
            has_mask = layer.mask is not None
            is_collapsed = layer.id in self._collapsed_groups

            item = QListWidgetItem()
            item.setData(_ROLE_LAYER_ID, layer.id)
            item.setData(_ROLE_IS_GROUP, is_group)
            item.setData(_ROLE_INDENT, indent)
            item.setData(_ROLE_PARENT_ID, layer.parent_id or "")
            item.setSizeHint(QSize(0, 30))

            widget = _LayerItemWidget(
                layer.id, layer.name, layer.visible, layer.locked,
                indent=indent, is_group=is_group, is_collapsed=is_collapsed,
                has_mask=has_mask,
            )
            widget.visibility_clicked.connect(self.visibility_toggled.emit)
            widget.lock_clicked.connect(self.lock_toggled.emit)
            widget.rename_finished.connect(self.rename_requested.emit)
            if is_group:
                widget.collapse_clicked.connect(self._on_collapse_toggled)

            self._list.addItem(item)
            self._list.setItemWidget(item, widget)
            self._row_layer_ids.append(layer.id)

        # Highlight active layer
        active = document.layers.active_layer
        if active:
            for row in range(self._list.count()):
                it = self._list.item(row)
                if it and it.data(_ROLE_LAYER_ID) == active.id:
                    self._list.setCurrentRow(row)
                    break

        # Sync controls to active layer
        if active:
            self._opacity_slider.blockSignals(True)
            self._opacity_slider.setValue(int(active.opacity * 100))
            self._opacity_slider.blockSignals(False)
            self._opacity_label.setText(f"{int(active.opacity * 100)} %")
            blend_idx = self._blend_combo.findData(active.blend_mode)
            if blend_idx >= 0:
                self._blend_combo.blockSignals(True)
                self._blend_combo.setCurrentIndex(blend_idx)
                self._blend_combo.blockSignals(False)

        self._refreshing = False

    def selected_layer_ids(self) -> list[str]:
        ids: list[str] = []
        for item in self._list.selectedItems():
            lid = item.data(_ROLE_LAYER_ID)
            if lid:
                ids.append(lid)
        return ids

    def row_layer_ids(self) -> list[str]:
        return list(self._row_layer_ids)

    # ---- Display order builder -----------------------------------------------

    @staticmethod
    def _build_display_order(
        document: Document, collapsed: set[str],
    ) -> list[tuple]:
        layers = list(document.layers)
        children_of: dict[str, list] = {}
        for layer in layers:
            if layer.parent_id:
                children_of.setdefault(layer.parent_id, []).append(layer)

        result: list[tuple] = []
        for layer in reversed(layers):
            if layer.parent_id is not None:
                continue
            result.append((layer, 0))
            if (
                layer.layer_type == LayerType.GROUP
                and layer.id not in collapsed
                and layer.id in children_of
            ):
                for child in reversed(children_of[layer.id]):
                    result.append((child, 1))
        return result

    # ---- Internal slots -----------------------------------------------------

    def _on_collapse_toggled(self, group_id: str) -> None:
        if group_id in self._collapsed_groups:
            self._collapsed_groups.discard(group_id)
        else:
            self._collapsed_groups.add(group_id)
        if self._doc:
            self.refresh(self._doc)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Start inline rename on double-click."""
        widget = self._list.itemWidget(item)
        if isinstance(widget, _LayerItemWidget):
            widget.start_rename()

    def _on_row_changed(self, row: int) -> None:
        if self._refreshing or row < 0 or not self._doc:
            return
        if 0 <= row < len(self._row_layer_ids):
            lid = self._row_layer_ids[row]
            for i, layer in enumerate(self._doc.layers):
                if layer.id == lid:
                    self.layer_selected.emit(i)
                    break
        layer = self._layer_for_row(row)
        if layer:
            self._opacity_slider.blockSignals(True)
            self._opacity_slider.setValue(int(layer.opacity * 100))
            self._opacity_slider.blockSignals(False)
            self._opacity_label.setText(f"{int(layer.opacity * 100)} %")
            blend_idx = self._blend_combo.findData(layer.blend_mode)
            if blend_idx >= 0:
                self._blend_combo.blockSignals(True)
                self._blend_combo.setCurrentIndex(blend_idx)
                self._blend_combo.blockSignals(False)

    def _layer_for_row(self, row: int):
        if not self._doc or row < 0 or row >= len(self._row_layer_ids):
            return None
        lid = self._row_layer_ids[row]
        return self._doc.layers.get(lid)

    def _on_opacity_changed(self, value: int) -> None:
        if self._refreshing:
            return
        self._opacity_label.setText(f"{value} %")
        self.opacity_changed.emit(value / 100.0)

    def _on_blend_changed(self, idx: int) -> None:
        if self._refreshing:
            return
        mode = self._blend_combo.itemData(idx)
        if mode is not None:
            self.blend_mode_changed.emit(mode)

    def toggle_visibility_for_selected(self) -> None:
        item = self._list.currentItem()
        if item:
            layer_id = item.data(_ROLE_LAYER_ID)
            if layer_id:
                self.visibility_toggled.emit(layer_id)
