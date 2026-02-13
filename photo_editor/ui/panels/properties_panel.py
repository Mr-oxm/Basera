"""Properties panel — shows editable parameters for the active layer / tool.

When the Text tool is active, the panel switches to a specialised
layout with font picker, bold/italic/underline toggles, alignment,
colour, and spacing controls.

When the Gradient tool is active, the panel switches to a gradient
properties bar with colour / gradient picker, type selector, opacity,
and reverse.
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Qt, QPoint, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QFont, QColor, QIcon
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFontComboBox,
    QHBoxLayout, QLabel, QPushButton, QSlider, QSpinBox,
    QVBoxLayout, QWidget, QFrame,
)

from ..widgets.color_dropdown import ColorDropdown
from ..widgets.gradient_editor import GradientEditor


# ============================================================================
# Qt Message Handler - Suppress OpenType font warnings
# ============================================================================

def _qt_message_handler(msg_type: QtMsgType, context, message: str) -> None:
    """Custom Qt message handler to suppress font database warnings.
    
    Filters out "OpenType support missing" warnings while preserving
    all other Qt messages for debugging.
    """
    # Suppress OpenType support warnings for fonts
    if "OpenType support missing" in message:
        return  # Ignore these warnings
    
    # Print all other messages normally
    import sys
    if msg_type == QtMsgType.QtDebugMsg:
        print(f"Qt Debug: {message}", file=sys.stderr)
    elif msg_type == QtMsgType.QtWarningMsg:
        print(f"Qt Warning: {message}", file=sys.stderr)
    elif msg_type == QtMsgType.QtCriticalMsg:
        print(f"Qt Critical: {message}", file=sys.stderr)
    elif msg_type == QtMsgType.QtFatalMsg:
        print(f"Qt Fatal: {message}", file=sys.stderr)


# Install the message handler once at module import
qInstallMessageHandler(_qt_message_handler)


# ============================================================================
# Font ComboBox with Hover Preview
# ============================================================================

class FontComboBoxWithPreview(QFontComboBox):
    """QFontComboBox with real-time hover preview support."""
    
    font_hovered = Signal(str)  # Emitted when hovering over a font (font family name)
    hover_ended = Signal()  # Emitted when hover ends or popup closes
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover_connected = False
        self._original_font = None
    
    def showPopup(self):
        """Override to install hover tracking when popup opens."""
        super().showPopup()
        
        # Get the list view inside the combo box
        view = self.view()
        if view and not self._hover_connected:
            view.setMouseTracking(True)
            view.entered.connect(self._on_item_hovered)
            self._hover_connected = True
        
        # Remember the current font for restoration
        self._original_font = self.currentFont().family()
    
    def hidePopup(self):
        """Override to emit hover_ended signal when closing."""
        self.hover_ended.emit()
        super().hidePopup()
    
    def _on_item_hovered(self, index):
        """Called when mouse hovers over an item in the dropdown."""
        if index.isValid():
            # Get the font at this index
            font_family = self.itemText(index.row())
            if font_family:
                self.font_hovered.emit(font_family)



# ============================================================================
# Size ComboBox with Hover Preview
# ============================================================================

class SizeComboBoxWithPreview(QComboBox):
    """Editable QComboBox with real-time hover preview for font sizes."""

    size_hovered = Signal(int)   # Emitted when hovering over a size
    hover_ended = Signal()       # Emitted when hover ends or popup closes

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


# ============================================================================
# Property Dropdown (floating slider)
# ============================================================================

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
                background-color: #2a2a2a; 
                border: 1px solid #555; 
                border-radius: 3px;
            }
        """)


# ============================================================================
# Compact property widget (for generic tool sliders)
# ============================================================================

