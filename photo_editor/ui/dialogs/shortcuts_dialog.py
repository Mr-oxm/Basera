"""Keyboard-shortcuts viewer / editor dialog.

Provides:
* A searchable, categorised table of every shortcut in the app
* Preset selector (Photoshop, Affinity Photo)
* Inline shortcut editing — click the key column and press a new key combo
* A *Reset to Defaults* button for the active preset
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QFont, QKeySequence, QColor, QKeyEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from ..shortcut_manager import ShortcutManager, PRESETS, ACTION_REGISTRY
from ..styles import render_qss


# ---------------------------------------------------------------------------
# Key-capture widget — placed inline in the tree when editing a shortcut
# ---------------------------------------------------------------------------

class _KeyCaptureEdit(QLineEdit):
    """A one-shot widget that captures a key-combo and emits ``key_captured``."""

    key_captured = Signal(str)  # emits the portable key-sequence string
    cancelled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("Press shortcut…")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "QLineEdit { background: #3a3a3a; color: #e8a64a; border: 2px solid #e8a64a;"
            "            border-radius: 3px; padding: 2px 6px; font-weight: bold;"
            "            font-family: 'Consolas', monospace; font-size: 12px; }"
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        # Ignore bare modifier presses
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift,
                   Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return
        if key == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return

        mods = event.modifiers()
        combo = int(mods.value) | key
        seq = QKeySequence(combo).toString()
        self.setText(seq)
        self.key_captured.emit(seq)

    def focusOutEvent(self, event):
        self.cancelled.emit()
        super().focusOutEvent(event)


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class KeyboardShortcutsDialog(QDialog):
    """Full-screen-capable dialog listing every shortcut with editing."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumSize(680, 520)
        self.resize(780, 620)
        self._mgr = ShortcutManager.instance()
        self._capture_widget: _KeyCaptureEdit | None = None
        self._capture_item: QTreeWidgetItem | None = None

        self._build_ui()
        self._populate()
        self.setStyleSheet(self._stylesheet())

    # ---- UI construction ----------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        # ---- Header row: preset selector + search --------------------------
        header = QHBoxLayout()
        header.setSpacing(10)

        preset_label = QLabel("Preset:")
        preset_label.setStyleSheet("color: #cccccc; font-weight: bold; font-size: 13px;")
        header.addWidget(preset_label)

        self._preset_combo = QComboBox()
        self._preset_combo.addItems(PRESETS.keys())
        self._preset_combo.setCurrentText(self._mgr.preset_name)
        self._preset_combo.currentTextChanged.connect(self._on_preset_changed)
        self._preset_combo.setFixedWidth(160)
        header.addWidget(self._preset_combo)

        header.addSpacing(20)

        search_label = QLabel("🔍")
        search_label.setStyleSheet("font-size: 16px;")
        header.addWidget(search_label)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search shortcuts…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_search)
        header.addWidget(self._search, 1)

        root.addLayout(header)

        # ---- Shortcut tree --------------------------------------------------
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Action", "Shortcut", ""])
        self._tree.setColumnCount(3)
        self._tree.setRootIsDecorated(True)
        self._tree.setAlternatingRowColors(True)
        self._tree.setIndentation(20)
        self._tree.setAnimated(True)
        self._tree.header().setStretchLastSection(False)
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._tree.header().resizeSection(1, 180)
        self._tree.header().resizeSection(2, 80)
        self._tree.setUniformRowHeights(True)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        root.addWidget(self._tree, 1)

        # ---- Footer buttons -------------------------------------------------
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self._reset_btn = QPushButton("Reset to Defaults")
        self._reset_btn.setFixedHeight(32)
        self._reset_btn.clicked.connect(self._on_reset)
        footer.addWidget(self._reset_btn)

        footer.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(32)
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)

        root.addLayout(footer)

    # ---- Populate tree ------------------------------------------------------

    def _populate(self) -> None:
        self._tree.clear()
        categories_order = self._mgr.categories()
        mono_font = QFont("Consolas", 11)
        mono_font.setBold(True)

        for cat in categories_order:
            cat_item = QTreeWidgetItem([cat])
            cat_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            cat_item.setFont(0, QFont("Segoe UI", 11, QFont.Weight.Bold))
            cat_item.setForeground(0, QColor("#7faad4"))
            self._tree.addTopLevelItem(cat_item)

            actions = self._mgr.actions_for_category(cat)
            for action_id, display_name, key_seq in actions:
                child = QTreeWidgetItem()
                child.setText(0, display_name)
                child.setText(1, key_seq if key_seq else "—")
                child.setData(0, Qt.ItemDataRole.UserRole, action_id)
                child.setFont(1, mono_font)
                if self._mgr.is_custom(action_id):
                    child.setForeground(1, QColor("#e8a64a"))
                elif key_seq:
                    child.setForeground(1, QColor("#8cc88c"))
                else:
                    child.setForeground(1, QColor("#666666"))

                cat_item.addChild(child)

            cat_item.setExpanded(True)

    # ---- Event handlers -----------------------------------------------------

    def _on_preset_changed(self, name: str) -> None:
        self._mgr.set_preset(name)
        self._populate()

    def _on_search(self, text: str) -> None:
        text = text.strip().lower()
        for i in range(self._tree.topLevelItemCount()):
            cat_item = self._tree.topLevelItem(i)
            any_visible = False
            for j in range(cat_item.childCount()):
                child = cat_item.child(j)
                name = child.text(0).lower()
                shortcut = child.text(1).lower()
                action_id = (child.data(0, Qt.ItemDataRole.UserRole) or "").lower()
                visible = (not text
                           or text in name
                           or text in shortcut
                           or text in action_id)
                child.setHidden(not visible)
                if visible:
                    any_visible = True
            cat_item.setHidden(not any_visible)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        action_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not action_id:
            return  # category header
        self._start_capture(item)

    def _start_capture(self, item: QTreeWidgetItem) -> None:
        # Cancel any existing capture
        self._cancel_capture()

        self._capture_item = item
        self._capture_widget = _KeyCaptureEdit()
        self._capture_widget.key_captured.connect(self._on_key_captured)
        self._capture_widget.cancelled.connect(self._cancel_capture)
        self._tree.setItemWidget(item, 1, self._capture_widget)
        self._capture_widget.setFocus()

    def _on_key_captured(self, key_seq: str) -> None:
        if self._capture_item is None:
            return
        action_id = self._capture_item.data(0, Qt.ItemDataRole.UserRole)
        if not action_id:
            self._cancel_capture()
            return

        # Check for conflicts
        conflict = self._find_conflict(action_id, key_seq)
        if conflict:
            cid, cname = conflict
            reply = QMessageBox.question(
                self,
                "Shortcut Conflict",
                f"'{key_seq}' is already assigned to '{cname}'.\n\n"
                f"Do you want to reassign it to '{self._capture_item.text(0)}'?\n"
                f"(The old binding will be cleared.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._cancel_capture()
                return
            # Clear the conflicting binding
            self._mgr.set_binding(cid, "")

        self._mgr.set_binding(action_id, key_seq)
        self._cancel_capture()
        self._populate()

    def _cancel_capture(self) -> None:
        if self._capture_widget is not None:
            if self._capture_item is not None:
                self._tree.removeItemWidget(self._capture_item, 1)
                key_seq = self._mgr.binding(
                    self._capture_item.data(0, Qt.ItemDataRole.UserRole) or "")
                self._capture_item.setText(1, key_seq if key_seq else "—")
            self._capture_widget.deleteLater()
            self._capture_widget = None
            self._capture_item = None

    def _find_conflict(self, action_id: str, key_seq: str):
        """Return (conflicting_action_id, display_name) or None."""
        if not key_seq:
            return None
        for cat, aid, name in ACTION_REGISTRY:
            if aid == action_id:
                continue
            if self._mgr.binding(aid).upper() == key_seq.upper():
                return (aid, name)
        return None

    def _on_reset(self) -> None:
        reply = QMessageBox.question(
            self,
            "Reset Shortcuts",
            f"Reset all shortcuts to the '{self._mgr.preset_name}' preset defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._mgr.reset_to_preset()
            self._populate()

    # ---- Stylesheet ---------------------------------------------------------

    @staticmethod
    def _stylesheet() -> str:
        from ..theme import ThemeManager
        return render_qss("shortcuts_dialog.qss", ThemeManager.instance().active_palette)
