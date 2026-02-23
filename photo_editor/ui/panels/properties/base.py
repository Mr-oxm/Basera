"""Shared widgets and styles for the properties panel."""

from __future__ import annotations

from PySide6.QtCore import Signal, Qt, QPoint, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFontComboBox,
    QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QSpinBox,
    QVBoxLayout, QWidget,
)


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
_LABEL = "font-size: 10px; font-weight: 600; color: #9aa0a6; letter-spacing: 0.6px; background: transparent;"
_SEPARATOR = """
    QFrame {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255,255,255,0), stop:0.5 rgba(255,255,255,0.08), stop:1 rgba(255,255,255,0));
        max-width: 1px; margin: 2px 4px; border: none;
    }
"""
_TOGGLE = """
    QPushButton {{
        font-size: {font_size}px; font-weight: 600; padding: 2px 5px;
        background: transparent; border: 1px solid transparent; border-radius: 4px;
        color: #b0b4b8; min-width: 24px; min-height: 24px;
    }}
    QPushButton:hover {{ 
        background: rgba(255,255,255,0.05); color: #e0e4e8; 
        border: 1px solid rgba(255,255,255,0.1); 
    }}
    QPushButton:checked {{ 
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(110,180,255,0.25), stop:1 rgba(110,180,255,0.1));
        border: 1px solid rgba(110,180,255,0.4); 
        color: #ffffff; 
    }}
"""
_ALIGN_BTN = """
    QPushButton {
        font-size: 11px; padding: 2px 4px;
        background: transparent; border: 1px solid transparent; border-radius: 4px;
        color: #b0b4b8; min-width: 24px; min-height: 24px;
    }
    QPushButton:hover { 
        background: rgba(255,255,255,0.05); color: #e0e4e8; 
        border: 1px solid rgba(255,255,255,0.1); 
    }
    QPushButton:checked { 
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(110,180,255,0.25), stop:1 rgba(110,180,255,0.1));
        border: 1px solid rgba(110,180,255,0.4); 
        color: #ffffff; 
    }
"""
_SPIN = """
    QSpinBox, QDoubleSpinBox {{
        font-size: 11px; padding: 2px 4px;
        background: rgba(0, 0, 0, 0.2); color: #e0e4e8;
        border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 4px; border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        max-width: {max_w}px; min-height: 22px; max-height: 22px;
    }}
    QSpinBox:hover, QDoubleSpinBox:hover {{
        background: rgba(0, 0, 0, 0.3); border: 1px solid rgba(255, 255, 255, 0.15);
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {accent}; background: rgba(0, 0, 0, 0.4);
    }}
"""
_COMBO = """
    {widget} {{
        background: rgba(0, 0, 0, 0.2); border: 1px solid rgba(255, 255, 255, 0.05); border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 4px; color: #e0e4e8; font-size: 11px; padding: 2px 6px;
        min-height: 20px; max-height: 22px;
    }}
    {widget}:hover {{ background: rgba(0, 0, 0, 0.3); border: 1px solid rgba(255, 255, 255, 0.15); }}
    {widget}:focus {{ border: 1px solid {accent}; background: rgba(0, 0, 0, 0.4); }}
    {widget}::drop-down {{
        subcontrol-origin: padding; subcontrol-position: center right;
        width: 16px; border: none; background: transparent;
    }}
    {widget}::down-arrow {{
        image: none; width: 0; height: 0;
        border-left: 4px solid transparent; border-right: 4px solid transparent;
        border-top: 5px solid #aaaaaa;
    }}
    {widget}::down-arrow:hover {{ border-top: 5px solid #eeeeee; }}
    {widget} QAbstractItemView {{
        background: #2a2c30; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 4px;
        color: #e0e4e8; selection-background-color: {accent}; outline: none; padding: 2px;
    }}
"""
_FLAT_BTN = """
    QPushButton {{
        background: transparent; border: 1px solid transparent; border-radius: 4px;
        color: #b0b4b8; font-size: 11px; padding: 2px 8px; font-weight: 500;
        min-height: 24px;
    }}
    QPushButton:hover {{ 
        background: rgba(255,255,255,0.05); color: #e0e4e8; 
        border: 1px solid rgba(255,255,255,0.1); 
    }}
    QPushButton:pressed {{ 
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(110,180,255,0.25), stop:1 rgba(110,180,255,0.1));
        border: 1px solid rgba(110,180,255,0.4); 
        color: #ffffff; 
    }}
"""


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
        self.setStyleSheet("""
            PropertyDropdown {
                background-color: #2a2c30; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 4px;
            }
        """)


class CompactPropertyWidget(QWidget):
    """Single property: Name | Value | Arrow button."""
    value_changed = Signal(str, object)

    def __init__(self, key: str, label: str, value: float,
                 min_val: float, max_val: float, step: float = 1.0, parent=None):
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
        name_label = QLabel(label)
        name_label.setMinimumWidth(40)
        name_label.setMaximumWidth(70)
        name_label.setStyleSheet(_LABEL)
        layout.addWidget(name_label)
        self.value_spin = QDoubleSpinBox()
        self.value_spin.setRange(min_val, max_val)
        self.value_spin.setSingleStep(step)
        self.value_spin.setValue(value)
        self.value_spin.setMaximumWidth(60)
        self.value_spin.setMinimumHeight(22)
        self.value_spin.setMaximumHeight(22)
        self.value_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.value_spin.setStyleSheet(_SPIN.format(max_w=60, accent=_ACCENT))
        self.value_spin.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self.value_spin)
        self.expand_btn = QPushButton("▾")
        self.expand_btn.setFixedSize(18, 18)
        self.expand_btn.setToolTip(f"Adjust {label}")
        self.expand_btn.setCheckable(True)
        self.expand_btn.clicked.connect(self._toggle_dropdown)
        self.expand_btn.setStyleSheet("""
            QPushButton {
                font-size: 10px; padding: 0px; font-weight: 600;
                background: transparent; border: none;
                border-radius: 4px; color: #b0b4b8;
            }
            QPushButton:hover { background: rgba(255,255,255,0.05); color: #e0e4e8; border: 1px solid rgba(255,255,255,0.1); }
            QPushButton:checked { color: #ffffff; background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(110,180,255,0.25), stop:1 rgba(110,180,255,0.1)); border: 1px solid rgba(110,180,255,0.4); }
        """)
        layout.addWidget(self.expand_btn)
        self.dropdown = None
        self.slider = None

    def _create_dropdown(self):
        if self.dropdown is None:
            self.dropdown = PropertyDropdown(self.window())
            self.dropdown.setStyleSheet("""
                PropertyDropdown {
                    background-color: #2a2a2a; border: 1px solid #3a3a3a; border-radius: 6px;
                }
            """)
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
