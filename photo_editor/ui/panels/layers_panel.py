"""Layers panel — visibility toggles, lock buttons, opacity, blend mode, groups."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QSlider,
    QVBoxLayout, QWidget,
)

from ...core.document import Document
from ...core.enums import BlendMode


# ---- Vector icon helpers ---------------------------------------------------

def _icon_eye(visible: bool) -> QIcon:
    """Draw a small eye icon (open or slashed)."""
    s = 18
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy = s / 2, s / 2

    col = QColor(200, 200, 200) if visible else QColor(90, 90, 90)
    p.setPen(QPen(col, 1.4))
    p.setBrush(Qt.BrushStyle.NoBrush)

    # Almond eye outline via two quadratic curves
    eye = QPainterPath()
    eye.moveTo(2, cy)
    eye.quadTo(cx, 3, s - 2, cy)
    eye.quadTo(cx, s - 3, 2, cy)
    p.drawPath(eye)

    if visible:
        # Filled pupil
        p.setBrush(col)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), 2.5, 2.5)
    else:
        # Diagonal slash through the eye
        p.setPen(QPen(QColor(170, 70, 70), 1.5))
        p.drawLine(QPointF(4, s - 4), QPointF(s - 4, 4))

    p.end()
    return QIcon(pm)


def _icon_lock(locked: bool) -> QIcon:
    """Draw a small padlock icon (closed or open)."""
    s = 18
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    col = QColor(200, 200, 200) if locked else QColor(90, 90, 90)
    cx = s / 2
    p.setPen(QPen(col, 1.4))

    # Lock body
    bw, bh = 10.0, 6.0
    bx = (s - bw) / 2
    by = s - bh - 2
    p.setBrush(col if locked else Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(bx, by, bw, bh), 1.5, 1.5)

    # Shackle (U-shape)
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
        shackle.lineTo(sx + sw, by - 5)   # right side stays up
    p.drawPath(shackle)

    p.end()
    return QIcon(pm)


# ---- Layer item widget -----------------------------------------------------

class _LayerItemWidget(QWidget):
    """Custom widget for a single row in the layers list."""

    visibility_clicked = Signal(str)
    lock_clicked = Signal(str)

    def __init__(self, layer_id: str, name: str, visible: bool, locked: bool, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 1, 4, 1)
        layout.setSpacing(4)

        # Layer name — left side, stretches
        label = QLabel(name)
        layout.addWidget(label, 1)

        # Visibility button — right side
        self._vis_btn = QPushButton()
        self._vis_btn.setIcon(_icon_eye(visible))
        self._vis_btn.setFixedSize(24, 22)
        self._vis_btn.setFlat(True)
        self._vis_btn.setToolTip("Toggle visibility")
        self._vis_btn.clicked.connect(lambda: self.visibility_clicked.emit(layer_id))
        layout.addWidget(self._vis_btn)

        # Lock button — right side
        self._lock_btn = QPushButton()
        self._lock_btn.setIcon(_icon_lock(locked))
        self._lock_btn.setFixedSize(24, 22)
        self._lock_btn.setFlat(True)
        self._lock_btn.setToolTip("Toggle lock")
        self._lock_btn.clicked.connect(lambda: self.lock_clicked.emit(layer_id))
        layout.addWidget(self._lock_btn)


class _BlendModeCombo(QComboBox):
    """QComboBox that emits hover-preview signals for blend modes.

    When the popup is open and the user hovers over an item, *hover_preview*
    fires with the corresponding :class:`BlendMode`.  When the popup closes
    without a new selection, *hover_ended* fires so the caller can restore
    the original blend mode.
    """

    hover_preview = Signal(object)   # BlendMode being hovered
    hover_ended = Signal()           # popup closed without new selection

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
        # Defer the check so that currentIndexChanged has a chance to fire
        # first when the user actually selects an item.
        QTimer.singleShot(0, self._on_popup_closed)

    def _on_highlighted(self, index: int) -> None:
        if self._popup_open:
            mode = self.itemData(index)
            if mode is not None:
                self.hover_preview.emit(mode)

    def _on_popup_closed(self) -> None:
        # If the selected index didn't change, the user dismissed the popup
        # (clicked away or pressed Escape) — restore the original.
        if self.currentIndex() == self._orig_idx:
            self.hover_ended.emit()


class LayersPanel(QWidget):
    """Dockable panel for managing the layer stack."""

    layer_selected = Signal(int)       # row index (reversed)
    visibility_toggled = Signal(str)   # layer id
    lock_toggled = Signal(str)         # layer id
    opacity_changed = Signal(float)
    blend_mode_changed = Signal(BlendMode)
    blend_mode_hovered = Signal(object)    # live preview on hover
    blend_mode_hover_ended = Signal()      # restore when popup dismissed
    add_requested = Signal()
    delete_requested = Signal()
    duplicate_requested = Signal()
    group_requested = Signal()
    mask_requested = Signal()
    merge_down_requested = Signal()
    flatten_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._doc: Document | None = None
        self._refreshing = False
        self._build_ui()

    # ---- Build UI -----------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Row 1: blend mode
        r1 = QHBoxLayout()
        self._blend_combo = _BlendModeCombo()
        for mode in BlendMode:
            self._blend_combo.addItem(mode.name.replace("_", " ").title(), mode)
        self._blend_combo.currentIndexChanged.connect(self._on_blend_changed)
        self._blend_combo.hover_preview.connect(self.blend_mode_hovered.emit)
        self._blend_combo.hover_ended.connect(self.blend_mode_hover_ended.emit)
        r1.addWidget(self._blend_combo, 1)
        root.addLayout(r1)

        # Row 2: opacity
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Opacity"))
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setValue(100)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        r2.addWidget(self._opacity_slider, 1)
        self._opacity_label = QLabel("100 %")
        self._opacity_label.setFixedWidth(40)
        self._opacity_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        r2.addWidget(self._opacity_label)
        root.addLayout(r2)

        # Layer list
        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._list.currentRowChanged.connect(self._on_row_changed)
        root.addWidget(self._list, 1)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(2)
        for label, tip, sig in [
            ("+", "New layer", self.add_requested),
            ("Grp", "New group", self.group_requested),
            ("Dup", "Duplicate", self.duplicate_requested),
            ("Msk", "Add mask", self.mask_requested),
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
        """Rebuild the list from the document's layer stack."""
        self._doc = document
        self._refreshing = True

        self._list.clear()
        for layer in reversed(list(document.layers)):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, layer.id)
            item.setSizeHint(QSize(0, 30))
            widget = _LayerItemWidget(layer.id, layer.name, layer.visible, layer.locked)
            widget.visibility_clicked.connect(self.visibility_toggled.emit)
            widget.lock_clicked.connect(self.lock_toggled.emit)
            self._list.addItem(item)
            self._list.setItemWidget(item, widget)

        # Highlight active layer
        active_idx = len(document.layers) - 1 - document.layers.active_index
        if 0 <= active_idx < self._list.count():
            self._list.setCurrentRow(active_idx)

        # Sync opacity slider & blend combo to the active layer
        active = document.layers.active_layer
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

    # ---- Internal slots -----------------------------------------------------

    def _on_row_changed(self, row: int) -> None:
        if self._refreshing or row < 0 or not self._doc:
            return
        stack_idx = len(self._doc.layers) - 1 - row
        self.layer_selected.emit(stack_idx)
        # Sync opacity slider and blend combo to the newly selected layer
        if 0 <= stack_idx < len(self._doc.layers):
            layer = self._doc.layers[stack_idx]
            self._opacity_slider.blockSignals(True)
            self._opacity_slider.setValue(int(layer.opacity * 100))
            self._opacity_slider.blockSignals(False)
            self._opacity_label.setText(f"{int(layer.opacity * 100)} %")
            blend_idx = self._blend_combo.findData(layer.blend_mode)
            if blend_idx >= 0:
                self._blend_combo.blockSignals(True)
                self._blend_combo.setCurrentIndex(blend_idx)
                self._blend_combo.blockSignals(False)

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
        """Toggle visibility of the currently selected layer."""
        item = self._list.currentItem()
        if item:
            layer_id = item.data(Qt.ItemDataRole.UserRole)
            if layer_id:
                self.visibility_toggled.emit(layer_id)
