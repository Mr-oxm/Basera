"""Properties panel — shows editable parameters for the active layer / tool.

When the Text tool is active, the panel switches to a specialised
layout with font picker, bold/italic/underline toggles, alignment,
colour, and spacing controls.
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Qt, QPoint, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QFont, QColor, QIcon
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDoubleSpinBox, QFontComboBox,
    QHBoxLayout, QLabel, QPushButton, QSlider, QSpinBox,
    QVBoxLayout, QWidget, QFrame,
)


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
        
        name_label = QLabel(label + ":")
        name_label.setMinimumWidth(50)
        name_label.setMaximumWidth(80)
        name_label.setStyleSheet("font-size: 9pt; color: #aaa;")
        layout.addWidget(name_label)
        
        self.value_spin = QDoubleSpinBox()
        self.value_spin.setRange(min_val, max_val)
        self.value_spin.setSingleStep(step)
        self.value_spin.setValue(value)
        self.value_spin.setMaximumWidth(65)
        self.value_spin.setMinimumHeight(22)
        self.value_spin.setMaximumHeight(22)
        self.value_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.value_spin.setStyleSheet("font-size: 9pt; padding: 2px;")
        self.value_spin.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self.value_spin)
        
        self.expand_btn = QPushButton("▼")
        self.expand_btn.setFixedSize(20, 20)
        self.expand_btn.setToolTip(f"Show/hide {label} slider")
        self.expand_btn.setCheckable(True)
        self.expand_btn.clicked.connect(self._toggle_dropdown)
        self.expand_btn.setStyleSheet("""
            QPushButton {
                font-size: 10pt; padding: 0px;
                border: 1px solid #555; border-radius: 2px;
                background-color: #3a3a3a;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:checked { background-color: #505050; }
        """)
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
            self.expand_btn.setText("▲")
        else:
            if self.dropdown:
                self.dropdown.hide()
            self.expand_btn.setText("▼")
    
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
# Text properties bar
# ============================================================================

_TOGGLE_STYLE = """
    QPushButton {{
        font-size: {font_size}pt; padding: 2px 6px;
        border: 1px solid #555; border-radius: 2px;
        background-color: #3a3a3a; color: #ccc;
        min-width: 24px; min-height: 22px;
    }}
    QPushButton:hover {{ background-color: #4a4a4a; }}
    QPushButton:checked {{ background-color: #0078d4; color: white; border-color: #0078d4; }}
"""

_ALIGN_STYLE = """
    QPushButton {
        font-size: 9pt; padding: 2px 4px;
        border: 1px solid #555; border-radius: 2px;
        background-color: #3a3a3a; color: #ccc;
        min-width: 22px; min-height: 22px;
    }
    QPushButton:hover { background-color: #4a4a4a; }
    QPushButton:checked { background-color: #0078d4; color: white; border-color: #0078d4; }
"""

_LABEL_STYLE = "font-size: 9pt; color: #aaa;"

_SPIN_STYLE = """
    QSpinBox, QDoubleSpinBox {
        font-size: 9pt; padding: 2px; max-width: 55px;
        min-height: 22px; max-height: 22px;
    }
"""


class TextPropertiesBar(QWidget):
    """Horizontal bar with all text formatting controls."""

    # Emitted as (key, value) for any property change
    property_changed = Signal(str, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        _COMBO_ARROW_STYLE = """
            {widget}::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 20px;
                border-left: 1px solid #555;
                background: #3a3a3a;
            }}
            {widget}::drop-down:hover {{
                background: #4a4a4a;
            }}
            {widget}::down-arrow {{
                image: none;
                width: 0px; height: 0px;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #ccc;
            }}
        """

        # ---- Font family ----
        lbl = QLabel("Font:")
        lbl.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(lbl)

        self._font_combo = FontComboBoxWithPreview()
        self._font_combo.setMinimumWidth(160)
        self._font_combo.setMaximumWidth(200)
        self._font_combo.setMaximumHeight(24)
        self._font_combo.setStyleSheet(
            "QFontComboBox { font-size: 9pt; padding: 2px 4px; }"
            + _COMBO_ARROW_STYLE.format(widget="QFontComboBox")
        )

        # Connect font change (when user clicks to select)
        self._font_combo.currentFontChanged.connect(self._on_font_selected)

        # Connect hover preview signals
        self._font_combo.font_hovered.connect(self._on_font_hover_preview)
        self._font_combo.hover_ended.connect(self._on_font_hover_end)

        layout.addWidget(self._font_combo)

        # ---- Font size (editable dropdown with common sizes + hover preview) ----
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
        # Only accept integers in the editable field
        from PySide6.QtGui import QIntValidator
        self._size_combo.setValidator(QIntValidator(1, 2000))
        self._size_combo.setStyleSheet(
            "QComboBox { font-size: 9pt; padding: 2px 4px; "
            "min-height: 20px; max-height: 22px; }"
            + _COMBO_ARROW_STYLE.format(widget="QComboBox")
        )
        self._size_combo.currentTextChanged.connect(self._on_size_changed)
        self._size_combo.size_hovered.connect(self._on_size_hover_preview)
        self._size_combo.hover_ended.connect(self._on_size_hover_end)
        layout.addWidget(self._size_combo)

        # ---- Separator ----
        layout.addWidget(self._separator())

        # ---- Bold / Italic / Underline / Strikethrough ----
        self._bold_btn = self._toggle_btn("B", "bold", bold=True)
        layout.addWidget(self._bold_btn)
        self._italic_btn = self._toggle_btn("I", "italic", italic=True)
        layout.addWidget(self._italic_btn)
        self._underline_btn = self._toggle_btn("U", "underline", underline=True)
        layout.addWidget(self._underline_btn)
        self._strike_btn = self._toggle_btn("S", "strikethrough", strike=True)
        layout.addWidget(self._strike_btn)

        layout.addWidget(self._separator())

        # ---- Alignment ----
        self._align_left = self._align_btn("≡L", "left")
        self._align_center = self._align_btn("≡C", "center")
        self._align_right = self._align_btn("≡R", "right")
        self._align_left.setChecked(True)
        layout.addWidget(self._align_left)
        layout.addWidget(self._align_center)
        layout.addWidget(self._align_right)

        layout.addWidget(self._separator())

        # ---- Color button ----
        lbl2 = QLabel("Color:")
        lbl2.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(lbl2)
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(26, 22)
        self._color_btn.setStyleSheet(
            "background-color: #000000; border: 1px solid #555; border-radius: 2px;")
        self._color_btn.clicked.connect(self._pick_color)
        self._current_color = QColor(0, 0, 0)
        layout.addWidget(self._color_btn)

        layout.addWidget(self._separator())

        # ---- Letter spacing ----
        lbl3 = QLabel("Tracking:")
        lbl3.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(lbl3)
        self._tracking_spin = QDoubleSpinBox()
        self._tracking_spin.setRange(-20.0, 100.0)
        self._tracking_spin.setValue(0.0)
        self._tracking_spin.setSingleStep(0.5)
        self._tracking_spin.setStyleSheet(_SPIN_STYLE)
        self._tracking_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._tracking_spin.valueChanged.connect(
            lambda v: self.property_changed.emit("letter_spacing", v))
        layout.addWidget(self._tracking_spin)

        # ---- Line height ----
        lbl4 = QLabel("Leading:")
        lbl4.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(lbl4)
        self._leading_spin = QDoubleSpinBox()
        self._leading_spin.setRange(0.5, 5.0)
        self._leading_spin.setValue(1.2)
        self._leading_spin.setSingleStep(0.1)
        self._leading_spin.setStyleSheet(_SPIN_STYLE)
        self._leading_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._leading_spin.valueChanged.connect(
            lambda v: self.property_changed.emit("line_height", v))
        layout.addWidget(self._leading_spin)

        # ---- Paragraph spacing ----
        lbl5 = QLabel("Para:")
        lbl5.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(lbl5)
        self._para_spin = QDoubleSpinBox()
        self._para_spin.setRange(0.0, 200.0)
        self._para_spin.setValue(0.0)
        self._para_spin.setSingleStep(1.0)
        self._para_spin.setStyleSheet(_SPIN_STYLE)
        self._para_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._para_spin.valueChanged.connect(
            lambda v: self.property_changed.emit("paragraph_spacing", v))
        layout.addWidget(self._para_spin)

        layout.addStretch()

    # ---- Helpers ----

    def _separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #555;")
        sep.setFixedWidth(2)
        return sep

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
        btn.setStyleSheet(_TOGGLE_STYLE.format(font_size=10))
        btn.toggled.connect(lambda checked: self.property_changed.emit(key, checked))
        return btn

    def _align_btn(self, label: str, alignment: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setStyleSheet(_ALIGN_STYLE)
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

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(self._current_color, self, "Text Color",
                                      QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            self._current_color = color
            self._color_btn.setStyleSheet(
                f"background-color: {color.name()}; border: 1px solid #555; border-radius: 2px;")
            from ...core.color import Color, SolidFill
            c = Color.from_rgb8(color.red(), color.green(), color.blue(), color.alpha())
            self.property_changed.emit("fill_color", SolidFill(color=c))

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
                self._current_color = QColor(int(c[0] * 255), int(c[1] * 255),
                                             int(c[2] * 255), int(c[3] * 255))
                self._color_btn.setStyleSheet(
                    f"background-color: {self._current_color.name()}; "
                    f"border: 1px solid #555; border-radius: 2px;")
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

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        
        self._main_layout = QHBoxLayout(self)
        self._main_layout.setContentsMargins(4, 2, 4, 2)
        self._main_layout.setSpacing(8)
        
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
        
        self._main_layout.addStretch()
        
        self._widgets: dict[str, CompactPropertyWidget] = {}
        self._text_mode = False
        
        self.setFixedHeight(34)

    # ---- Mode switching ----

    def set_text_mode(self, enabled: bool, tool=None) -> None:
        """Switch between generic slider mode and text properties mode."""
        self._text_mode = enabled
        self._props_container.setVisible(not enabled)
        self._text_bar.setVisible(enabled)
        if enabled and tool is not None:
            self._text_bar.sync_from_tool(tool)

    @property
    def text_bar(self) -> TextPropertiesBar:
        return self._text_bar

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
