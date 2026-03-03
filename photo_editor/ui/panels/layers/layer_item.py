"""Single layer row widget for the layers list."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from .base import ROW_HEIGHT, THUMB_SIZE
from photo_editor.ui.theme import ThemeManager
from .icons import icon_eye, icon_lock, icon_mask, ico_adjustment, ico_filter, ico_mask_layer, ico_text


class LayerItemWidget(QWidget):
    """Custom widget for a single row in the layers list."""

    visibility_clicked = Signal(str)
    lock_clicked = Signal(str)
    collapse_clicked = Signal(str)
    rename_finished = Signal(str, str)

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
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._layer_id = layer_id
        self._orig_name = name
        self._edit: QLineEdit | None = None
        self._rename_done = False
        palette = ThemeManager.instance().active_palette

        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        left_margin = 4 + indent * 16
        layout.setContentsMargins(left_margin, 2, 4, 2)
        layout.setSpacing(6)

        if is_group:
            arrow_text = "\u25B6" if is_collapsed else "\u25BC"
            self._arrow_btn = QPushButton(arrow_text)
            self._arrow_btn.setFixedSize(18, 18)
            self._arrow_btn.setFlat(True)
            self._arrow_btn.setStyleSheet(
                f"font-size: 9px; padding: 0; color: {palette['fg']}; background: transparent;")
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
            self._arrow_btn.setStyleSheet(
                f"font-size: 9px; padding: 0; color: {palette['fg']}; background: transparent;")
            self._arrow_btn.setToolTip("Show masks" if masks_collapsed else "Hide masks")
            self._arrow_btn.clicked.connect(
                lambda: self.collapse_clicked.emit(layer_id),
            )
            layout.addWidget(self._arrow_btn)

        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        self._thumb_label.setStyleSheet(
            f"border: 1px solid {palette['border']}; background: transparent;")
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
            f"color: {palette['fg']}; background: transparent; padding: 0 2px;"
            + (" font-weight: bold;" if is_group else ""))
        layout.addWidget(self._name_label, 1)

        if has_mask:
            mask_lbl = QLabel()
            mask_lbl.setPixmap(icon_mask(True).pixmap(14, 14))
            mask_lbl.setToolTip("Layer has mask")
            mask_lbl.setStyleSheet("background: transparent;")
            layout.addWidget(mask_lbl)

        if locked:
            self._lock_icon = QLabel()
            self._lock_icon.setPixmap(icon_lock(True).pixmap(16, 16))
            self._lock_icon.setFixedSize(20, 20)
            self._lock_icon.setToolTip("Locked")
            self._lock_icon.setStyleSheet("background: transparent;")
            layout.addWidget(self._lock_icon)

        self._vis_btn = QPushButton()
        self._vis_btn.setIcon(icon_eye(visible))
        self._vis_btn.setIconSize(QSize(18, 18))
        self._vis_btn.setFixedSize(24, 24)
        self._vis_btn.setFlat(True)
        self._vis_btn.setToolTip("Toggle visibility")
        self._vis_btn.setStyleSheet("background: transparent; border: none;")
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
            self._lock_icon.setStyleSheet("background: transparent;")
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