class CompactPropertyWidget(QWidget):
    """Single property displayed horizontally: Name | Value | Arrow button."""
    
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
        name_label.setStyleSheet("font-size: 10px; color: #888; letter-spacing: 0.5px;")
        layout.addWidget(name_label)
        
        self.value_spin = QDoubleSpinBox()
        self.value_spin.setRange(min_val, max_val)
        self.value_spin.setSingleStep(step)
        self.value_spin.setValue(value)
        self.value_spin.setMaximumWidth(60)
        self.value_spin.setMinimumHeight(22)
        self.value_spin.setMaximumHeight(22)
        self.value_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.value_spin.setStyleSheet("""
            QDoubleSpinBox {
                font-size: 11px; padding: 2px 4px;
                background: #383838; color: #ccc;
                border: 1px solid transparent; border-radius: 3px;
            }
            QDoubleSpinBox:focus {
                border: 1px solid #4a6fa5;
            }
        """)
        self.value_spin.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self.value_spin)
        
        self.expand_btn = QPushButton("▾")
        self.expand_btn.setFixedSize(18, 18)
        self.expand_btn.setToolTip(f"Adjust {label}")
        self.expand_btn.setCheckable(True)
        self.expand_btn.clicked.connect(self._toggle_dropdown)
        self.expand_btn.setStyleSheet("""
            QPushButton {
                font-size: 10px; padding: 0px;
                background: transparent; border: none;
                border-radius: 3px; color: #777;
            }
            QPushButton:hover { background: rgba(255,255,255,0.07); color: #bbb; }
            QPushButton:checked { color: #4a6fa5; }
        """)
        layout.addWidget(self.expand_btn)
        
        self.dropdown = None
        self.slider = None

    def _create_dropdown(self):
        if self.dropdown is None:
            self.dropdown = PropertyDropdown(self.window())
            self.dropdown.setStyleSheet("""
                PropertyDropdown {
                    background-color: #2a2a2a;
                    border: 1px solid #3a3a3a;
                    border-radius: 6px;
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


# ============================================================================
# Move properties bar — alignment
# ============================================================================

_MOVE_BTN_STYLE = """
    QPushButton {
        background: transparent;
        border: none;
        border-radius: 4px;
        padding: 3px;
        min-width: 26px; min-height: 26px;
        max-width: 26px; max-height: 26px;
    }
    QPushButton:hover { background-color: rgba(255, 255, 255, 0.08); }
    QPushButton:pressed { background-color: rgba(74, 111, 165, 0.5); }
"""

_MOVE_SEP_STYLE = "color: #444; background: #444; max-width: 1px; margin: 4px 2px;"


def _icon_from_painter(paint_func, size: int = 20):
    """Create a QIcon by painting with a callable ``paint_func(painter, rect)``."""
    from PySide6.QtGui import QPixmap, QPainter, QPen, QColor as QC
    pix = QPixmap(size, size)
    pix.fill(QC(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    paint_func(p, size)
    p.end()
    return QIcon(pix)


def _make_align_icons():
    """Return a dict of action-name → QIcon for the alignment buttons."""
    from PySide6.QtGui import QPen, QColor as QC
    from PySide6.QtCore import QRectF

    icons = {}
    line_c = QC("#888888")
    bar_c = QC("#cccccc")

    def _pen(color, w=1.5):
        pen = QPen(color, w)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        return pen

    def align_left(p, s):
        p.setPen(_pen(bar_c, 1.5))
        p.drawLine(4, 3, 4, s - 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(line_c)
        p.drawRoundedRect(QRectF(6, 5, 10, 3), 1, 1)
        p.drawRoundedRect(QRectF(6, 12, 7, 3), 1, 1)

    def align_center_h(p, s):
        cx = s / 2
        p.setPen(_pen(bar_c, 1.5))
        p.drawLine(int(cx), 3, int(cx), s - 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(line_c)
        p.drawRoundedRect(QRectF(cx - 5, 5, 10, 3), 1, 1)
        p.drawRoundedRect(QRectF(cx - 3.5, 12, 7, 3), 1, 1)

    def align_right(p, s):
        p.setPen(_pen(bar_c, 1.5))
        p.drawLine(s - 4, 3, s - 4, s - 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(line_c)
        p.drawRoundedRect(QRectF(s - 14, 5, 10, 3), 1, 1)
        p.drawRoundedRect(QRectF(s - 11, 12, 7, 3), 1, 1)

    def align_top(p, s):
        p.setPen(_pen(bar_c, 1.5))
        p.drawLine(3, 4, s - 3, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(line_c)
        p.drawRoundedRect(QRectF(5, 6, 3, 10), 1, 1)
        p.drawRoundedRect(QRectF(12, 6, 3, 7), 1, 1)

    def align_middle_v(p, s):
        cy = s / 2
        p.setPen(_pen(bar_c, 1.5))
        p.drawLine(3, int(cy), s - 3, int(cy))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(line_c)
        p.drawRoundedRect(QRectF(5, cy - 5, 3, 10), 1, 1)
        p.drawRoundedRect(QRectF(12, cy - 3.5, 3, 7), 1, 1)

    def align_bottom(p, s):
        p.setPen(_pen(bar_c, 1.5))
        p.drawLine(3, s - 4, s - 3, s - 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(line_c)
        p.drawRoundedRect(QRectF(5, s - 14, 3, 10), 1, 1)
        p.drawRoundedRect(QRectF(12, s - 11, 3, 7), 1, 1)

    for name, fn in [
        ("align_left", align_left), ("align_center_h", align_center_h),
        ("align_right", align_right), ("align_top", align_top),
        ("align_middle_v", align_middle_v), ("align_bottom", align_bottom),
    ]:
        icons[name] = _icon_from_painter(fn)
    return icons


class MovePropertiesBar(QWidget):
    """Horizontal bar with layer alignment buttons — clean, icon-only design."""

    align_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(1)

        icons = _make_align_icons()

        self._btns: list[QPushButton] = []
        for action in ("align_left", "align_center_h", "align_right"):
            self._btns.append(self._make_btn(icons[action], action))
            layout.addWidget(self._btns[-1])

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(18)
        sep.setStyleSheet(_MOVE_SEP_STYLE)
        layout.addWidget(sep)

        for action in ("align_top", "align_middle_v", "align_bottom"):
            self._btns.append(self._make_btn(icons[action], action))
            layout.addWidget(self._btns[-1])

        layout.addStretch()

    def _make_btn(self, icon: QIcon, action: str) -> QPushButton:
        btn = QPushButton()
        btn.setIcon(icon)
        btn.setIconSize(btn.minimumSize())
        from PySide6.QtCore import QSize
        btn.setIconSize(QSize(20, 20))
        # Tooltip: turn action name into nice label
        tip = action.replace("_", " ").replace("align ", "Align ").replace("h", "Horizontally").replace("v", "Vertically")
        if "center" in action:
            tip = "Align Center Horizontally"
        elif "middle" in action:
            tip = "Align Center Vertically"
        else:
            tip = action.replace("_", " ").title()
        btn.setToolTip(tip)
        btn.setStyleSheet(_MOVE_BTN_STYLE)
        btn.clicked.connect(lambda checked=False, a=action: self.align_requested.emit(a))
        return btn


# ============================================================================
# Shared modern style constants
# ============================================================================

# Accent colour used for checked/active states throughout all bars.
_ACCENT = "#4a6fa5"
_ACCENT_HOVER = "#5a8abf"

_LABEL = "font-size: 10px; color: #777; letter-spacing: 0.5px; background: transparent;"

_SEPARATOR = "color: #3a3a3a; background: #3a3a3a; max-width: 1px; margin: 4px 1px;"

_TOGGLE = """
    QPushButton {{
        font-size: {font_size}px; padding: 2px 5px;
        background: transparent; border: none; border-radius: 4px;
        color: #999; min-width: 24px; min-height: 24px;
    }}
    QPushButton:hover {{ background: rgba(255,255,255,0.07); color: #ccc; }}
    QPushButton:checked {{ background: rgba(74,111,165,0.35); color: #ddeeff; }}
"""

_ALIGN_BTN = """
    QPushButton {
        font-size: 10px; padding: 2px 4px;
        background: transparent; border: none; border-radius: 4px;
        color: #999; min-width: 24px; min-height: 24px;
    }
    QPushButton:hover { background: rgba(255,255,255,0.07); color: #ccc; }
    QPushButton:checked { background: rgba(74,111,165,0.35); color: #ddeeff; }
"""

_SPIN = """
    QSpinBox, QDoubleSpinBox {{
        font-size: 11px; padding: 2px 4px;
        background: #383838; color: #ccc;
        border: 1px solid transparent; border-radius: 3px;
        max-width: {max_w}px; min-height: 22px; max-height: 22px;
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {accent};
    }}
"""

_COMBO = """
    {widget} {{
        background: #383838; border: 1px solid transparent; border-radius: 3px;
        color: #ccc; font-size: 11px; padding: 2px 6px;
        min-height: 20px; max-height: 22px;
    }}
    {widget}:hover {{ border: 1px solid #4a4a4a; }}
    {widget}:focus {{ border: 1px solid {accent}; }}
    {widget}::drop-down {{
        subcontrol-origin: padding; subcontrol-position: center right;
        width: 16px; border: none; background: transparent;
    }}
    {widget}::down-arrow {{
        image: none; width: 0; height: 0;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid #888;
    }}
    {widget} QAbstractItemView {{
        background: #2e2e2e; border: 1px solid #3a3a3a; border-radius: 4px;
        color: #ccc; selection-background-color: {accent};
    }}
"""

_FLAT_BTN = """
    QPushButton {{
        background: transparent; border: none; border-radius: 4px;
        color: #999; font-size: 11px; padding: 2px 8px;
        min-height: 24px;
    }}
    QPushButton:hover {{ background: rgba(255,255,255,0.07); color: #ccc; }}
    QPushButton:pressed {{ background: rgba(74,111,165,0.35); }}
"""


def _make_separator(height: int = 18) -> QFrame:
    """Return a thin vertical separator matching the modern theme."""
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFixedHeight(height)
    sep.setStyleSheet(_SEPARATOR)
    return sep


class TextPropertiesBar(QWidget):
    """Horizontal bar with all text formatting controls."""

    # Emitted as (key, value) for any property change
    property_changed = Signal(str, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        _spin_css = _SPIN.format(max_w=70, accent=_ACCENT)

        # ---- Font family ----
        lbl = QLabel("Font")
        lbl.setStyleSheet(_LABEL)
        layout.addWidget(lbl)

        self._font_combo = FontComboBoxWithPreview()
        self._font_combo.setMinimumWidth(160)
        self._font_combo.setMaximumWidth(200)
        self._font_combo.setMaximumHeight(24)
        self._font_combo.setStyleSheet(_COMBO.format(widget="QFontComboBox", accent=_ACCENT))
        self._font_combo.currentFontChanged.connect(self._on_font_selected)
        self._font_combo.font_hovered.connect(self._on_font_hover_preview)
        self._font_combo.hover_ended.connect(self._on_font_hover_end)
        layout.addWidget(self._font_combo)

        # ---- Font size ----
        self._size_combo = SizeComboBoxWithPreview()
        self._size_combo.setEditable(True)
        _COMMON_SIZES = [
            "6", "7", "8", "9", "10", "11", "12", "14", "16", "18",
            "20", "22", "24", "26", "28", "30", "32", "36", "40",
            "44", "48", "54", "60", "72", "80", "96", "100",
            "120", "144", "200", "300", "400", "500",
        ]
        self._size_combo.addItems(_COMMON_SIZES)
        self._size_combo.setCurrentText("36")
        self._size_combo.setMinimumWidth(80)
        self._size_combo.setMaximumWidth(90)
        self._size_combo.setMaximumHeight(24)
        from PySide6.QtGui import QIntValidator
        self._size_combo.setValidator(QIntValidator(1, 2000))
        self._size_combo.setStyleSheet(_COMBO.format(widget="QComboBox", accent=_ACCENT))
        self._size_combo.currentTextChanged.connect(self._on_size_changed)
        self._size_combo.size_hovered.connect(self._on_size_hover_preview)
        self._size_combo.hover_ended.connect(self._on_size_hover_end)
        layout.addWidget(self._size_combo)

        layout.addWidget(_make_separator())

        # ---- Bold / Italic / Underline / Strikethrough ----
        self._bold_btn = self._toggle_btn("B", "bold", bold=True)
        layout.addWidget(self._bold_btn)
        self._italic_btn = self._toggle_btn("I", "italic", italic=True)
        layout.addWidget(self._italic_btn)
        self._underline_btn = self._toggle_btn("U", "underline", underline=True)
        layout.addWidget(self._underline_btn)
        self._strike_btn = self._toggle_btn("S", "strikethrough", strike=True)
        layout.addWidget(self._strike_btn)

        layout.addWidget(_make_separator())

        # ---- Alignment ----
        self._align_left = self._align_btn("\u2261L", "left")
        self._align_center = self._align_btn("\u2261C", "center")
        self._align_right = self._align_btn("\u2261R", "right")
        self._align_left.setChecked(True)
        layout.addWidget(self._align_left)
        layout.addWidget(self._align_center)
        layout.addWidget(self._align_right)

        layout.addWidget(_make_separator())

        # ---- Color dropdown ----
        self._color_dropdown = ColorDropdown(
            label="Color:", show_gradient=True, show_wheel=True,
        )
        self._color_dropdown.color_committed.connect(self._on_color_committed)
        self._color_dropdown.color_changed.connect(self._on_color_preview)
        self._color_dropdown.gradient_changed.connect(self._on_gradient_pick)
        layout.addWidget(self._color_dropdown)

        layout.addWidget(_make_separator())

        # ---- Letter spacing ----
        lbl3 = QLabel("Tracking")
        lbl3.setStyleSheet(_LABEL)
        layout.addWidget(lbl3)
        self._tracking_spin = QDoubleSpinBox()
        self._tracking_spin.setRange(-20.0, 100.0)
        self._tracking_spin.setValue(0.0)
        self._tracking_spin.setSingleStep(0.5)
        self._tracking_spin.setStyleSheet(_spin_css)
        self._tracking_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._tracking_spin.valueChanged.connect(
            lambda v: self.property_changed.emit("letter_spacing", v))
        layout.addWidget(self._tracking_spin)

        # ---- Line height ----
        lbl4 = QLabel("Leading")
        lbl4.setStyleSheet(_LABEL)
        layout.addWidget(lbl4)
        self._leading_spin = QDoubleSpinBox()
        self._leading_spin.setRange(0.5, 5.0)
        self._leading_spin.setValue(1.2)
        self._leading_spin.setSingleStep(0.1)
        self._leading_spin.setStyleSheet(_spin_css)
        self._leading_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._leading_spin.valueChanged.connect(
            lambda v: self.property_changed.emit("line_height", v))
        layout.addWidget(self._leading_spin)

        # ---- Paragraph spacing ----
        lbl5 = QLabel("Para")
        lbl5.setStyleSheet(_LABEL)
        layout.addWidget(lbl5)
        self._para_spin = QDoubleSpinBox()
        self._para_spin.setRange(0.0, 200.0)
        self._para_spin.setValue(0.0)
        self._para_spin.setSingleStep(1.0)
        self._para_spin.setStyleSheet(_spin_css)
        self._para_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._para_spin.valueChanged.connect(
            lambda v: self.property_changed.emit("paragraph_spacing", v))
        layout.addWidget(self._para_spin)

        layout.addStretch()

    # ---- Helpers ----

    def _toggle_btn(self, label: str, key: str,
                    bold: bool = False, italic: bool = False,
                    underline: bool = False, strike: bool = False) -> QPushButton:
        btn = QPushButton(label)
        btn.setCheckable(True)
        font = btn.font()
        if bold:
            font.setBold(True)
        if italic:
            font.setItalic(True)
        if underline:
            font.setUnderline(True)
        if strike:
            font.setStrikeOut(True)
        btn.setFont(font)
        btn.setStyleSheet(_TOGGLE.format(font_size=10))
        btn.toggled.connect(lambda checked: self.property_changed.emit(key, checked))
        return btn

    def _align_btn(self, label: str, alignment: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setStyleSheet(_ALIGN_BTN)
        btn.clicked.connect(lambda: self._on_align(alignment))
        return btn

    def _on_align(self, alignment: str) -> None:
        for btn, align in [(self._align_left, "left"),
                           (self._align_center, "center"),
                           (self._align_right, "right")]:
            btn.blockSignals(True)
            btn.setChecked(align == alignment)
            btn.blockSignals(False)
        self.property_changed.emit("alignment", alignment)

    def _on_font_selected(self, font: QFont) -> None:
        """Handle font selection (when user clicks to select)"""
        family = font.family()
        self.property_changed.emit("font_family", family)
    
    def _on_font_hover_preview(self, font_family: str) -> None:
        """Handle font hover for preview (temporary change)"""
        self.property_changed.emit("_preview_font_family", font_family)
    
    def _on_font_hover_end(self) -> None:
        """Handle end of font hover (restore original)"""
        self.property_changed.emit("_preview_font_end", None)

    def _on_size_changed(self, text: str) -> None:
        """Handle font size change from the editable combo box."""
        try:
            val = int(text)
            if 1 <= val <= 2000:
                self.property_changed.emit("font_size", val)
        except ValueError:
            pass

    def _on_size_hover_preview(self, size: int) -> None:
        """Handle size hover for live preview."""
        self.property_changed.emit("_preview_font_size", size)

    def _on_size_hover_end(self) -> None:
        """Restore original size when hover ends."""
        self.property_changed.emit("_preview_font_size_end", None)

    def _on_color_committed(self, c) -> None:
        from ...core.color import SolidFill
        self.property_changed.emit("fill_color", SolidFill(color=c))

    def _on_color_preview(self, c) -> None:
        from ...core.color import SolidFill
        self.property_changed.emit("_preview_fill_color", SolidFill(color=c))

    def _on_gradient_pick(self, fill) -> None:
        self.property_changed.emit("fill_color", fill)

    # ---- Sync from tool state ----

    def sync_from_tool(self, tool) -> None:
        """Update controls to reflect the tool's current state."""
        self.blockSignals(True)
        try:
            if hasattr(tool, "font_family"):
                self._font_combo.setCurrentFont(QFont(tool.font_family))
            if hasattr(tool, "font_size"):
                self._size_combo.setCurrentText(str(int(tool.font_size)))
            if hasattr(tool, "bold"):
                self._bold_btn.setChecked(tool.bold)
            if hasattr(tool, "italic"):
                self._italic_btn.setChecked(tool.italic)
            if hasattr(tool, "underline"):
                self._underline_btn.setChecked(tool.underline)
            if hasattr(tool, "strikethrough"):
                self._strike_btn.setChecked(tool.strikethrough)
            if hasattr(tool, "alignment"):
                self._on_align(tool.alignment)
            if hasattr(tool, "letter_spacing"):
                self._tracking_spin.setValue(tool.letter_spacing)
            if hasattr(tool, "line_height"):
                self._leading_spin.setValue(tool.line_height)
            if hasattr(tool, "paragraph_spacing"):
                self._para_spin.setValue(tool.paragraph_spacing)
            if hasattr(tool, "color"):
                c = tool.color
                from ...core.color import Color
                col = Color(c[0], c[1], c[2], c[3] if len(c) > 3 else 1.0)
                self._color_dropdown.set_color(col)
        finally:
            self.blockSignals(False)


# ============================================================================
# Gradient properties bar
# ============================================================================

class GradientPropertiesBar(QWidget):
    """Horizontal bar with gradient-specific controls.

    Signals
    -------
    property_changed(str, object)
        Emitted as *(key, value)* for gradient type, opacity, reverse,
        or gradient stop changes.
    """

    property_changed = Signal(str, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        # ---- Colour / gradient dropdown ----
        self._color_dropdown = ColorDropdown(
            label="Gradient:",
            show_gradient=True,
            show_wheel=True,
            default_tab=2,
        )
        self._color_dropdown.gradient_changed.connect(self._on_gradient_pick)
        layout.addWidget(self._color_dropdown)

        layout.addWidget(_make_separator())

        # ---- Type ----
        lbl = QLabel("Type")
        lbl.setStyleSheet(_LABEL)
        layout.addWidget(lbl)

        self._type_combo = QComboBox()
        self._type_combo.addItems(["Linear", "Radial", "Conical", "Diamond"])
        self._type_combo.setMaximumHeight(24)
        self._type_combo.setFixedWidth(90)
        self._type_combo.setStyleSheet(_COMBO.format(widget="QComboBox", accent=_ACCENT))
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        layout.addWidget(self._type_combo)

        layout.addWidget(_make_separator())

        # ---- Opacity ----
        lbl2 = QLabel("Opacity")
        lbl2.setStyleSheet(_LABEL)
        layout.addWidget(lbl2)

        self._opacity_spin = QSpinBox()
        self._opacity_spin.setRange(0, 100)
        self._opacity_spin.setValue(100)
        self._opacity_spin.setSuffix("%")
        self._opacity_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._opacity_spin.setMaximumWidth(60)
        self._opacity_spin.setMaximumHeight(22)
        self._opacity_spin.setStyleSheet(_SPIN.format(max_w=60, accent=_ACCENT))
        self._opacity_spin.valueChanged.connect(self._on_opacity_changed)
        layout.addWidget(self._opacity_spin)

        layout.addWidget(_make_separator())

        # ---- Reverse ----
        self._rev_btn = QPushButton("\u27F3 Reverse")
        self._rev_btn.setFixedHeight(24)
        self._rev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rev_btn.setStyleSheet(_FLAT_BTN.format())
        self._rev_btn.clicked.connect(self._on_reverse)
        layout.addWidget(self._rev_btn)

        layout.addStretch()

    # ---- slots --------------------------------------------------------------

    def _on_gradient_pick(self, fill) -> None:
        self.property_changed.emit("gradient_fill", fill)

    def _on_type_changed(self, text: str) -> None:
        self.property_changed.emit("gradient_type", text.lower())

    def _on_opacity_changed(self, val: int) -> None:
        self.property_changed.emit("opacity", val / 100.0)

    def _on_reverse(self) -> None:
        self.property_changed.emit("reverse", True)

    # ---- sync from tool state ----------------------------------------------

    def sync_from_tool(self, tool) -> None:
        """Update controls to reflect the gradient tool's current state."""
        self.blockSignals(True)
        try:
            if hasattr(tool, "gradient_type"):
                idx = {"linear": 0, "radial": 1, "conical": 2, "diamond": 3}.get(
                    tool.gradient_type, 0
                )
                self._type_combo.setCurrentIndex(idx)
            if hasattr(tool, "opacity"):
                self._opacity_spin.setValue(int(tool.opacity * 100))
        finally:
            self.blockSignals(False)


# ============================================================================
# Crop properties bar
# ============================================================================

class CropPropertiesBar(QWidget):
    """Horizontal bar with crop-specific controls: mode selector, dimensions,
    Apply / Cancel buttons."""

    property_changed = Signal(str, object)
    apply_requested = Signal()       # user wants to commit the crop
    cancel_requested = Signal()      # user wants to discard the crop box

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        _spin_css = _SPIN.format(max_w=70, accent=_ACCENT)

        # ---- Mode selector ----
        lbl = QLabel("Mode")
        lbl.setStyleSheet(_LABEL)
        layout.addWidget(lbl)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Canvas Crop", "Layer Crop"])
        self._mode_combo.setMaximumHeight(24)
        self._mode_combo.setFixedWidth(110)
        self._mode_combo.setStyleSheet(_COMBO.format(widget="QComboBox", accent=_ACCENT))
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        layout.addWidget(self._mode_combo)

        layout.addWidget(_make_separator())

        # ---- Crop dimensions (read-only display, updated live) ----
        lbl_x = QLabel("X")
        lbl_x.setStyleSheet(_LABEL)
        layout.addWidget(lbl_x)
        self._x_spin = QSpinBox()
        self._x_spin.setRange(0, 99999)
        self._x_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._x_spin.setReadOnly(True)
        self._x_spin.setMaximumWidth(55)
        self._x_spin.setMaximumHeight(22)
        self._x_spin.setStyleSheet(_spin_css)
        layout.addWidget(self._x_spin)

        lbl_y = QLabel("Y")
        lbl_y.setStyleSheet(_LABEL)
        layout.addWidget(lbl_y)
        self._y_spin = QSpinBox()
        self._y_spin.setRange(0, 99999)
        self._y_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._y_spin.setReadOnly(True)
        self._y_spin.setMaximumWidth(55)
        self._y_spin.setMaximumHeight(22)
        self._y_spin.setStyleSheet(_spin_css)
        layout.addWidget(self._y_spin)

        lbl_w = QLabel("W")
        lbl_w.setStyleSheet(_LABEL)
        layout.addWidget(lbl_w)
        self._w_spin = QSpinBox()
        self._w_spin.setRange(0, 99999)
        self._w_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._w_spin.setReadOnly(True)
        self._w_spin.setMaximumWidth(55)
        self._w_spin.setMaximumHeight(22)
        self._w_spin.setStyleSheet(_spin_css)
        layout.addWidget(self._w_spin)

        lbl_h = QLabel("H")
        lbl_h.setStyleSheet(_LABEL)
        layout.addWidget(lbl_h)
        self._h_spin = QSpinBox()
        self._h_spin.setRange(0, 99999)
        self._h_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._h_spin.setReadOnly(True)
        self._h_spin.setMaximumWidth(55)
        self._h_spin.setMaximumHeight(22)
        self._h_spin.setStyleSheet(_spin_css)
        layout.addWidget(self._h_spin)

        layout.addWidget(_make_separator())

        # ---- Apply / Cancel ----
        self._apply_btn = QPushButton("✓ Apply")
        self._apply_btn.setFixedHeight(24)
        self._apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_btn.setStyleSheet(
            _FLAT_BTN.format() + """
            QPushButton { color: #88cc88; font-weight: bold; }
            QPushButton:hover { color: #aaffaa; }
        """)
        self._apply_btn.clicked.connect(self.apply_requested.emit)
        layout.addWidget(self._apply_btn)

        self._cancel_btn = QPushButton("✗ Cancel")
        self._cancel_btn.setFixedHeight(24)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setStyleSheet(
            _FLAT_BTN.format() + """
            QPushButton { color: #cc8888; }
            QPushButton:hover { color: #ffaaaa; }
        """)
        self._cancel_btn.clicked.connect(self.cancel_requested.emit)
        layout.addWidget(self._cancel_btn)

        layout.addStretch()

    # ---- Slots --------------------------------------------------------------

    def _on_mode_changed(self, index: int) -> None:
        mode_name = "canvas" if index == 0 else "layer"
        self.property_changed.emit("crop_mode", mode_name)

    # ---- Public helpers -----------------------------------------------------

    def set_dimensions(self, x: int, y: int, w: int, h: int) -> None:
        """Update the displayed crop rectangle dimensions."""
        self._x_spin.setValue(x)
        self._y_spin.setValue(y)
        self._w_spin.setValue(w)
        self._h_spin.setValue(h)

    def clear_dimensions(self) -> None:
        for sp in (self._x_spin, self._y_spin, self._w_spin, self._h_spin):
            sp.setValue(0)

    def sync_from_tool(self, tool) -> None:
        """Update controls to match the crop tool state."""
        self.blockSignals(True)
        try:
            from ...tools.crop_tool import CropMode
            idx = 0 if tool.mode == CropMode.CANVAS else 1
            self._mode_combo.setCurrentIndex(idx)
            if tool.box is not None:
                self.set_dimensions(*tool.box)
            else:
                self.clear_dimensions()
        finally:
            self.blockSignals(False)


# ============================================================================
# Main Properties Panel
# ============================================================================

class PropertiesPanel(QWidget):
    """Horizontal dynamic property editor for the current context.

    Switches between a generic slider layout and the text-specific bar
    depending on the active tool.
    """

    value_changed = Signal(str, object)
    # Specialised text property signal
    text_property_changed = Signal(str, object)
    # Gradient property signal
    gradient_property_changed = Signal(str, object)
    # Move-tool alignment signal — carries the action name
    align_requested = Signal(str)
    # Crop signals
    crop_property_changed = Signal(str, object)
    crop_apply = Signal()
    crop_cancel = Signal()

    _PANEL_BG = "#2e2e2e"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            PropertiesPanel, PropertiesPanel > QWidget {{
                background-color: {self._PANEL_BG};
            }}
            QLabel {{ background: transparent; }}
        """)

        self._main_layout = QHBoxLayout(self)
        self._main_layout.setContentsMargins(8, 0, 8, 0)
        self._main_layout.setSpacing(6)
        
        # Generic slider container
        self._props_container = QWidget()
        self._props_layout = QHBoxLayout(self._props_container)
        self._props_layout.setContentsMargins(0, 0, 0, 0)
        self._props_layout.setSpacing(10)
        self._main_layout.addWidget(self._props_container)
        
        # Text properties bar (hidden by default)
        self._text_bar = TextPropertiesBar()
        self._text_bar.property_changed.connect(
            lambda k, v: self.text_property_changed.emit(k, v))
        self._text_bar.hide()
        self._main_layout.addWidget(self._text_bar)

        # Gradient properties bar (hidden by default)
        self._gradient_bar = GradientPropertiesBar()
        self._gradient_bar.property_changed.connect(
            lambda k, v: self.gradient_property_changed.emit(k, v))
        self._gradient_bar.hide()
        self._main_layout.addWidget(self._gradient_bar)

        # Move-tool alignment bar (hidden by default)
        self._move_bar = MovePropertiesBar()
        self._move_bar.align_requested.connect(
            lambda action: self.align_requested.emit(action))
        self._move_bar.hide()
        self._main_layout.addWidget(self._move_bar)

        # Crop properties bar (hidden by default)
        self._crop_bar = CropPropertiesBar()
        self._crop_bar.property_changed.connect(
            lambda k, v: self.crop_property_changed.emit(k, v))
        self._crop_bar.apply_requested.connect(self.crop_apply.emit)
        self._crop_bar.cancel_requested.connect(self.crop_cancel.emit)
        self._crop_bar.hide()
        self._main_layout.addWidget(self._crop_bar)

        self._main_layout.addStretch()
        
        self._widgets: dict[str, CompactPropertyWidget] = {}
        self._text_mode = False
        self._gradient_mode = False
        self._move_mode = False
        self._crop_mode = False

        self.setFixedHeight(34)

    # ---- Mode switching ----

    def set_text_mode(self, enabled: bool, tool=None) -> None:
        """Switch between generic slider mode and text properties mode."""
        self._text_mode = enabled
        self._gradient_mode = False
        self._move_mode = False
        self._crop_mode = False
        self._props_container.setVisible(not enabled)
        self._text_bar.setVisible(enabled)
        self._gradient_bar.setVisible(False)
        self._move_bar.setVisible(False)
        self._crop_bar.setVisible(False)
        if enabled and tool is not None:
            self._text_bar.sync_from_tool(tool)

    def set_gradient_mode(self, enabled: bool, tool=None) -> None:
        """Switch to gradient properties mode."""
        self._gradient_mode = enabled
        self._text_mode = False
        self._move_mode = False
        self._crop_mode = False
        self._props_container.setVisible(not enabled)
        self._text_bar.setVisible(False)
        self._gradient_bar.setVisible(enabled)
        self._move_bar.setVisible(False)
        self._crop_bar.setVisible(False)
        if enabled and tool is not None:
            self._gradient_bar.sync_from_tool(tool)

    def set_move_mode(self, enabled: bool) -> None:
        """Switch to move-tool alignment bar."""
        self._move_mode = enabled
        self._text_mode = False
        self._gradient_mode = False
        self._crop_mode = False
        self._props_container.setVisible(not enabled)
        self._text_bar.setVisible(False)
        self._gradient_bar.setVisible(False)
        self._move_bar.setVisible(enabled)
        self._crop_bar.setVisible(False)

    def set_crop_mode(self, enabled: bool, tool=None) -> None:
        """Switch to crop properties bar."""
        self._crop_mode = enabled
        self._text_mode = False
        self._gradient_mode = False
        self._move_mode = False
        self._props_container.setVisible(not enabled)
        self._text_bar.setVisible(False)
        self._gradient_bar.setVisible(False)
        self._move_bar.setVisible(False)
        self._crop_bar.setVisible(enabled)
        if enabled and tool is not None:
            self._crop_bar.sync_from_tool(tool)

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

    # ---- Generic API (unchanged) ----

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
