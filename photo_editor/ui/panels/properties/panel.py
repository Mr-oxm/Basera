"""Main PropertiesPanel — switches between mode-specific bars."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QWidget

from .base import CompactPropertyWidget
from .crop_bar import CropPropertiesBar
from .gradient_bar import GradientPropertiesBar
from .move_bar import MovePropertiesBar
from .selection_bar import SelectionPropertiesBar
from .text_bar import TextPropertiesBar
from .vector_bar import VectorPropertiesBar
from .zoom_bar import ZoomPropertiesBar


class PropertiesPanel(QWidget):
    """Horizontal dynamic property editor for the current context."""

    from PySide6.QtCore import Signal
    value_changed = Signal(str, object)
    text_property_changed = Signal(str, object)
    gradient_property_changed = Signal(str, object)
    align_requested = Signal(str)
    zoom_action = Signal(str)
    selection_property_changed = Signal(str, object)
    selection_action = Signal(str)
    crop_property_changed = Signal(str, object)
    crop_apply = Signal()
    crop_cancel = Signal()
    vector_property_changed = Signal(str, object)
    vector_action = Signal(str)

    _PANEL_BG = "#2e2e2e"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        
        from ...theme import ThemeManager
        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._apply_theme(ThemeManager.instance().active_palette)

        self._main_layout = QHBoxLayout(self)
        self._main_layout.setContentsMargins(8, 0, 8, 0)
        self._main_layout.setSpacing(6)

        self._props_container = QWidget()
        self._props_layout = QHBoxLayout(self._props_container)
        self._props_layout.setContentsMargins(0, 0, 0, 0)
        self._props_layout.setSpacing(10)
        self._main_layout.addWidget(self._props_container)

        self._text_bar = TextPropertiesBar()
        self._text_bar.property_changed.connect(
            lambda k, v: self.text_property_changed.emit(k, v))
        self._text_bar.hide()
        self._main_layout.addWidget(self._text_bar)

        self._gradient_bar = GradientPropertiesBar()
        self._gradient_bar.property_changed.connect(
            lambda k, v: self.gradient_property_changed.emit(k, v))
        self._gradient_bar.hide()
        self._main_layout.addWidget(self._gradient_bar)

        self._move_bar = MovePropertiesBar()
        self._move_bar.align_requested.connect(
            lambda action: self.align_requested.emit(action))
        self._move_bar.hide()
        self._main_layout.addWidget(self._move_bar)

        self._zoom_bar = ZoomPropertiesBar()
        self._zoom_bar.zoom_action.connect(
            lambda action: self.zoom_action.emit(action))
        self._zoom_bar.hide()
        self._main_layout.addWidget(self._zoom_bar)

        self._sel_bar = SelectionPropertiesBar()
        self._sel_bar.property_changed.connect(
            lambda k, v: self.selection_property_changed.emit(k, v))
        self._sel_bar.action_requested.connect(
            lambda action: self.selection_action.emit(action))
        self._sel_bar.hide()
        self._main_layout.addWidget(self._sel_bar)

        self._crop_bar = CropPropertiesBar()
        self._crop_bar.property_changed.connect(
            lambda k, v: self.crop_property_changed.emit(k, v))
        self._crop_bar.apply_requested.connect(self.crop_apply.emit)
        self._crop_bar.cancel_requested.connect(self.crop_cancel.emit)
        self._crop_bar.hide()
        self._main_layout.addWidget(self._crop_bar)

        self._vector_bar = VectorPropertiesBar()
        self._vector_bar.property_changed.connect(
            lambda k, v: self.vector_property_changed.emit(k, v))
        self._vector_bar.action_requested.connect(
            lambda a: self.vector_action.emit(a))
        self._vector_bar.hide()
        self._main_layout.addWidget(self._vector_bar)

        self._main_layout.addStretch()

        self._widgets: dict[str, CompactPropertyWidget] = {}
        self._text_mode = False
        self._gradient_mode = False
        self._move_mode = False
        self._zoom_mode = False
        self._sel_mode = False
        self._crop_mode = False
        self._vector_mode = False

        self.setFixedHeight(34)

    def _hide_all_bars(self) -> None:
        self._text_bar.setVisible(False)
        self._gradient_bar.setVisible(False)
        self._move_bar.setVisible(False)
        self._zoom_bar.setVisible(False)
        self._sel_bar.setVisible(False)
        self._crop_bar.setVisible(False)
        self._vector_bar.setVisible(False)

    def _clear_modes(self) -> None:
        self._text_mode = False
        self._gradient_mode = False
        self._move_mode = False
        self._zoom_mode = False
        self._sel_mode = False
        self._crop_mode = False
        self._vector_mode = False

    def set_text_mode(self, enabled: bool, tool=None) -> None:
        self._clear_modes()
        self._text_mode = enabled
        self._props_container.setVisible(not enabled)
        self._hide_all_bars()
        self._text_bar.setVisible(enabled)
        if enabled and tool is not None:
            self._text_bar.sync_from_tool(tool)

    def set_gradient_mode(self, enabled: bool, tool=None) -> None:
        self._clear_modes()
        self._gradient_mode = enabled
        self._props_container.setVisible(not enabled)
        self._hide_all_bars()
        self._gradient_bar.setVisible(enabled)
        if enabled and tool is not None:
            self._gradient_bar.sync_from_tool(tool)

    def set_move_mode(self, enabled: bool) -> None:
        self._clear_modes()
        self._move_mode = enabled
        self._props_container.setVisible(not enabled)
        self._hide_all_bars()
        self._move_bar.setVisible(enabled)

    def set_zoom_mode(self, enabled: bool) -> None:
        self._clear_modes()
        self._zoom_mode = enabled
        self._props_container.setVisible(not enabled)
        self._hide_all_bars()
        self._zoom_bar.setVisible(enabled)

    def set_selection_mode(self, enabled: bool, tool=None, is_wand: bool = False) -> None:
        self._clear_modes()
        self._sel_mode = enabled
        self._props_container.setVisible(not enabled)
        self._hide_all_bars()
        self._sel_bar.setVisible(enabled)
        self._sel_bar.set_wand_mode(is_wand)
        if enabled and tool is not None:
            self._sel_bar.sync_from_tool(tool)

    def set_crop_mode(self, enabled: bool, tool=None) -> None:
        self._clear_modes()
        self._crop_mode = enabled
        self._props_container.setVisible(not enabled)
        self._hide_all_bars()
        self._crop_bar.setVisible(enabled)
        if enabled and tool is not None:
            self._crop_bar.sync_from_tool(tool)

    def set_vector_mode(self, enabled: bool, tool=None, mode: str = "pen") -> None:
        self._clear_modes()
        self._vector_mode = enabled
        self._props_container.setVisible(not enabled)
        self._hide_all_bars()
        self._vector_bar.setVisible(enabled)
        if enabled and tool is not None:
            self._vector_bar.sync_from_tool(tool, mode)

    @property
    def text_bar(self) -> TextPropertiesBar:
        return self._text_bar

    @property
    def gradient_bar(self) -> GradientPropertiesBar:
        return self._gradient_bar

    @property
    def move_bar(self) -> MovePropertiesBar:
        return self._move_bar

    @property
    def crop_bar(self) -> CropPropertiesBar:
        return self._crop_bar

    @property
    def zoom_bar(self) -> ZoomPropertiesBar:
        return self._zoom_bar

    @property
    def selection_bar(self) -> SelectionPropertiesBar:
        return self._sel_bar

    @property
    def vector_bar(self) -> VectorPropertiesBar:
        return self._vector_bar

    def clear(self) -> None:
        while self._props_layout.count() > 0:
            item = self._props_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._widgets.clear()

    def set_title(self, title: str) -> None:
        pass

    def add_slider(
        self, key: str, label: str, value: int = 0,
        min_val: int = 0, max_val: int = 100,
    ) -> None:
        widget = CompactPropertyWidget(
            key, label, float(value), float(min_val), float(max_val),
            step=1.0, parent=self._props_container
        )
        widget.value_changed.connect(lambda k, v: self.value_changed.emit(k, int(v)))
        self._props_layout.addWidget(widget)
        self._widgets[key] = widget

    def add_spinbox(
        self, key: str, label: str, value: float = 0.0,
        min_val: float = -999.0, max_val: float = 999.0, step: float = 0.1,
    ) -> None:
        widget = CompactPropertyWidget(
            key, label, value, min_val, max_val,
            step=step, parent=self._props_container
        )
        widget.value_changed.connect(lambda k, v: self.value_changed.emit(k, v))
        self._props_layout.addWidget(widget)
        self._widgets[key] = widget

    def set_value(self, key: str, value: object) -> None:
        w = self._widgets.get(key)
        if w:
            w.set_value(float(value))

    def _apply_theme(self, palette: dict) -> None:
        self.setStyleSheet(f"""
            PropertiesPanel, PropertiesPanel > QWidget {{
                background-color: {palette['bg3']};
            }}
            QLabel {{ background: transparent; }}
        """)
