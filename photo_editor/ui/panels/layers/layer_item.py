"""Single layer row widget for the layers list."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from .base import ROW_HEIGHT, THUMB_SIZE, INDENT_WIDTH, MAX_INDENT_DEPTH
from ...styles import render_qss
from photo_editor.ui.theme import ThemeManager
from .icons import icon_eye, icon_lock, icon_mask, ico_adjustment, ico_filter, ico_mask_layer, ico_text


class LayerItemWidget(QWidget):
    """Custom widget for a single row in the layers list."""

    visibility_clicked = Signal(str)
    lock_clicked = Signal(str)
    collapse_clicked = Signal(str)
    rename_finished = Signal(str, str)

    # Data fingerprint for memoization (skip re-render when unchanged)
    _data_key: tuple = ()

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
        has_children: bool = False,
        masks_collapsed: bool = False,
        thumbnail: QPixmap | None = None,
        is_adjustment: bool = False,
        is_filter: bool = False,
        is_text: bool = False,
        is_mask_layer: bool = False,
        is_clipped: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._layer_id = layer_id
        self._orig_name = name
        self._edit: QLineEdit | None = None
        self._rename_done = False
        self._is_clipped = is_clipped
        palette = ThemeManager.instance().active_palette

        # Build memoization key (all the data that affects rendering)
        self._data_key = (
            layer_id, name, visible, locked, indent, is_group, is_collapsed,
            has_mask, has_children, masks_collapsed, is_adjustment, is_filter,
            is_text, is_mask_layer, is_clipped,
        )

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(render_qss("layer_item_root.qss"))

        layout = QHBoxLayout(self)
        # Cap visual indent at MAX_INDENT_DEPTH
        capped = min(indent, MAX_INDENT_DEPTH)
        left_margin = 4 + capped * INDENT_WIDTH
        layout.setContentsMargins(left_margin, 2, 4, 2)
        layout.setSpacing(6)

        # Depth indicator for deeply nested layers (>5 levels)
        if indent > MAX_INDENT_DEPTH:
            dots = "\u00B7" * min(indent - MAX_INDENT_DEPTH, 5)
            depth_lbl = QLabel(dots)
            depth_lbl.setStyleSheet(f"color: #666; background: transparent; font-size: 8px;")
            depth_lbl.setFixedWidth(12)
            layout.addWidget(depth_lbl)

        # Clipping indicator prefix
        if is_clipped:
            clip_lbl = QLabel("\u2310")  # ⌐ clip indicator
            clip_lbl.setStyleSheet(
                f"color: {palette.get('accent', '#9b59b6')};"
                "background: transparent; font-size: 14px; font-weight: bold;"
            )
            clip_lbl.setFixedWidth(14)
            clip_lbl.setToolTip("Clipped to layer below")
            layout.addWidget(clip_lbl)

        if is_group:
            arrow_text = "\u25B6" if is_collapsed else "\u25BC"
            self._arrow_btn = QPushButton(arrow_text)
            self._arrow_btn.setFixedSize(18, 18)
            self._arrow_btn.setFlat(True)
            arrow_font = QFont("Segoe UI Symbol")
            arrow_font.setPointSize(10)
            arrow_font.setWeight(QFont.Weight.DemiBold)
            self._arrow_btn.setFont(arrow_font)
            self._arrow_btn.setStyleSheet(render_qss("layer_item_arrow.qss", palette))
            self._arrow_btn.setToolTip("Collapse" if not is_collapsed else "Expand")
            self._arrow_btn.clicked.connect(
                lambda: self.collapse_clicked.emit(layer_id),
            )
            layout.addWidget(self._arrow_btn)
        elif has_children:
            arrow_text = "\u25B6" if masks_collapsed else "\u25BC"
            self._arrow_btn = QPushButton(arrow_text)
            self._arrow_btn.setFixedSize(18, 18)
            self._arrow_btn.setFlat(True)
            arrow_font = QFont("Segoe UI Symbol")
            arrow_font.setPointSize(10)
            arrow_font.setWeight(QFont.Weight.DemiBold)
            self._arrow_btn.setFont(arrow_font)
            self._arrow_btn.setStyleSheet(render_qss("layer_item_arrow.qss", palette))
            self._arrow_btn.setToolTip("Show masks" if masks_collapsed else "Hide masks")
            self._arrow_btn.clicked.connect(
                lambda: self.collapse_clicked.emit(layer_id),
            )
            layout.addWidget(self._arrow_btn)

        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        self._thumb_label.setStyleSheet(render_qss("layer_item_thumb.qss", palette))
        if is_mask_layer:
            if thumbnail:
                self._thumb_label.setPixmap(thumbnail)
            else:
                self._thumb_label.setPixmap(ico_mask_layer().pixmap(THUMB_SIZE - 4, THUMB_SIZE - 4))
                self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        elif is_adjustment:
            self._thumb_label.setPixmap(ico_adjustment().pixmap(THUMB_SIZE - 4, THUMB_SIZE - 4))
            self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        elif is_filter:
            self._thumb_label.setPixmap(ico_filter().pixmap(THUMB_SIZE - 4, THUMB_SIZE - 4))
            self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        elif is_text:
            self._thumb_label.setPixmap(ico_text().pixmap(THUMB_SIZE - 4, THUMB_SIZE - 4))
            self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        elif thumbnail:
            self._thumb_label.setPixmap(thumbnail)
        layout.addWidget(self._thumb_label)

        self._name_label = QLabel(name)
        self._name_label.setStyleSheet(
            render_qss(
                "layer_item_name.qss",
                palette,
                weight=" font-weight: bold;" if is_group else "",
            )
        )
        layout.addWidget(self._name_label, 1)

        if has_mask:
            mask_lbl = QLabel()
            mask_lbl.setPixmap(icon_mask(True).pixmap(14, 14))
            mask_lbl.setToolTip("Layer has mask")
            mask_lbl.setStyleSheet(render_qss("layer_item_transparent.qss"))
            layout.addWidget(mask_lbl)

        if locked:
            self._lock_icon = QLabel()
            self._lock_icon.setPixmap(icon_lock(True).pixmap(16, 16))
            self._lock_icon.setFixedSize(20, 20)
            self._lock_icon.setToolTip("Locked")
            self._lock_icon.setStyleSheet(render_qss("layer_item_transparent.qss"))
            layout.addWidget(self._lock_icon)

        self._vis_btn = QPushButton()
        self._vis_btn.setIcon(icon_eye(visible))
        self._vis_btn.setIconSize(QSize(18, 18))
        self._vis_btn.setFixedSize(24, 24)
        self._vis_btn.setFlat(True)
        self._vis_btn.setToolTip("Toggle visibility")
        self._vis_btn.setStyleSheet(render_qss("layer_item_visibility_button.qss"))
        self._vis_btn.clicked.connect(
            lambda: self.visibility_clicked.emit(layer_id),
        )
        layout.addWidget(self._vis_btn)

    def update_state(self, visible: bool, locked: bool) -> None:
        self._vis_btn.setIcon(icon_eye(visible))
        if locked and not hasattr(self, '_lock_icon'):
            self._lock_icon = QLabel()
            self._lock_icon.setPixmap(icon_lock(True).pixmap(16, 16))
            self._lock_icon.setFixedSize(20, 20)
            self._lock_icon.setToolTip("Locked")
            self._lock_icon.setStyleSheet(render_qss("layer_item_transparent.qss"))
            lay = self.layout()
            idx = lay.indexOf(self._vis_btn)
            lay.insertWidget(idx, self._lock_icon)
        elif not locked and hasattr(self, '_lock_icon'):
            self._lock_icon.setParent(None)
            self._lock_icon.deleteLater()
            del self._lock_icon

    def start_rename(self) -> None:
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
