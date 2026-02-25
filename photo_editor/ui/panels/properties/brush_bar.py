"""Brush properties bar — horizontal bar shown when brush-type tools are active.

Controls: brush preset dropdown, size, hardness, opacity, flow, spacing, rotation,
blend mode. All values sync bidirectionally with tools and the global BrushManager.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QImage, QPixmap, QIcon
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from .base import ACCENT, COMBO, FLAT_BTN, LABEL, SPIN, make_separator


class BrushPropertiesBar(QWidget):
    """Horizontal properties bar for Brush / Eraser / Clone Stamp / Healing Brush."""

    property_changed = Signal(str, object)

    _BRUSH_TOOLS = {"Brush", "Eraser", "Clone Stamp", "Healing Brush"}

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        # ----- Brush Preset Selector Button -----
        self._preset_btn = QPushButton("▾ Default")
        self._preset_btn.setFixedHeight(24)
        self._preset_btn.setMinimumWidth(120)
        self._preset_btn.setMaximumWidth(220)
        self._preset_btn.setIconSize(QSize(20, 20))
        self._preset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._preset_btn.setStyleSheet(FLAT_BTN.format())
        self._preset_btn.clicked.connect(self._toggle_preset_popup)
        layout.addWidget(self._preset_btn)

        self._preset_popup = None

        layout.addWidget(make_separator())

        # ----- Size -----
        lbl_size = QLabel("Size")
        lbl_size.setStyleSheet(LABEL)
        layout.addWidget(lbl_size)

        self._size_spin = QSpinBox()
        self._size_spin.setRange(1, 5000)
        self._size_spin.setValue(20)
        self._size_spin.setSuffix(" px")
        self._size_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._size_spin.setMaximumWidth(70)
        self._size_spin.setMaximumHeight(22)
        self._size_spin.setStyleSheet(SPIN.format(max_w=70, accent=ACCENT))
        self._size_spin.valueChanged.connect(lambda v: self._emit("size", v))
        layout.addWidget(self._size_spin)

        layout.addWidget(make_separator())

        # ----- Hardness -----
        lbl_hard = QLabel("Hardness")
        lbl_hard.setStyleSheet(LABEL)
        layout.addWidget(lbl_hard)

        self._hardness_spin = QSpinBox()
        self._hardness_spin.setRange(0, 100)
        self._hardness_spin.setValue(80)
        self._hardness_spin.setSuffix(" %")
        self._hardness_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._hardness_spin.setMaximumWidth(60)
        self._hardness_spin.setMaximumHeight(22)
        self._hardness_spin.setStyleSheet(SPIN.format(max_w=60, accent=ACCENT))
        self._hardness_spin.valueChanged.connect(
            lambda v: self._emit("hardness", v / 100.0))
        layout.addWidget(self._hardness_spin)

        layout.addWidget(make_separator())

        # ----- Opacity -----
        lbl_op = QLabel("Opacity")
        lbl_op.setStyleSheet(LABEL)
        layout.addWidget(lbl_op)

        self._opacity_spin = QSpinBox()
        self._opacity_spin.setRange(0, 100)
        self._opacity_spin.setValue(100)
        self._opacity_spin.setSuffix(" %")
        self._opacity_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._opacity_spin.setMaximumWidth(60)
        self._opacity_spin.setMaximumHeight(22)
        self._opacity_spin.setStyleSheet(SPIN.format(max_w=60, accent=ACCENT))
        self._opacity_spin.valueChanged.connect(
            lambda v: self._emit("opacity", v / 100.0))
        layout.addWidget(self._opacity_spin)

        layout.addWidget(make_separator())

        # ----- Flow -----
        lbl_flow = QLabel("Flow")
        lbl_flow.setStyleSheet(LABEL)
        layout.addWidget(lbl_flow)

        self._flow_spin = QSpinBox()
        self._flow_spin.setRange(0, 100)
        self._flow_spin.setValue(100)
        self._flow_spin.setSuffix(" %")
        self._flow_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._flow_spin.setMaximumWidth(60)
        self._flow_spin.setMaximumHeight(22)
        self._flow_spin.setStyleSheet(SPIN.format(max_w=60, accent=ACCENT))
        self._flow_spin.valueChanged.connect(
            lambda v: self._emit("flow", v / 100.0))
        layout.addWidget(self._flow_spin)

        layout.addWidget(make_separator())

        # ----- Spacing -----
        lbl_sp = QLabel("Spacing")
        lbl_sp.setStyleSheet(LABEL)
        layout.addWidget(lbl_sp)

        self._spacing_spin = QSpinBox()
        self._spacing_spin.setRange(1, 200)
        self._spacing_spin.setValue(25)
        self._spacing_spin.setSuffix(" %")
        self._spacing_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._spacing_spin.setMaximumWidth(60)
        self._spacing_spin.setMaximumHeight(22)
        self._spacing_spin.setStyleSheet(SPIN.format(max_w=60, accent=ACCENT))
        self._spacing_spin.valueChanged.connect(
            lambda v: self._emit("spacing", v / 100.0))
        layout.addWidget(self._spacing_spin)

        layout.addWidget(make_separator())

        # ----- Rotation -----
        lbl_rot = QLabel("Rotation")
        lbl_rot.setStyleSheet(LABEL)
        layout.addWidget(lbl_rot)

        self._rotation_spin = QSpinBox()
        self._rotation_spin.setRange(0, 360)
        self._rotation_spin.setValue(0)
        self._rotation_spin.setSuffix("°")
        self._rotation_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._rotation_spin.setMaximumWidth(55)
        self._rotation_spin.setMaximumHeight(22)
        self._rotation_spin.setStyleSheet(SPIN.format(max_w=55, accent=ACCENT))
        self._rotation_spin.valueChanged.connect(
            lambda v: self._emit("rotation", float(v)))
        layout.addWidget(self._rotation_spin)

        layout.addWidget(make_separator())

        # ----- Blend Mode -----
        lbl_bm = QLabel("Mode")
        lbl_bm.setStyleSheet(LABEL)
        layout.addWidget(lbl_bm)

        self._blend_combo = QComboBox()
        self._blend_combo.addItems([
            "Normal", "Multiply", "Screen", "Overlay",
            "Darken", "Lighten", "Color Dodge", "Color Burn",
            "Soft Light", "Hard Light", "Difference", "Exclusion",
        ])
        self._blend_combo.setMaximumHeight(24)
        self._blend_combo.setFixedWidth(100)
        self._blend_combo.setStyleSheet(COMBO.format(widget="QComboBox", accent=ACCENT))
        self._blend_combo.currentTextChanged.connect(
            lambda t: self._emit("blend_mode", t.lower().replace(" ", "_")))
        layout.addWidget(self._blend_combo)

        layout.addStretch()

        self._mgr = None
        self._tool = None
        self._syncing = False
        self._popup_category: QComboBox | None = None
        self._popup_list: QListWidget | None = None
        self._preset_refs: dict = {}

    # ---- Helpers ----

    def _emit(self, key: str, value: object) -> None:
        if not self._syncing:
            self.property_changed.emit(key, value)

    # ---- Preset Popup ----

    def _toggle_preset_popup(self) -> None:
        if self._preset_popup and self._preset_popup.isVisible():
            self._preset_popup.hide()
            return
        if self._mgr is None:
            return
        self._build_preset_popup()
        pos = self._preset_btn.mapToGlobal(
            self._preset_btn.rect().bottomLeft()
        )
        self._preset_popup.move(pos)
        self._preset_popup.show()

    def _build_preset_popup(self) -> None:
        if self._preset_popup is None:
            self._preset_popup = QWidget(
                self.window(), Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
            )
            self._preset_popup.setFixedSize(280, 300)
            popup_layout = QVBoxLayout(self._preset_popup)
            popup_layout.setContentsMargins(4, 4, 4, 4)
            popup_layout.setSpacing(2)

            self._popup_category = QComboBox()
            self._popup_category.currentTextChanged.connect(self._on_popup_category)
            popup_layout.addWidget(self._popup_category)

            self._popup_list = QListWidget()
            self._popup_list.setIconSize(QSize(160, 36))
            self._popup_list.setSpacing(1)
            self._popup_list.itemClicked.connect(self._on_popup_item_click)
            popup_layout.addWidget(self._popup_list)

            self._preset_popup.setStyleSheet("""
                QWidget {
                    background-color: #2a2c30;
                    border: 1px solid rgba(255,255,255,0.12);
                    border-radius: 6px;
                }
                QListWidget {
                    background-color: #2a2c30;
                    border: none;
                    outline: none;
                }
                QListWidget::item {
                    border-bottom: 1px solid rgba(255,255,255,0.06);
                    color: #e0e4e8;
                    padding: 2px 4px;
                }
                QListWidget::item:selected {
                    background-color: #4a6fa5;
                }
                QListWidget::item:hover {
                    background-color: rgba(255,255,255,0.06);
                }
                QComboBox {
                    background: rgba(0,0,0,0.2);
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 4px;
                    color: #e0e4e8;
                    padding: 4px 8px;
                }
            """)

        # Populate
        self._popup_category.blockSignals(True)
        self._popup_category.clear()
        self._popup_category.addItem("All Brushes")
        for name in self._mgr.collection_names:
            self._popup_category.addItem(name)
        self._popup_category.blockSignals(False)
        self._populate_popup_list(None)

    def _populate_popup_list(self, collection: str | None) -> None:
        self._popup_list.clear()
        presets = self._mgr.search("", collection)
        for p in presets:
            item = QListWidgetItem(f"  {p.size}  {p.name}")
            item.setSizeHint(QSize(0, 40))
            item.setData(Qt.ItemDataRole.UserRole, id(p))
            # Try to set icon
            try:
                thumb = p.preview_thumbnail(32, 140)
                if thumb is not None:
                    h, w = thumb.shape[:2]
                    img = QImage(thumb.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
                    item.setIcon(QIcon(QPixmap.fromImage(img)))
            except Exception:
                pass
            self._popup_list.addItem(item)
        self._preset_refs = {id(p): p for p in presets}

    def _on_popup_category(self, text: str) -> None:
        col = None if text == "All Brushes" else text
        self._populate_popup_list(col)

    def _on_popup_item_click(self, item: QListWidgetItem) -> None:
        pid = item.data(Qt.ItemDataRole.UserRole)
        preset = self._preset_refs.get(pid)
        if preset and self._mgr:
            self._mgr.set_active(preset)
        if self._preset_popup:
            self._preset_popup.hide()

    # ---- Sync ----

    def set_brush_manager(self, mgr) -> None:
        self._mgr = mgr
        mgr.brush_changed.connect(self._on_brush_changed)

    def _on_brush_changed(self, preset) -> None:
        """Handle global brush change — update button icon and sync values."""
        if preset:
            self._preset_btn.setText(f"▾ {preset.name}")
            # Show brush tip as icon on the button
            try:
                if preset.tip_image is not None:
                    import cv2
                    tip = preset.tip_image
                    th, tw = tip.shape[:2]
                    icon_sz = 20
                    scale = icon_sz / max(th, tw, 1)
                    nh = max(1, int(th * scale))
                    nw = max(1, int(tw * scale))
                    scaled = cv2.resize(tip, (nw, nh), interpolation=cv2.INTER_AREA)
                    import numpy as np
                    rgba = np.zeros((nh, nw, 4), dtype=np.uint8)
                    rgba[..., :3] = 220  # light grey brush preview
                    rgba[..., 3] = scaled
                    img = QImage(rgba.data, nw, nh, nw * 4,
                                 QImage.Format.Format_RGBA8888)
                    self._preset_btn.setIcon(QIcon(QPixmap.fromImage(img)))
                else:
                    self._preset_btn.setIcon(QIcon())
            except Exception:
                self._preset_btn.setIcon(QIcon())

            # Sync spin values from the preset
            self._syncing = True
            try:
                self._size_spin.setValue(preset.size)
                self._hardness_spin.setValue(int(preset.hardness * 100))
                self._opacity_spin.setValue(int(preset.opacity * 100))
                self._flow_spin.setValue(int(preset.flow * 100))
                self._spacing_spin.setValue(int(preset.spacing * 100))
                self._rotation_spin.setValue(int(preset.rotation))
            finally:
                self._syncing = False
        else:
            self._preset_btn.setText("▾ Default")
            self._preset_btn.setIcon(QIcon())

    def sync_from_tool(self, tool) -> None:
        """Populate bar values from the active tool."""
        self._syncing = True
        self._tool = tool
        try:
            if hasattr(tool, "size"):
                self._size_spin.setValue(int(tool.size))
            if hasattr(tool, "hardness"):
                self._hardness_spin.setValue(int(tool.hardness * 100))
            if hasattr(tool, "opacity"):
                self._opacity_spin.setValue(int(tool.opacity * 100))
            if hasattr(tool, "flow"):
                self._flow_spin.setValue(int(getattr(tool, "flow", 1.0) * 100))
            else:
                self._flow_spin.setValue(100)
            if hasattr(tool, "spacing"):
                self._spacing_spin.setValue(int(tool.spacing * 100))
            # Show/hide flow for tools that don't have it
            has_flow = hasattr(tool, "flow")
            # Flow label is the parent of the spin
            self._flow_spin.setVisible(has_flow)
        finally:
            self._syncing = False
