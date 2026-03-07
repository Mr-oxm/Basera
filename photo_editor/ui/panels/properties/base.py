"""Shared widgets and styles for the properties panel."""

from __future__ import annotations

from PySide6.QtCore import Signal, Qt, QPoint, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFontComboBox,
    QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QSpinBox,
    QVBoxLayout, QWidget,
)

from ...styles import load_qss_template, render_qss


def _qt_message_handler(msg_type: QtMsgType, context, message: str) -> None:
    """Suppress OpenType font warnings while preserving other Qt messages."""
    if "OpenType support missing" in message:
        return
    import sys
    if msg_type == QtMsgType.QtDebugMsg:
        print(f"Qt Debug: {message}", file=sys.stderr)
    elif msg_type == QtMsgType.QtWarningMsg:
        print(f"Qt Warning: {message}", file=sys.stderr)
    elif msg_type == QtMsgType.QtCriticalMsg:
        print(f"Qt Critical: {message}", file=sys.stderr)
    elif msg_type == QtMsgType.QtFatalMsg:
        print(f"Qt Fatal: {message}", file=sys.stderr)


qInstallMessageHandler(_qt_message_handler)


# ---- Style constants ----
_ACCENT = "#6eb4ff"
_ACCENT_HOVER = "#8ec5ff"
_LABEL = load_qss_template("properties_label.qss")
_SEPARATOR = load_qss_template("properties_separator.qss")
_TOGGLE = load_qss_template("properties_toggle.qss")
_ALIGN_BTN = load_qss_template("properties_align_button.qss")
_SPIN = load_qss_template("properties_spin.qss")
_COMBO = load_qss_template("properties_combo.qss")
_FLAT_BTN = load_qss_template("properties_flat_button.qss")


class FontComboBoxWithPreview(QFontComboBox):
    """QFontComboBox with real-time hover preview support."""
    font_hovered = Signal(str)
    hover_ended = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover_connected = False
        self._original_font = None

    def showPopup(self):
        super().showPopup()
        view = self.view()
        if view and not self._hover_connected:
            view.setMouseTracking(True)
            view.entered.connect(self._on_item_hovered)
            self._hover_connected = True
        self._original_font = self.currentFont().family()

    def hidePopup(self):
        self.hover_ended.emit()
        super().hidePopup()

    def _on_item_hovered(self, index):
        if index.isValid():
            font_family = self.itemText(index.row())
            if font_family:
                self.font_hovered.emit(font_family)


class SizeComboBoxWithPreview(QComboBox):
    """Editable QComboBox with real-time hover preview for font sizes."""
    size_hovered = Signal(int)
    hover_ended = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover_connected = False

    def showPopup(self):
        super().showPopup()
        view = self.view()
        if view and not self._hover_connected:
            view.setMouseTracking(True)
            view.entered.connect(self._on_item_hovered)
            self._hover_connected = True

    def hidePopup(self):
        self.hover_ended.emit()
        super().hidePopup()

    def _on_item_hovered(self, index):
        if index.isValid():
            text = self.itemText(index.row())
            try:
                self.size_hovered.emit(int(text))
            except ValueError:
                pass


class PropertyDropdown(QWidget):
    """Floating dropdown widget that appears as overlay."""
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimumWidth(200)
        layout.addWidget(self.slider)

        from ...theme import ThemeManager
        try:
            ThemeManager.instance().theme_changed.connect(self._apply_theme)
            self._apply_theme(ThemeManager.instance().active_palette)
        except Exception:
            self.setStyleSheet(
                render_qss("properties_dropdown.qss", bg2="#2a2c30", border="rgba(255, 255, 255, 0.1)")
            )

    def _apply_theme(self, palette: dict) -> None:
        """Update popup background style based on active theme palette."""
        self.setStyleSheet(render_qss("properties_dropdown.qss", palette))


