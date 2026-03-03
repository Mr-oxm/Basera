"""Brushes panel — dockable panel showing loaded brush presets with search, category dropdown, and preview thumbnails."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QImage, QPixmap, QIcon, QPainter, QColor, QPen
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..theme import ThemeManager


class BrushPreviewItem(QListWidgetItem):
    """Custom list item that stores a brush preset reference."""

    def __init__(self, preset, parent=None) -> None:
        super().__init__(parent)
        self.preset = preset
        self.setText(f"  {preset.size}   {preset.name}")
        self.setSizeHint(QSize(0, 52))
        # Generate and set icon from preview
        self._set_preview_icon()

    def _set_preview_icon(self) -> None:
        try:
            thumb = self.preset.preview_thumbnail(44, 180)
            if thumb is not None and thumb.size > 0:
                h, w = thumb.shape[:2]
                img = QImage(thumb.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
                pix = QPixmap.fromImage(img)
                self.setIcon(QIcon(pix))
        except Exception:
            pass


class BrushesPanel(QWidget):
    """Dockable panel for browsing and selecting brush presets."""

    brush_selected = Signal(object)  # emits BrushPreset

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(220)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Search bar
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(4)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_search)
        search_row.addWidget(self._search)

        layout.addLayout(search_row)

        # Category dropdown row
        cat_row = QHBoxLayout()
        cat_row.setContentsMargins(0, 0, 0, 0)
        cat_row.setSpacing(4)

        self._category_combo = QComboBox()
        self._category_combo.setMinimumHeight(28)
        self._category_combo.currentTextChanged.connect(self._on_category_changed)
        cat_row.addWidget(self._category_combo, 1)

        layout.addLayout(cat_row)

        # Brush list
        self._list = QListWidget()
        self._list.setIconSize(QSize(180, 44))
        self._list.setSpacing(1)
        self._list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._list.currentItemChanged.connect(self._on_item_selected)
        layout.addWidget(self._list, 1)

        # Theme
        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._apply_theme(ThemeManager.instance().active_palette)

        # Deferred population (don't block startup)
        self._populate_timer = QTimer(self)
        self._populate_timer.setSingleShot(True)
        self._populate_timer.setInterval(100)
        self._populate_timer.timeout.connect(self._populate)

        self._mgr = None
        self._current_collection = None

    def set_brush_manager(self, mgr) -> None:
        """Set the BrushManager reference and populate the panel."""
        self._mgr = mgr
        mgr.brush_changed.connect(self._on_external_brush_change)
        self._populate_timer.start()

    def _populate(self) -> None:
        """Fill the category combo and list with loaded brushes."""
        if self._mgr is None:
            return
        self._category_combo.blockSignals(True)
        self._category_combo.clear()
        self._category_combo.addItem("All Brushes")
        for name in self._mgr.collection_names:
            self._category_combo.addItem(name)
        self._category_combo.blockSignals(False)
        self._current_collection = None
        self._refresh_list()

    def _refresh_list(self, query: str = "") -> None:
        """Repopulate the brush list based on current category and search."""
        if self._mgr is None:
            return
        self._list.blockSignals(True)
        self._list.clear()
        collection = self._current_collection
        presets = self._mgr.search(query, collection)
        for p in presets:
            item = BrushPreviewItem(p)
            self._list.addItem(item)
        # Select active preset if it's in the list
        active = self._mgr.active_preset
        if active:
            for i in range(self._list.count()):
                item = self._list.item(i)
                if isinstance(item, BrushPreviewItem) and item.preset is active:
                    self._list.setCurrentItem(item)
                    break
        self._list.blockSignals(False)

    def _on_search(self, text: str) -> None:
        self._refresh_list(text)

    def _on_category_changed(self, text: str) -> None:
        if text == "All Brushes":
            self._current_collection = None
        else:
            self._current_collection = text
        self._refresh_list(self._search.text())

    def _on_item_selected(self, current, previous) -> None:
        if isinstance(current, BrushPreviewItem):
            self._mgr.set_active(current.preset)
            self.brush_selected.emit(current.preset)

    def _on_external_brush_change(self, preset) -> None:
        """Sync list selection when brush is changed externally."""
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            item = self._list.item(i)
            if isinstance(item, BrushPreviewItem) and item.preset is preset:
                self._list.setCurrentItem(item)
                break
        self._list.blockSignals(False)

    def _apply_theme(self, palette: dict) -> None:
        bg1 = palette.get("bg1", "#2b2b2b")
        bg2 = palette.get("bg2", "#383838")
        bg3 = palette.get("bg3", "#333333")
        fg = palette.get("fg", "#cccccc")
        fg_dim = palette.get("fg_dim", "#999999")
        border = palette.get("border", "#444444")
        border_light = palette.get("border_light", "#555555")
        accent = palette.get("accent", "#4a6fa5")
        btn = palette.get("btn", "#444444")
        input_bg = palette.get("input_bg", "#3a3a3a")
        hover = palette.get("hover", "#505050")

        self.setStyleSheet(f"""
            BrushesPanel {{
                background-color: {bg1};
            }}
            QLineEdit {{
                background-color: {input_bg};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 6px 12px;
                color: {fg};
                font-size: 13px;
                margin-top: 4px;
                margin-bottom: 2px;
            }}
            QLineEdit:focus {{
                border: 1px solid {accent};
                background-color: {bg2};
            }}
            QComboBox {{
                background-color: {bg2};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 6px 12px;
                color: {fg};
                font-size: 13px;
                margin-bottom: 4px;
            }}
            QComboBox:hover {{
                border: 1px solid {border_light};
                background-color: {hover};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0; height: 0;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {fg_dim};
            }}
            QComboBox QAbstractItemView {{
                background-color: {bg2};
                color: {fg};
                selection-background-color: {accent};
                selection-color: #ffffff;
                border: 1px solid {border_light};
                border-radius: 4px;
                outline: none;
                padding: 4px;
            }}
            QListWidget {{
                background-color: {bg1};
                border: none;
                outline: none;
                padding-top: 4px;
            }}
            QListWidget::item {{
                background-color: {bg2};
                border-radius: 6px;
                margin-bottom: 4px;
                color: {fg};
                font-size: 12px;
                padding: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {accent};
                color: #ffffff;
            }}
            QListWidget::item:hover:!selected {{
                background-color: {hover};
            }}
        """)
