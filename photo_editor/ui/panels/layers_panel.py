"""Layers panel — visibility toggles, lock buttons, opacity, blend mode, groups.

Visual design inspired by professional photo editors: dark panel with purple
accent colour for the selected layer, compact header with opacity / blend-mode
controls, thumbnail previews, and an icon-based bottom toolbar.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QPushButton, QSizePolicy,
    QSlider, QSpinBox, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
    QVBoxLayout, QWidget,
)

from ...core.document import Document
from ...core.enums import BlendMode, LayerType

import numpy as np

# ---- Palette constants ------------------------------------------------------

_BG           = "#2b2b2b"
_BG_HEADER    = "#3a3a3a"
_BG_LIST      = "#262626"
_SEL_PURPLE   = "#5c2d82"     # selection highlight
_SEL_BORDER   = "#7a3da8"
_BORDER       = "#444444"
_TEXT          = "#cccccc"
_TEXT_DIM      = "#888888"
_ICON_ACTIVE  = "#cccccc"
_ICON_INACTIVE = "#555555"
_BTN_BG       = "#333333"
_BTN_HOVER    = "#444444"

# ---- Custom data roles ------------------------------------------------------

_ROLE_LAYER_ID  = Qt.ItemDataRole.UserRole
_ROLE_IS_GROUP  = Qt.ItemDataRole.UserRole + 1
_ROLE_INDENT    = Qt.ItemDataRole.UserRole + 2
_ROLE_PARENT_ID = Qt.ItemDataRole.UserRole + 3

_THUMB_SIZE = 36
_ROW_HEIGHT = 48


# ---- Vector icon helpers ---------------------------------------------------

def _draw_icon(size: int, draw_fn) -> QIcon:
    """Helper to create a QIcon by calling *draw_fn(QPainter, size)*."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_fn(p, size)
    p.end()
    return QIcon(pm)


def _icon_eye(visible: bool) -> QIcon:
    def _draw(p: QPainter, s: int):
        cx, cy = s / 2, s / 2
        col = QColor(_ICON_ACTIVE) if visible else QColor(_ICON_INACTIVE)
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
            p.drawEllipse(QPointF(cx, cy), 2.8, 2.8)
        else:
            p.setPen(QPen(QColor(170, 70, 70), 1.5))
            p.drawLine(QPointF(4, s - 4), QPointF(s - 4, 4))
    return _draw_icon(18, _draw)


def _icon_lock(locked: bool) -> QIcon:
    def _draw(p: QPainter, s: int):
        col = QColor(_ICON_ACTIVE) if locked else QColor(_ICON_INACTIVE)
        cx = s / 2
        p.setPen(QPen(col, 1.4))
        bw, bh = 10.0, 6.0
        bx, by = (s - bw) / 2, s - bh - 2
        p.setBrush(col if locked else Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(bx, by, bw, bh), 1.5, 1.5)
        p.setBrush(Qt.BrushStyle.NoBrush)
        sw, sx = 6.0, (s - 6.0) / 2
        shackle = QPainterPath()
        shackle.moveTo(sx, by)
        shackle.lineTo(sx, by - 3)
        shackle.quadTo(sx, by - 6, cx, by - 6)
        shackle.quadTo(sx + sw, by - 6, sx + sw, by - 3)
        shackle.lineTo(sx + sw, by if locked else by - 5)
        p.drawPath(shackle)
    return _draw_icon(18, _draw)


def _icon_mask(has_mask: bool) -> QIcon:
    if not has_mask:
        return QIcon(QPixmap(18, 18))

    def _draw(p: QPainter, s: int):
        p.setPen(QPen(QColor(180, 180, 180), 1.2))
        p.setBrush(QColor(180, 180, 180, 50))
        p.drawEllipse(QRectF(2, 2, s - 4, s - 4))
    return _draw_icon(18, _draw)


# ---- Tiny toolbar-icon builders --------------------------------------------

def _tb_icon(draw_fn, size: int = 16) -> QIcon:
    return _draw_icon(size, draw_fn)