class CompactPropertyWidget(QWidget):
    """Single property: Name | Value | Arrow button."""
    value_changed = Signal(str, object)

    def __init__(self, key: str, label: str, value: float,
                 min_val: float, max_val: float, step: float = 1.0, 
                 decimals: int = 0, suffix: str = "", parent=None):
        super().__init__(parent)
        self.key = key
        self.label_text = label
        self.min_val = min_val
        self.max_val = max_val
        self.step = step
        self.current_value = value
        self._expanded = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        if label:
            name_label = QLabel(label)
            name_label.setMinimumWidth(40)
            name_label.setMaximumWidth(60)
            name_label.setStyleSheet(_LABEL)
            layout.addWidget(name_label)
        self.value_spin = QDoubleSpinBox()
        self.value_spin.setRange(min_val, max_val)
        self.value_spin.setSingleStep(step)
        if decimals is not None:
            self.value_spin.setDecimals(decimals)
        self.value_spin.setValue(value)
        if suffix:
            self.value_spin.setSuffix(suffix)
        self.value_spin.setMaximumWidth(70)
        self.value_spin.setMinimumHeight(22)
        self.value_spin.setMaximumHeight(22)
        self.value_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.value_spin.setStyleSheet(_SPIN.format(max_w=70, accent=_ACCENT))
        self.value_spin.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self.value_spin)
        self.expand_btn = QPushButton("▾")
        self.expand_btn.setFixedSize(18, 18)
        self.expand_btn.setToolTip(f"Adjust {label}")
        self.expand_btn.setCheckable(True)
        self.expand_btn.clicked.connect(self._toggle_dropdown)
        self.expand_btn.setStyleSheet(load_qss_template("properties_expand_button.qss"))
        layout.addWidget(self.expand_btn)
        self.dropdown = None
        self.slider = None

    def _create_dropdown(self):
        if self.dropdown is None:
            self.dropdown = PropertyDropdown(self.window())
            self.slider = self.dropdown.slider
            if self.step == 1.0:
                self.slider.setRange(int(self.min_val), int(self.max_val))
                self.slider.setValue(int(self.current_value))
                self.slider.valueChanged.connect(lambda v: self.value_spin.setValue(v))
            else:
                self.slider.setRange(0, 1000)
                ratio = (self.current_value - self.min_val) / (self.max_val - self.min_val) if self.max_val > self.min_val else 0
                self.slider.setValue(int(ratio * 1000))
                self.slider.valueChanged.connect(
                    lambda v: self.value_spin.setValue(self.min_val + (v / 1000.0) * (self.max_val - self.min_val))
                )
            self.value_spin.valueChanged.connect(
                lambda v: self.slider.setValue(
                    int(v) if self.step == 1.0 else int((v - self.min_val) / (self.max_val - self.min_val) * 1000)
                )
            )

    def _on_value_changed(self, value: float):
        self.current_value = value
        self.value_changed.emit(self.key, value)

    def _toggle_dropdown(self):
        self._expanded = not self._expanded
        if self._expanded:
            self._create_dropdown()
            global_pos = self.mapToGlobal(QPoint(0, self.height()))
            self.dropdown.move(global_pos)
            self.dropdown.show()
            self.expand_btn.setText("▴")
        else:
            if self.dropdown:
                self.dropdown.hide()
            self.expand_btn.setText("▾")

    def set_value(self, value: float):
        self.value_spin.blockSignals(True)
        self.value_spin.setValue(value)
        self.current_value = value
        self.value_spin.blockSignals(False)
        if self.slider:
            self.slider.blockSignals(True)
            if self.step == 1.0:
                self.slider.setValue(int(value))
            else:
                ratio = (value - self.min_val) / (self.max_val - self.min_val) if self.max_val > self.min_val else 0
                self.slider.setValue(int(ratio * 1000))
            self.slider.blockSignals(False)


def _icon_from_painter(paint_func, size: int = 20):
    from PySide6.QtGui import QPixmap, QPainter, QPen, QColor as QC
    from PySide6.QtGui import QIcon
    pix = QPixmap(size, size)
    pix.fill(QC(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    paint_func(p, size)
    p.end()
    return QIcon(pix)


def make_separator(height: int = 18) -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFixedHeight(height)
    sep.setStyleSheet(_SEPARATOR)
    return sep


# Export for use by bar modules
__all__ = [
    "ACCENT", "LABEL", "SEPARATOR", "TOGGLE", "ALIGN_BTN", "SPIN", "COMBO", "FLAT_BTN",
    "FontComboBoxWithPreview", "SizeComboBoxWithPreview", "PropertyDropdown",
    "CompactPropertyWidget", "make_separator", "_icon_from_painter",
]
ACCENT = _ACCENT
LABEL = _LABEL
SEPARATOR = _SEPARATOR
TOGGLE = _TOGGLE
ALIGN_BTN = _ALIGN_BTN
SPIN = _SPIN
COMBO = _COMBO
FLAT_BTN = _FLAT_BTN
