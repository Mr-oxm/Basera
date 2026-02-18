"""Text tool properties bar — font, size, bold/italic, alignment, color, spacing."""

from __future__ import annotations

from PySide6.QtGui import QFont, QIntValidator
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QWidget,
)

from ...widgets.color_dropdown import ColorDropdown
from .base import (
    ACCENT,
    ALIGN_BTN,
    COMBO,
    LABEL,
    SPIN,
    TOGGLE,
    FontComboBoxWithPreview,
    SizeComboBoxWithPreview,
    make_separator,
)


class TextPropertiesBar(QWidget):
    """Horizontal bar with all text formatting controls."""

    from PySide6.QtCore import Signal
    property_changed = Signal(str, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        _spin_css = SPIN.format(max_w=70, accent=ACCENT)

        lbl = QLabel("Font")
        lbl.setStyleSheet(LABEL)
        layout.addWidget(lbl)

        self._font_combo = FontComboBoxWithPreview()
        self._font_combo.setMinimumWidth(160)
        self._font_combo.setMaximumWidth(200)
        self._font_combo.setMaximumHeight(24)
        self._font_combo.setStyleSheet(COMBO.format(widget="QFontComboBox", accent=ACCENT))
        self._font_combo.currentFontChanged.connect(self._on_font_selected)
        self._font_combo.font_hovered.connect(self._on_font_hover_preview)
        self._font_combo.hover_ended.connect(self._on_font_hover_end)
        layout.addWidget(self._font_combo)

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
        self._size_combo.setValidator(QIntValidator(1, 2000))
        self._size_combo.setStyleSheet(COMBO.format(widget="QComboBox", accent=ACCENT))
        self._size_combo.currentTextChanged.connect(self._on_size_changed)
        self._size_combo.size_hovered.connect(self._on_size_hover_preview)
        self._size_combo.hover_ended.connect(self._on_size_hover_end)
        layout.addWidget(self._size_combo)

        layout.addWidget(make_separator())

        self._bold_btn = self._toggle_btn("B", "bold", bold=True)
        layout.addWidget(self._bold_btn)
        self._italic_btn = self._toggle_btn("I", "italic", italic=True)
        layout.addWidget(self._italic_btn)
        self._underline_btn = self._toggle_btn("U", "underline", underline=True)
        layout.addWidget(self._underline_btn)
        self._strike_btn = self._toggle_btn("S", "strikethrough", strike=True)
        layout.addWidget(self._strike_btn)

        layout.addWidget(make_separator())

        self._align_left = self._align_btn("\u2261L", "left")
        self._align_center = self._align_btn("\u2261C", "center")
        self._align_right = self._align_btn("\u2261R", "right")
        self._align_left.setChecked(True)
        layout.addWidget(self._align_left)
        layout.addWidget(self._align_center)
        layout.addWidget(self._align_right)

        layout.addWidget(make_separator())

        self._color_dropdown = ColorDropdown(
            label="Color:", show_gradient=True, show_wheel=True,
        )
        self._color_dropdown.color_committed.connect(self._on_color_committed)
        self._color_dropdown.color_changed.connect(self._on_color_preview)
        self._color_dropdown.gradient_changed.connect(self._on_gradient_pick)
        layout.addWidget(self._color_dropdown)

        layout.addWidget(make_separator())

        lbl3 = QLabel("Tracking")
        lbl3.setStyleSheet(LABEL)
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

        lbl4 = QLabel("Leading")
        lbl4.setStyleSheet(LABEL)
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

        lbl5 = QLabel("Para")
        lbl5.setStyleSheet(LABEL)
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
        btn.setStyleSheet(TOGGLE.format(font_size=10))
        btn.toggled.connect(lambda checked: self.property_changed.emit(key, checked))
        return btn

    def _align_btn(self, label: str, alignment: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setStyleSheet(ALIGN_BTN)
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
        self.property_changed.emit("font_family", font.family())

    def _on_font_hover_preview(self, font_family: str) -> None:
        self.property_changed.emit("_preview_font_family", font_family)

    def _on_font_hover_end(self) -> None:
        self.property_changed.emit("_preview_font_end", None)

    def _on_size_changed(self, text: str) -> None:
        try:
            val = int(text)
            if 1 <= val <= 2000:
                self.property_changed.emit("font_size", val)
        except ValueError:
            pass

    def _on_size_hover_preview(self, size: int) -> None:
        self.property_changed.emit("_preview_font_size", size)

    def _on_size_hover_end(self) -> None:
        self.property_changed.emit("_preview_font_size_end", None)

    def _on_color_committed(self, c) -> None:
        from ....core.color import SolidFill
        self.property_changed.emit("fill_color", SolidFill(color=c))

    def _on_color_preview(self, c) -> None:
        from ....core.color import SolidFill
        self.property_changed.emit("_preview_fill_color", SolidFill(color=c))

    def _on_gradient_pick(self, fill) -> None:
        self.property_changed.emit("fill_color", fill)

    def sync_from_tool(self, tool) -> None:
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
                from ....core.color import Color
                col = Color(c[0], c[1], c[2], c[3] if len(c) > 3 else 1.0)
                self._color_dropdown.set_color(col)
        finally:
            self.blockSignals(False)