def _ico_new_layer():
    def _d(p, s):
        col = QColor(_ICON_ACTIVE)
        p.setPen(QPen(col, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(2, 4, s - 4, s - 6), 1, 1)
        # folded corner
        p.drawLine(QPointF(s - 5, 4), QPointF(s - 5, 7))
        p.drawLine(QPointF(s - 5, 7), QPointF(s - 2, 7))
    return _tb_icon(_d)


def _ico_fx():
    def _d(p, s):
        p.setPen(QPen(QColor(_ICON_ACTIVE), 1.4))
        from PySide6.QtGui import QFont
        f = QFont("Segoe UI", 9, QFont.Weight.Bold)
        p.setFont(f)
        p.drawText(QRectF(0, 0, s, s), Qt.AlignmentFlag.AlignCenter, "fx")
    return _tb_icon(_d)


def _ico_mask():
    def _d(p, s):
        p.setPen(QPen(QColor(_ICON_ACTIVE), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(2, 2, s - 4, s - 4))
    return _tb_icon(_d)


def _ico_adjustment():
    """Half-filled circle ● for adjustment layers."""
    def _d(p, s):
        cx, cy, r = s / 2, s / 2, s / 2 - 2
        p.setPen(QPen(QColor(_ICON_ACTIVE), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)
        # filled left half
        clip = QPainterPath()
        clip.addRect(QRectF(0, 0, cx, s))
        p.setClipPath(clip)
        p.setBrush(QColor(_ICON_ACTIVE))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), r, r)
    return _tb_icon(_d)


def _ico_filter():
    """Three stacked horizontal lines (filter/funnel icon)."""
    def _d(p, s):
        col = QColor(_ICON_ACTIVE)
        p.setPen(QPen(col, 1.4))
        import math
        cx, cy = s / 2, s / 2
        # Diamond / sparkle shape
        r = s / 2 - 2
        pts = [
            QPointF(cx, cy - r),       # top
            QPointF(cx + r * 0.35, cy - r * 0.35),
            QPointF(cx + r, cy),       # right
            QPointF(cx + r * 0.35, cy + r * 0.35),
            QPointF(cx, cy + r),       # bottom
            QPointF(cx - r * 0.35, cy + r * 0.35),
            QPointF(cx - r, cy),       # left
            QPointF(cx - r * 0.35, cy - r * 0.35),
        ]
        path = QPainterPath()
        path.moveTo(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        path.closeSubpath()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
    return _tb_icon(_d)


def _ico_text():
    """Bold T for text layers."""
    def _d(p, s):
        col = QColor(_ICON_ACTIVE)
        p.setPen(QPen(col, 1.6))
        from PySide6.QtGui import QFont
        f = QFont("Segoe UI", int(s * 0.6), QFont.Weight.Bold)
        p.setFont(f)
        p.drawText(QRectF(0, 0, s, s), Qt.AlignmentFlag.AlignCenter, "T")
    return _tb_icon(_d)


def _ico_chain():
    def _d(p, s):
        col = QColor(_ICON_ACTIVE)
        p.setPen(QPen(col, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(3, 2, s - 6, 5), 2, 2)
        p.drawRoundedRect(QRectF(3, s - 7, s - 6, 5), 2, 2)
        p.drawLine(QPointF(s / 2, 7), QPointF(s / 2, s - 7))
    return _tb_icon(_d)


def _ico_eraser():
    def _d(p, s):
        p.setPen(QPen(QColor(_ICON_ACTIVE), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(4, s - 3), QPointF(s - 4, 3))
        p.drawLine(QPointF(s - 6, s - 3), QPointF(s - 2, s - 3))
    return _tb_icon(_d)


def _ico_folder():
    def _d(p, s):
        col = QColor(_ICON_ACTIVE)
        p.setPen(QPen(col, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(2, 5)
        path.lineTo(2, s - 3)
        path.lineTo(s - 2, s - 3)
        path.lineTo(s - 2, 6)
        path.lineTo(s / 2 + 1, 6)
        path.lineTo(s / 2 - 1, 4)
        path.lineTo(2, 4)
        path.closeSubpath()
        p.drawPath(path)
    return _tb_icon(_d)


def _ico_duplicate():
    def _d(p, s):
        col = QColor(_ICON_ACTIVE)
        p.setPen(QPen(col, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(1, 3, s - 5, s - 5), 1, 1)
        p.drawRoundedRect(QRectF(4, 1, s - 5, s - 5), 1, 1)
    return _tb_icon(_d)


def _ico_move():
    def _d(p, s):
        col = QColor(_ICON_ACTIVE)
        p.setPen(QPen(col, 1.4))
        cx, cy = s / 2, s / 2
        p.drawLine(QPointF(cx, 2), QPointF(cx, s - 2))
        p.drawLine(QPointF(2, cy), QPointF(s - 2, cy))
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            tip = QPointF(cx + dx * (cx - 2), cy + dy * (cy - 2))
            p.drawLine(tip, QPointF(tip.x() - dx * 3 + dy * 2, tip.y() - dy * 3 + dx * 2))
            p.drawLine(tip, QPointF(tip.x() - dx * 3 - dy * 2, tip.y() - dy * 3 - dx * 2))
    return _tb_icon(_d)


def _ico_grid():
    def _d(p, s):
        col = QColor(_ICON_ACTIVE)
        p.setPen(QPen(col, 1.0))
        t = 3
        for r in range(3):
            for c in range(3):
                x = t + c * (s - 2 * t) / 2
                y = t + r * (s - 2 * t) / 2
                w = (s - 2 * t) / 2 - 1
                p.drawRect(QRectF(x, y, w, w))
    return _tb_icon(_d)


def _ico_trash():
    def _d(p, s):
        col = QColor(_ICON_ACTIVE)
        p.setPen(QPen(col, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        # lid
        p.drawLine(QPointF(3, 5), QPointF(s - 3, 5))
        p.drawLine(QPointF(s / 2 - 2, 5), QPointF(s / 2 - 2, 3))
        p.drawLine(QPointF(s / 2 - 2, 3), QPointF(s / 2 + 2, 3))
        p.drawLine(QPointF(s / 2 + 2, 3), QPointF(s / 2 + 2, 5))
        # body
        p.drawLine(QPointF(4, 5), QPointF(5, s - 2))
        p.drawLine(QPointF(5, s - 2), QPointF(s - 5, s - 2))
        p.drawLine(QPointF(s - 5, s - 2), QPointF(s - 4, 5))
    return _tb_icon(_d)


def _ico_settings():
    def _d(p, s):
        col = QColor(_ICON_ACTIVE)
        p.setPen(QPen(col, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = s / 2, s / 2
        p.drawEllipse(QPointF(cx, cy), 3, 3)
        import math
        for i in range(8):
            a = math.radians(i * 45)
            inner, outer = 4.5, 6.5
            p.drawLine(
                QPointF(cx + inner * math.cos(a), cy + inner * math.sin(a)),
                QPointF(cx + outer * math.cos(a), cy + outer * math.sin(a)),
            )
    return _tb_icon(_d)


# ---- Thumbnail helper -------------------------------------------------------

# Pre-built checkerboard tile for thumbnails (built once, reused)
_THUMB_CHECKER: QPixmap | None = None


def _thumb_checker(size: int = _THUMB_SIZE) -> QPixmap:
    global _THUMB_CHECKER
    if _THUMB_CHECKER is None or _THUMB_CHECKER.width() != size:
        _THUMB_CHECKER = QPixmap(size, size)
        _THUMB_CHECKER.fill(QColor(42, 42, 42))
        tp = QPainter(_THUMB_CHECKER)
        tp.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        cs = 4
        light, dark = QColor(70, 70, 70), QColor(50, 50, 50)
        for r in range(0, size, cs):
            for c in range(0, size, cs):
                tp.fillRect(c, r, cs, cs, light if (r // cs + c // cs) % 2 == 0 else dark)
        tp.end()
    return _THUMB_CHECKER


def _make_thumbnail(layer, size: int = _THUMB_SIZE) -> QPixmap:
    """Generate a small QPixmap thumbnail for *layer*."""
    pm = QPixmap(_thumb_checker(size))  # copy pre-built checkerboard

    # Paint the layer pixels scaled into the square
    try:
        px = layer.pixels  # float32, (H, W, 4)
        if px is not None and px.size > 0:
            h, w = px.shape[:2]
            # Downsample before conversion for large layers
            if h > size * 4 or w > size * 4:
                step_h = max(1, h // (size * 2))
                step_w = max(1, w // (size * 2))
                px = px[::step_h, ::step_w]
                h, w = px.shape[:2]
            buf = np.empty((h, w, 4), dtype=np.uint8)
            np.multiply(px[:, :, 2:3], 255, out=buf[:, :, 0:1], casting='unsafe')  # B
            np.multiply(px[:, :, 1:2], 255, out=buf[:, :, 1:2], casting='unsafe')  # G
            np.multiply(px[:, :, 0:1], 255, out=buf[:, :, 2:3], casting='unsafe')  # R
            np.multiply(px[:, :, 3:4], 255, out=buf[:, :, 3:4], casting='unsafe')  # A
            np.clip(buf, 0, 255, out=buf)
            img = QImage(buf.data, w, h, w * 4, QImage.Format.Format_ARGB32)
            scaled = img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.FastTransformation)
            tp = QPainter(pm)
            ox = (size - scaled.width()) // 2
            oy = (size - scaled.height()) // 2
            tp.drawImage(ox, oy, scaled)
            tp.end()
    except Exception:
        pass

    return pm


# ---- Layer item widget -----------------------------------------------------

class _LayerItemWidget(QWidget):
    """Custom widget for a single row in the layers list.

    Layout: [group-arrow?] [thumbnail] [name-label] [mask-badge?] [eye-btn]
    """

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
        thumbnail: QPixmap | None = None,
        is_adjustment: bool = False,
        is_filter: bool = False,
        is_text: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._layer_id = layer_id
        self._orig_name = name
        self._edit: QLineEdit | None = None
        self._rename_done = False

        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        left_margin = 4 + indent * 16
        layout.setContentsMargins(left_margin, 2, 4, 2)
        layout.setSpacing(6)

        # Group expand/collapse toggle
        if is_group:
            arrow_text = "\u25B6" if is_collapsed else "\u25BC"
            self._arrow_btn = QPushButton(arrow_text)
            self._arrow_btn.setFixedSize(18, 18)
            self._arrow_btn.setFlat(True)
            self._arrow_btn.setStyleSheet(
                f"font-size: 9px; padding: 0; color: {_TEXT}; background: transparent;")
            self._arrow_btn.setToolTip("Collapse" if not is_collapsed else "Expand")
            self._arrow_btn.clicked.connect(
                lambda: self.collapse_clicked.emit(layer_id),
            )
            layout.addWidget(self._arrow_btn)

        # Thumbnail
        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)
        self._thumb_label.setStyleSheet(
            f"border: 1px solid {_BORDER}; background: transparent;")
        if is_adjustment:
            self._thumb_label.setPixmap(_ico_adjustment().pixmap(_THUMB_SIZE - 4, _THUMB_SIZE - 4))
            self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        elif is_filter:
            self._thumb_label.setPixmap(_ico_filter().pixmap(_THUMB_SIZE - 4, _THUMB_SIZE - 4))
            self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        elif is_text:
            self._thumb_label.setPixmap(_ico_text().pixmap(_THUMB_SIZE - 4, _THUMB_SIZE - 4))
            self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        elif thumbnail:
            self._thumb_label.setPixmap(thumbnail)
        layout.addWidget(self._thumb_label)

        # Layer name label
        self._name_label = QLabel(name)
        self._name_label.setStyleSheet(
            f"color: {_TEXT}; background: transparent; padding: 0 2px;"
            + (" font-weight: bold;" if is_group else ""))
        layout.addWidget(self._name_label, 1)

        # Mask badge
        if has_mask:
            mask_lbl = QLabel()
            mask_lbl.setPixmap(_icon_mask(True).pixmap(14, 14))
            mask_lbl.setToolTip("Layer has mask")
            mask_lbl.setStyleSheet("background: transparent;")
            layout.addWidget(mask_lbl)

        # Lock indicator (only shown when locked) — left of eye
        if locked:
            self._lock_icon = QLabel()
            self._lock_icon.setPixmap(_icon_lock(True).pixmap(16, 16))
            self._lock_icon.setFixedSize(20, 20)
            self._lock_icon.setToolTip("Locked")
            self._lock_icon.setStyleSheet("background: transparent;")
            layout.addWidget(self._lock_icon)

        # Visibility button (eye icon)
        self._vis_btn = QPushButton()
        self._vis_btn.setIcon(_icon_eye(visible))
        self._vis_btn.setIconSize(QSize(18, 18))
        self._vis_btn.setFixedSize(24, 24)
        self._vis_btn.setFlat(True)
        self._vis_btn.setToolTip("Toggle visibility")
        self._vis_btn.setStyleSheet("background: transparent; border: none;")
        self._vis_btn.clicked.connect(
            lambda: self.visibility_clicked.emit(layer_id),
        )
        layout.addWidget(self._vis_btn)

    # ---- State sync (no rebuild) --------------------------------------------

    def update_state(self, visible: bool, locked: bool) -> None:
        """Sync the eye / lock icons to match the current layer state."""
        self._vis_btn.setIcon(_icon_eye(visible))
        # Lock indicator: add or remove as needed
        if locked and not hasattr(self, '_lock_icon'):
            self._lock_icon = QLabel()
            self._lock_icon.setPixmap(_icon_lock(True).pixmap(16, 16))
            self._lock_icon.setFixedSize(20, 20)
            self._lock_icon.setToolTip("Locked")
            self._lock_icon.setStyleSheet("background: transparent;")
            # Insert before the visibility button
            lay = self.layout()
            idx = lay.indexOf(self._vis_btn)
            lay.insertWidget(idx, self._lock_icon)
        elif not locked and hasattr(self, '_lock_icon'):
            self._lock_icon.setParent(None)
            self._lock_icon.deleteLater()
            del self._lock_icon

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


# ---- Custom delegate for purple selection highlight -------------------------

class _LayerItemDelegate(QStyledItemDelegate):
    """Draw a rounded purple selection rectangle behind the item widget."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = option.rect.adjusted(1, 1, -1, -1)

        if option.state & QStyle.StateFlag.State_Selected:
            painter.setBrush(QColor(_SEL_PURPLE))
            painter.setPen(QPen(QColor(_SEL_BORDER), 1))
            painter.drawRoundedRect(QRectF(rect), 4, 4)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(rect)

        painter.restore()
        # do NOT call super() — the item widget paints on top


# ---- Custom QListWidget with drag-drop support ----------------------------

class _LayerListWidget(QListWidget):
    """QListWidget subclass that handles drag-drop for reorder & reparent."""

    layers_reordered = Signal(list, int)
    layers_dropped_in_group = Signal(list, str)
    layers_unparented = Signal(list)           # remove layers from their group

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setItemDelegate(_LayerItemDelegate(self))

        self.setStyleSheet(f"""
            QListWidget {{
                background-color: {_BG_LIST};
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                background: transparent;
                border: none;
                padding: 0px;
            }}
            QListWidget::item:selected {{
                background: transparent;   /* delegate paints selection */
            }}
        """)

    def dropEvent(self, event) -> None:
        source_items = self.selectedItems()
        if not source_items:
            event.ignore()
            return

        source_ids = [item.data(_ROLE_LAYER_ID) for item in source_items]
        # Check if any dragged layers are currently inside a group
        source_parent_ids = [item.data(_ROLE_PARENT_ID) for item in source_items]
        any_in_group = any(pid for pid in source_parent_ids)

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
                event.ignore()   # prevent Qt internal move
                return

            # Drop ON a child of a group: reparent into the child's group
            if parent_id and not is_group:
                if target_id not in source_ids:
                    self.layers_dropped_in_group.emit(source_ids, parent_id)
                event.ignore()
                return

            # Drop on a top-level item (no parent, not inside a group)
            # If the source layers were in a group, unparent them first
            if any_in_group and not parent_id:
                self.layers_unparented.emit(source_ids)
                event.ignore()
                return

            # Simple reorder among top-level layers
            drop_row = self.row(target_item)
            if rel_y > 0.5 * item_rect.height():
                drop_row += 1
            self.layers_reordered.emit(source_ids, drop_row)
        else:
            # Dropped on empty space — unparent if needed, then reorder
            if any_in_group:
                self.layers_unparented.emit(source_ids)
                event.ignore()
                return
            self.layers_reordered.emit(source_ids, self.count())

        event.ignore()   # always prevent Qt internal move; we rebuild via refresh


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


# ---- Separator line --------------------------------------------------------

def _h_separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"color: {_BORDER};")
    line.setFixedHeight(1)
    return line


# ---- Bottom toolbar button helper ------------------------------------------

def _toolbar_btn(icon: QIcon, tooltip: str, signal) -> QPushButton:
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
            background: {_BTN_HOVER};
        }}
    """)
    b.clicked.connect(signal.emit)
    return b


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
    adjustment_layer_requested = Signal(str)  # adjustment name
    edit_adjustment_requested = Signal(str)   # layer_id of adjustment layer
    filter_layer_requested = Signal(str)       # filter display name
    edit_filter_requested = Signal(str)        # layer_id of filter layer
    layers_reordered = Signal(list, int)
    layers_reparented = Signal(list, str)
    layers_unparented = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._doc: Document | None = None
        self._refreshing = False
        self._row_layer_ids: list[str] = []
        self._collapsed_groups: set[str] = set()
        self._build_ui()

    # ---- Build UI -----------------------------------------------------------

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {_BG};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header area ─────────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet(f"background-color: {_BG_HEADER};")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(6, 4, 6, 4)
        header_layout.setSpacing(4)

        # Row 1: Opacity label + spin + blend-mode combo + settings + lock
        r1 = QHBoxLayout()
        r1.setSpacing(4)

        opacity_lbl = QLabel("Opacity:")
        opacity_lbl.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 11px;")
        r1.addWidget(opacity_lbl)

        self._opacity_spin = QSpinBox()
        self._opacity_spin.setRange(0, 100)
        self._opacity_spin.setValue(100)
        self._opacity_spin.setSuffix(" %")
        self._opacity_spin.setFixedWidth(52)
        self._opacity_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._opacity_spin.setStyleSheet(f"""
            QSpinBox {{
                background: {_BG}; color: {_TEXT}; border: 1px solid {_BORDER};
                border-radius: 3px; padding: 2px 4px; font-size: 11px;
            }}
        """)
        self._opacity_spin.valueChanged.connect(self._on_opacity_changed)
        r1.addWidget(self._opacity_spin)

        self._blend_combo = _BlendModeCombo()
        self._blend_combo.setStyleSheet(f"""
            QComboBox {{
                background: {_BG}; color: {_TEXT}; border: 1px solid {_BORDER};
                border-radius: 3px; padding: 2px 4px; font-size: 11px;
                min-width: 70px;
            }}
            QComboBox::drop-down {{ border: none; width: 14px; }}
            QComboBox QAbstractItemView {{
                background: {_BG_HEADER}; color: {_TEXT};
                selection-background-color: {_SEL_PURPLE};
            }}
        """)
        for mode in BlendMode:
            self._blend_combo.addItem(mode.name.replace("_", " ").title(), mode)
        self._blend_combo.currentIndexChanged.connect(self._on_blend_changed)
        self._blend_combo.hover_preview.connect(self.blend_mode_hovered.emit)
        self._blend_combo.hover_ended.connect(self.blend_mode_hover_ended.emit)
        r1.addWidget(self._blend_combo, 1)

        self._settings_btn = QPushButton()
        self._settings_btn.setIcon(_ico_settings())
        self._settings_btn.setIconSize(QSize(16, 16))
        self._settings_btn.setFixedSize(22, 22)
        self._settings_btn.setFlat(True)
        self._settings_btn.setToolTip("Layer options")
        self._settings_btn.setStyleSheet("background: transparent; border: none;")
        r1.addWidget(self._settings_btn)

        self._lock_btn = QPushButton()
        self._lock_btn.setIcon(_icon_lock(False))
        self._lock_btn.setIconSize(QSize(16, 16))
        self._lock_btn.setFixedSize(22, 22)
        self._lock_btn.setFlat(True)
        self._lock_btn.setToolTip("Toggle lock")
        self._lock_btn.setStyleSheet("background: transparent; border: none;")
        self._lock_btn.clicked.connect(self._on_header_lock_clicked)
        r1.addWidget(self._lock_btn)

        header_layout.addLayout(r1)

        # Row 2: Opacity slider (full width)
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setValue(100)
        self._opacity_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {_BORDER}; height: 3px; border-radius: 1px;
            }}
            QSlider::handle:horizontal {{
                background: {_ICON_ACTIVE}; width: 10px; height: 10px;
                margin: -4px 0; border-radius: 5px;
            }}
            QSlider::handle:horizontal:hover {{ background: #ffffff; }}
        """)
        self._opacity_slider.valueChanged.connect(self._on_opacity_slider_changed)
        header_layout.addWidget(self._opacity_slider)

        root.addWidget(header)

        root.addWidget(_h_separator())

        # ── Layer list ───────────────────────────────────────────────────
        self._list = _LayerListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list.layers_reordered.connect(self.layers_reordered.emit)
        self._list.layers_dropped_in_group.connect(self.layers_reparented.emit)
        self._list.layers_unparented.connect(self.layers_unparented.emit)
        root.addWidget(self._list, 1)

        root.addWidget(_h_separator())

        # ── Bottom toolbar ───────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet(f"background-color: {_BG_HEADER};")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(4, 3, 4, 3)
        tb_layout.setSpacing(1)

        # Left group
        tb_layout.addWidget(_toolbar_btn(_ico_new_layer(), "New layer", self.add_requested))
        tb_layout.addWidget(_toolbar_btn(_ico_fx(), "Layer styles", self.styles_requested))
        tb_layout.addWidget(_toolbar_btn(_ico_mask(), "Add mask", self.mask_requested))

        # Adjustment layer button with popup menu
        self._adj_btn = QPushButton()
        self._adj_btn.setIcon(_ico_adjustment())
        self._adj_btn.setIconSize(QSize(16, 16))
        self._adj_btn.setFixedSize(24, 24)
        self._adj_btn.setFlat(True)
        self._adj_btn.setToolTip("Add adjustment layer")
        self._adj_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; border-radius: 3px;
            }}
            QPushButton:hover {{
                background: {_BTN_HOVER};
            }}
        """)
        self._adj_menu = QMenu(self)
        self._adj_menu.setStyleSheet(f"""
            QMenu {{
                background: {_BG_HEADER}; color: {_TEXT};
                border: 1px solid {_BORDER}; padding: 4px 0;
            }}
            QMenu::item {{
                padding: 4px 20px;
            }}
            QMenu::item:selected {{
                background: {_SEL_PURPLE};
            }}
        """)
        _ADJ_NAMES = [
            "Brightness/Contrast", "Levels", "Curves", "Exposure",
            "Vibrance", "Hue/Saturation", "Color Balance", "Black & White",
            "Photo Filter", "Gradient Map", "Selective Color", "Channel Mixer",
            "Invert", "Posterize", "Threshold",
        ]
        for adj_name in _ADJ_NAMES:
            action = self._adj_menu.addAction(adj_name)
            action.triggered.connect(
                lambda checked, n=adj_name: self.adjustment_layer_requested.emit(n),
            )
        self._adj_btn.clicked.connect(self._show_adj_menu)
        tb_layout.addWidget(self._adj_btn)

        # Filter layer button with categorized popup menu
        self._filt_btn = QPushButton()
        self._filt_btn.setIcon(_ico_filter())
        self._filt_btn.setIconSize(QSize(16, 16))
        self._filt_btn.setFixedSize(24, 24)
        self._filt_btn.setFlat(True)
        self._filt_btn.setToolTip("Add filter layer")
        self._filt_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; border-radius: 3px;
            }}
            QPushButton:hover {{
                background: {_BTN_HOVER};
            }}
        """)
        self._filt_menu = QMenu(self)
        self._filt_menu.setStyleSheet(f"""
            QMenu {{
                background: {_BG_HEADER}; color: {_TEXT};
                border: 1px solid {_BORDER}; padding: 4px 0;
            }}
            QMenu::item {{
                padding: 4px 20px;
            }}
            QMenu::item:selected {{
                background: {_SEL_PURPLE};
            }}
        """)
        _FILTER_CATEGORIES = [
            ("Blur", ["Gaussian Blur", "Motion Blur", "Radial Blur", "Surface Blur", "Lens Blur"]),
            ("Sharpen", ["Sharpen", "Unsharp Mask", "Smart Sharpen"]),
            ("Noise", ["Add Noise", "Reduce Noise", "Dust & Scratches", "Median"]),
            ("Distort", ["Ripple", "Wave", "Twirl", "Pinch", "Perspective"]),
            ("Stylize", ["Emboss", "Find Edges", "Solarize", "Oil Paint"]),
            ("Render", ["Clouds", "Difference Clouds", "Lighting Effects"]),
        ]
        for cat_name, filters in _FILTER_CATEGORIES:
            sub = self._filt_menu.addMenu(cat_name)
            sub.setStyleSheet(self._filt_menu.styleSheet())
            for fname in filters:
                action = sub.addAction(fname)
                action.triggered.connect(
                    lambda checked, n=fname: self.filter_layer_requested.emit(n),
                )
        self._filt_btn.clicked.connect(self._show_filt_menu)
        tb_layout.addWidget(self._filt_btn)

        tb_layout.addStretch()

        # Right group
        tb_layout.addWidget(_toolbar_btn(_ico_folder(), "New group", self.group_requested))
        tb_layout.addWidget(_toolbar_btn(_ico_duplicate(), "Duplicate layer", self.duplicate_requested))
        tb_layout.addWidget(_toolbar_btn(_ico_grid(), "Flatten image", self.flatten_requested))
        tb_layout.addWidget(_toolbar_btn(_ico_trash(), "Delete layer", self.delete_requested))

        root.addWidget(toolbar)

    # ---- Public API ---------------------------------------------------------

    def refresh(self, document: Document, *, thumbnails: bool = True) -> None:
        """Rebuild the layer list.

        Parameters
        ----------
        document : Document
            The document whose layers to display.
        thumbnails : bool
            If *False*, skip expensive thumbnail regeneration (useful
            during interactive operations like typing or dragging).
        """
        self._doc = document
        self._refreshing = True

        # --- Fast path: if the layer structure hasn't changed, just
        # update the active-layer highlight and header controls.
        display_order = self._build_display_order(document, self._collapsed_groups)
        new_ids = [layer.id for layer, _ in display_order]
        structure_changed = (new_ids != self._row_layer_ids)

        if not structure_changed and not thumbnails:
            # Structure identical — sync per-row state + highlight.
            self._sync_row_states(document)
            self._sync_active(document)
            self._refreshing = False
            return

        self._list.clear()
        self._row_layer_ids = []

        for layer, indent in display_order:
            is_group = layer.layer_type == LayerType.GROUP
            is_adjustment = layer.layer_type == LayerType.ADJUSTMENT
            is_filter = layer.layer_type == LayerType.FILTER
            is_text = layer.layer_type == LayerType.TEXT
            has_mask = layer.mask is not None
            is_collapsed = layer.id in self._collapsed_groups

            item = QListWidgetItem()
            item.setData(_ROLE_LAYER_ID, layer.id)
            item.setData(_ROLE_IS_GROUP, is_group)
            item.setData(_ROLE_INDENT, indent)
            item.setData(_ROLE_PARENT_ID, layer.parent_id or "")
            item.setSizeHint(QSize(0, _ROW_HEIGHT))

            thumbnail = None
            if thumbnails and not is_group and not is_adjustment and not is_filter and not is_text:
                thumbnail = _make_thumbnail(layer)

            widget = _LayerItemWidget(
                layer.id, layer.name, layer.visible, layer.locked,
                indent=indent, is_group=is_group, is_collapsed=is_collapsed,
                has_mask=has_mask, thumbnail=thumbnail,
                is_adjustment=is_adjustment, is_filter=is_filter,
                is_text=is_text,
            )
            widget.visibility_clicked.connect(self.visibility_toggled.emit)
            widget.lock_clicked.connect(self.lock_toggled.emit)
            widget.rename_finished.connect(self.rename_requested.emit)
            if is_group:
                widget.collapse_clicked.connect(self._on_collapse_toggled)

            self._list.addItem(item)
            self._list.setItemWidget(item, widget)
            self._row_layer_ids.append(layer.id)

        self._sync_active(document)
        self._refreshing = False

    def _sync_row_states(self, document: Document) -> None:
        """Update per-row visibility / lock icons without rebuilding."""
        layers_by_id = {layer.id: layer for layer in document.layers}
        for row in range(self._list.count()):
            item = self._list.item(row)
            if not item:
                continue
            lid = item.data(_ROLE_LAYER_ID)
            layer = layers_by_id.get(lid)
            if not layer:
                continue
            widget = self._list.itemWidget(item)
            if isinstance(widget, _LayerItemWidget):
                widget.update_state(layer.visible, layer.locked)

    def refresh_controls_only(self, document: Document) -> None:
        """Lightweight refresh — sync header controls without rebuilding the list."""
        self._doc = document
        self._refreshing = True
        self._sync_active(document)
        self._refreshing = False

    def _sync_active(self, document: Document) -> None:
        """Highlight the active layer and sync header controls."""
        active = document.layers.active_layer
        if active:
            for row in range(self._list.count()):
                it = self._list.item(row)
                if it and it.data(_ROLE_LAYER_ID) == active.id:
                    self._list.setCurrentRow(row)
                    break

            op_val = int(active.opacity * 100)
            self._opacity_spin.blockSignals(True)
            self._opacity_spin.setValue(op_val)
            self._opacity_spin.blockSignals(False)
            self._opacity_slider.blockSignals(True)
            self._opacity_slider.setValue(op_val)
            self._opacity_slider.blockSignals(False)
            blend_idx = self._blend_combo.findData(active.blend_mode)
            if blend_idx >= 0:
                self._blend_combo.blockSignals(True)
                self._blend_combo.setCurrentIndex(blend_idx)
                self._blend_combo.blockSignals(False)
            self._lock_btn.setIcon(_icon_lock(active.locked))

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

    def _show_adj_menu(self) -> None:
        """Show the adjustment-layer popup above the toolbar button."""
        pos = self._adj_btn.mapToGlobal(self._adj_btn.rect().topLeft())
        pos.setY(pos.y() - self._adj_menu.sizeHint().height())
        self._adj_menu.exec(pos)

    def _show_filt_menu(self) -> None:
        """Show the filter-layer popup above the toolbar button."""
        pos = self._filt_btn.mapToGlobal(self._filt_btn.rect().topLeft())
        pos.setY(pos.y() - self._filt_menu.sizeHint().height())
        self._filt_menu.exec(pos)

    def _on_collapse_toggled(self, group_id: str) -> None:
        if group_id in self._collapsed_groups:
            self._collapsed_groups.discard(group_id)
        else:
            self._collapsed_groups.add(group_id)
        if self._doc:
            self.refresh(self._doc)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Double-click: edit adjustment/filter layers; inline rename for others."""
        layer_id = item.data(_ROLE_LAYER_ID)
        # Check if this is an adjustment or filter layer
        if self._doc and layer_id:
            layer = self._doc.layers.get(layer_id)
            if layer and layer.layer_type == LayerType.ADJUSTMENT:
                self.edit_adjustment_requested.emit(layer_id)
                return
            if layer and layer.layer_type == LayerType.FILTER:
                self.edit_filter_requested.emit(layer_id)
                return
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
            op_val = int(layer.opacity * 100)
            self._opacity_spin.blockSignals(True)
            self._opacity_spin.setValue(op_val)
            self._opacity_spin.blockSignals(False)
            self._opacity_slider.blockSignals(True)
            self._opacity_slider.setValue(op_val)
            self._opacity_slider.blockSignals(False)
            blend_idx = self._blend_combo.findData(layer.blend_mode)
            if blend_idx >= 0:
                self._blend_combo.blockSignals(True)
                self._blend_combo.setCurrentIndex(blend_idx)
                self._blend_combo.blockSignals(False)
            # Update header lock icon
            self._lock_btn.setIcon(_icon_lock(layer.locked))

    def _layer_for_row(self, row: int):
        if not self._doc or row < 0 or row >= len(self._row_layer_ids):
            return None
        lid = self._row_layer_ids[row]
        return self._doc.layers.get(lid)

    def _on_opacity_changed(self, value: int) -> None:
        if self._refreshing:
            return
        self._opacity_slider.blockSignals(True)
        self._opacity_slider.setValue(value)
        self._opacity_slider.blockSignals(False)
        self.opacity_changed.emit(value / 100.0)

    def _on_opacity_slider_changed(self, value: int) -> None:
        if self._refreshing:
            return
        self._opacity_spin.blockSignals(True)
        self._opacity_spin.setValue(value)
        self._opacity_spin.blockSignals(False)
        self.opacity_changed.emit(value / 100.0)

    def _on_header_lock_clicked(self) -> None:
        """Toggle lock on the currently active layer via the header lock btn."""
        item = self._list.currentItem()
        if item:
            layer_id = item.data(_ROLE_LAYER_ID)
            if layer_id:
                self.lock_toggled.emit(layer_id)

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
