"""New Project dialog — professional template-based project creation.

Features:
* 7 template categories with named presets and aspect-ratio previews
* Custom dimension fields with lock-aspect-ratio toggle
* Portrait / Landscape swap that auto-detects orientation
* Units dropdown (px, in, cm, mm, pt), Resolution / DPI presets
* Color Mode (RGB / CMYK / LAB / Grayscale), Color Profile
* Background colour swatches (white, black, transparent, custom)
* Live preview box showing aspect ratio
* Estimated uncompressed file size calculation
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QPainter, QBrush, QPen, QPixmap, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QSpinBox, QDoubleSpinBox, QComboBox,
    QWidget, QScrollArea, QFrame, QButtonGroup,
    QSizePolicy, QColorDialog, QGraphicsDropShadowEffect,
)

from ..styles import render_qss


# ---------------------------------------------------------------------------
# Template presets: (name, width_px, height_px, dpi)
# ---------------------------------------------------------------------------

PRESETS = {
    "Custom": [],
    "Print": [
        ("A4", 2480, 3508, 300),
        ("A3", 3508, 4961, 300),
        ("A5", 1748, 2480, 300),
        ("Letter", 2550, 3300, 300),
        ("Legal", 2550, 4200, 300),
        ("Tabloid", 3300, 5100, 300),
        ("B5", 2079, 2953, 300),
        ("5 × 7 in", 1500, 2100, 300),
        ("4 × 6 in", 1200, 1800, 300),
    ],
    "Web": [
        ("1920 × 1080", 1920, 1080, 72),
        ("1280 × 720", 1280, 720, 72),
        ("1366 × 768", 1366, 768, 72),
        ("800 × 600", 800, 600, 72),
        ("Banner 728 × 90", 728, 90, 72),
        ("Favicon 64 × 64", 64, 64, 72),
        ("OG Image 1200 × 630", 1200, 630, 72),
    ],
    "Photo": [
        ("Full HD (1920 × 1080)", 1920, 1080, 72),
        ("4K UHD (3840 × 2160)", 3840, 2160, 72),
        ("8K (7680 × 4320)", 7680, 4320, 72),
        ("5 × 7 Print", 1500, 2100, 300),
        ("8 × 10 Print", 2400, 3000, 300),
        ("Square 1:1 (2000)", 2000, 2000, 72),
        ("3:2 (3000 × 2000)", 3000, 2000, 72),
        ("4:3 (2800 × 2100)", 2800, 2100, 72),
    ],
    "Social Media": [
        ("Instagram Post (1080²)", 1080, 1080, 72),
        ("Instagram Story (1080 × 1920)", 1080, 1920, 72),
        ("Facebook Cover (820 × 312)", 820, 312, 72),
        ("Facebook Post (1200 × 630)", 1200, 630, 72),
        ("Twitter Post (1600 × 900)", 1600, 900, 72),
        ("Twitter Header (1500 × 500)", 1500, 500, 72),
        ("LinkedIn Banner (1584 × 396)", 1584, 396, 72),
        ("YouTube Thumbnail (1280 × 720)", 1280, 720, 72),
        ("Pinterest Pin (1000 × 1500)", 1000, 1500, 72),
        ("TikTok (1080 × 1920)", 1080, 1920, 72),
    ],
    "Video": [
        ("1080p (1920 × 1080)", 1920, 1080, 72),
        ("720p (1280 × 720)", 1280, 720, 72),
        ("4K (3840 × 2160)", 3840, 2160, 72),
        ("2K (2560 × 1440)", 2560, 1440, 72),
        ("DCI 4K (4096 × 2160)", 4096, 2160, 72),
        ("Ultrawide (2560 × 1080)", 2560, 1080, 72),
        ("Vertical 9:16 (1080 × 1920)", 1080, 1920, 72),
    ],
    "Art": [
        ("Square Canvas (4000²)", 4000, 4000, 300),
        ("A3 Landscape", 4961, 3508, 300),
        ("A2 Portrait", 4961, 7016, 300),
        ("Digital Painting (3000 × 2000)", 3000, 2000, 150),
        ("Pixel Art 64 × 64", 64, 64, 72),
        ("Pixel Art 128 × 128", 128, 128, 72),
        ("Pixel Art 256 × 256", 256, 256, 72),
        ("Icon 512 × 512", 512, 512, 72),
    ],
}

UNITS = ["px", "in", "cm", "mm", "pt"]
COLOR_MODES = ["RGB", "CMYK", "LAB", "Grayscale"]
COLOR_PROFILES = [
    "sRGB IEC61966-2.1",
    "Adobe RGB (1998)",
    "ProPhoto RGB",
    "Display P3",
]
DPI_PRESETS = [72, 96, 150, 200, 300, 600, 1200]

# Bytes per channel per color mode (8-bit)
_CHANNEL_MAP = {"RGB": 3, "CMYK": 4, "LAB": 3, "Grayscale": 1}


class _AspectPreview(QWidget):
    """Live aspect-ratio preview box."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("LivePreview")
        self.setMinimumSize(180, 140)
        self._w = 1920
        self._h = 1080
        self._bg_color = QColor(255, 255, 255)
        self._transparent = False

    def set_dimensions(self, w: int, h: int) -> None:
        self._w = max(w, 1)
        self._h = max(h, 1)
        self.update()

    def set_background(self, color: QColor, transparent: bool = False) -> None:
        self._bg_color = color
        self._transparent = transparent
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        area_w = self.width() - 20
        area_h = self.height() - 20
        if area_w <= 0 or area_h <= 0:
            p.end()
            return

        # Fit within area
        scale = min(area_w / self._w, area_h / self._h)
        rect_w = int(self._w * scale)
        rect_h = int(self._h * scale)
        x = (self.width() - rect_w) // 2
        y = (self.height() - rect_h) // 2

        # Shadow
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 30))
        p.drawRoundedRect(x + 3, y + 3, rect_w, rect_h, 4, 4)

        # Background
        if self._transparent:
            # Checkerboard
            checker_size = 8
            for cy in range(y, y + rect_h, checker_size):
                for cx in range(x, x + rect_w, checker_size):
                    row = (cy - y) // checker_size
                    col = (cx - x) // checker_size
                    c = QColor(200, 200, 200) if (row + col) % 2 == 0 else QColor(160, 160, 160)
                    p.setBrush(c)
                    cw = min(checker_size, x + rect_w - cx)
                    ch = min(checker_size, y + rect_h - cy)
                    p.drawRect(cx, cy, cw, ch)
        else:
            p.setBrush(self._bg_color)
            p.drawRoundedRect(x, y, rect_w, rect_h, 4, 4)

        # Border
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.drawRoundedRect(x, y, rect_w, rect_h, 4, 4)

        # Dimension text
        p.setPen(QColor(180, 180, 180))
        font = QFont("Segoe UI", 9)
        p.setFont(font)
        p.drawText(x, y + rect_h + 14, f"{self._w} × {self._h} px")

        p.end()


class NewProjectDialog(QDialog):
    """Professional New Project dialog with templates, settings, and preview."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NewProjectDialog")
        self.setWindowTitle("New Project")
        self.setMinimumSize(820, 600)
        self.resize(900, 660)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        self._aspect_locked = False
        self._aspect_ratio = 1920 / 1080
        self._suppress_ratio = False

        self._build_ui()
        self._apply_theme()
        self._select_category("Photo")
        self._update_preview()

    def _apply_theme(self) -> None:
        from ..theme import ThemeManager
        palette = ThemeManager.instance().active_palette
        self.setStyleSheet(render_qss("new_project_dialog.qss", palette))

    # ---- UI ---------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        # Title
        title = QLabel("New Project")
        title.setObjectName("DialogTitle")
        root.addWidget(title)

        # ---- Main body: left (categories + presets) | right (settings + preview) ----
        body = QHBoxLayout()
        body.setSpacing(16)

        # ---- Left: categories + preset grid ----
        left = QVBoxLayout()
        left.setSpacing(10)

        # Category tabs
        cat_layout = QHBoxLayout()
        cat_layout.setSpacing(4)
        self._cat_group = QButtonGroup(self)
        self._cat_group.setExclusive(True)

        for cat_name in PRESETS.keys():
            btn = QPushButton(cat_name)
            btn.setObjectName("CategoryTab")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._cat_group.addButton(btn)
            cat_layout.addWidget(btn)
            btn.clicked.connect(lambda _, n=cat_name: self._select_category(n))

        cat_layout.addStretch()
        left.addLayout(cat_layout)

        # Preset scroll area
        self._preset_scroll = QScrollArea()
        self._preset_scroll.setWidgetResizable(True)
        self._preset_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._preset_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._preset_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._preset_container = QWidget()
        self._preset_container.setStyleSheet("background: transparent;")
        self._preset_grid = QGridLayout(self._preset_container)
        self._preset_grid.setSpacing(8)
        self._preset_grid.setContentsMargins(0, 0, 0, 0)
        self._preset_scroll.setWidget(self._preset_container)

        left.addWidget(self._preset_scroll, 1)
        body.addLayout(left, 3)

        # ---- Right: settings panel + preview ----
        right = QVBoxLayout()
        right.setSpacing(12)

        settings = QWidget()
        settings.setObjectName("SettingsPanel")
        settings_layout = QVBoxLayout(settings)
        settings_layout.setContentsMargins(16, 14, 16, 14)
        settings_layout.setSpacing(10)

        # Dimensions row
        dim_title = QLabel("DIMENSIONS")
        dim_title.setObjectName("SettingLabel")
        dim_title.setStyleSheet("font-size: 10px; font-weight: 700; letter-spacing: 0.06em;")
        settings_layout.addWidget(dim_title)

        dim_row = QHBoxLayout()
        dim_row.setSpacing(8)

        # Width
        w_layout = QVBoxLayout()
        w_layout.setSpacing(2)
        w_label = QLabel("W")
        w_label.setObjectName("DimLabel")
        w_layout.addWidget(w_label)
        self._width_spin = QSpinBox()
        self._width_spin.setObjectName("DimInput")
        self._width_spin.setRange(1, 30000)
        self._width_spin.setValue(1920)
        self._width_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._width_spin.valueChanged.connect(self._on_width_changed)
        w_layout.addWidget(self._width_spin)
        dim_row.addLayout(w_layout)

        # Link button
        self._link_btn = QPushButton("🔗")
        self._link_btn.setObjectName("LinkButton")
        self._link_btn.setCheckable(True)
        self._link_btn.setToolTip("Lock aspect ratio")
        self._link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._link_btn.toggled.connect(self._on_lock_toggled)
        dim_row.addWidget(self._link_btn, 0, Qt.AlignmentFlag.AlignBottom)

        # Height
        h_layout = QVBoxLayout()
        h_layout.setSpacing(2)
        h_label = QLabel("H")
        h_label.setObjectName("DimLabel")
        h_layout.addWidget(h_label)
        self._height_spin = QSpinBox()
        self._height_spin.setObjectName("DimInput")
        self._height_spin.setRange(1, 30000)
        self._height_spin.setValue(1080)
        self._height_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._height_spin.valueChanged.connect(self._on_height_changed)
        h_layout.addWidget(self._height_spin)
        dim_row.addLayout(h_layout)

        settings_layout.addLayout(dim_row)

        # Orientation toggle
        orient_row = QHBoxLayout()
        orient_row.setSpacing(6)

        self._orient_group = QButtonGroup(self)
        self._landscape_btn = QPushButton("◻ Landscape")
        self._landscape_btn.setObjectName("OrientationButton")
        self._landscape_btn.setCheckable(True)
        self._landscape_btn.setChecked(True)
        self._landscape_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._orient_group.addButton(self._landscape_btn)
        self._landscape_btn.clicked.connect(lambda: self._set_orientation("landscape"))
        orient_row.addWidget(self._landscape_btn)

        self._portrait_btn = QPushButton("▯ Portrait")
        self._portrait_btn.setObjectName("OrientationButton")
        self._portrait_btn.setCheckable(True)
        self._portrait_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._orient_group.addButton(self._portrait_btn)
        self._portrait_btn.clicked.connect(lambda: self._set_orientation("portrait"))
        orient_row.addWidget(self._portrait_btn)

        orient_row.addStretch()
        settings_layout.addLayout(orient_row)

        # Units + DPI row
        units_row = QHBoxLayout()
        units_row.setSpacing(10)

        u_layout = QVBoxLayout()
        u_layout.setSpacing(2)
        u_label = QLabel("Units")
        u_label.setObjectName("SettingLabel")
        u_layout.addWidget(u_label)
        self._units_combo = QComboBox()
        self._units_combo.setObjectName("SettingCombo")
        self._units_combo.addItems(UNITS)
        u_layout.addWidget(self._units_combo)
        units_row.addLayout(u_layout)

        dpi_layout = QVBoxLayout()
        dpi_layout.setSpacing(2)
        dpi_label = QLabel("Resolution")
        dpi_label.setObjectName("SettingLabel")
        dpi_layout.addWidget(dpi_label)
        self._dpi_combo = QComboBox()
        self._dpi_combo.setObjectName("SettingCombo")
        self._dpi_combo.setEditable(True)
        for d in DPI_PRESETS:
            self._dpi_combo.addItem(f"{d} DPI", d)
        self._dpi_combo.setCurrentText("72 DPI")
        self._dpi_combo.currentIndexChanged.connect(self._update_preview)
        dpi_layout.addWidget(self._dpi_combo)
        units_row.addLayout(dpi_layout)

        settings_layout.addLayout(units_row)

        # Color mode + profile row
        color_row = QHBoxLayout()
        color_row.setSpacing(10)

        cm_layout = QVBoxLayout()
        cm_layout.setSpacing(2)
        cm_label = QLabel("Color Mode")
        cm_label.setObjectName("SettingLabel")
        cm_layout.addWidget(cm_label)
        self._color_mode_combo = QComboBox()
        self._color_mode_combo.setObjectName("SettingCombo")
        self._color_mode_combo.addItems(COLOR_MODES)
        self._color_mode_combo.currentIndexChanged.connect(self._update_preview)
        cm_layout.addWidget(self._color_mode_combo)
        color_row.addLayout(cm_layout)

        cp_layout = QVBoxLayout()
        cp_layout.setSpacing(2)
        cp_label = QLabel("Color Profile")
        cp_label.setObjectName("SettingLabel")
        cp_layout.addWidget(cp_label)
        self._profile_combo = QComboBox()
        self._profile_combo.setObjectName("SettingCombo")
        self._profile_combo.addItems(COLOR_PROFILES)
        cp_layout.addWidget(self._profile_combo)
        color_row.addLayout(cp_layout)

        settings_layout.addLayout(color_row)

        # Background color swatches
        bg_section = QVBoxLayout()
        bg_section.setSpacing(6)
        bg_label = QLabel("Background")
        bg_label.setObjectName("SettingLabel")
        bg_section.addWidget(bg_label)

        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(8)
        self._bg_group = QButtonGroup(self)
        self._bg_color = QColor(255, 255, 255)
        self._bg_transparent = False

        swatches = [
            ("White", QColor(255, 255, 255), False),
            ("Black", QColor(0, 0, 0), False),
            ("Transparent", QColor(0, 0, 0, 0), True),
        ]

        for label, color, transp in swatches:
            btn = QPushButton()
            btn.setObjectName("BgSwatch")
            btn.setCheckable(True)
            btn.setToolTip(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if transp:
                btn.setStyleSheet(
                    "QPushButton { background: qlineargradient("
                    "x1:0, y1:0, x2:1, y2:1, stop:0 #ccc, stop:0.5 #fff, stop:1 #ccc); }"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {color.name()}; }}"
                )
            self._bg_group.addButton(btn)
            btn.clicked.connect(
                lambda _, c=color, t=transp: self._set_bg(c, t)
            )
            swatch_row.addWidget(btn)
            if label == "White":
                btn.setChecked(True)

        # Custom color
        custom_btn = QPushButton("+")
        custom_btn.setObjectName("BgSwatch")
        custom_btn.setToolTip("Custom color")
        custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        custom_btn.clicked.connect(self._pick_custom_bg)
        swatch_row.addWidget(custom_btn)

        swatch_row.addStretch()
        bg_section.addLayout(swatch_row)
        settings_layout.addLayout(bg_section)

        right.addWidget(settings)

        # Preview
        self._preview = _AspectPreview()
        right.addWidget(self._preview, 1)

        # File size estimate
        self._size_label = QLabel("")
        self._size_label.setObjectName("FileSizeLabel")
        self._size_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self._size_label)

        body.addLayout(right, 2)
        root.addLayout(body, 1)

        # ---- Bottom buttons ----
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("CancelButton")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        create_btn = QPushButton("Create Project")
        create_btn.setObjectName("CreateButton")
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.clicked.connect(self.accept)
        btn_row.addWidget(create_btn)

        root.addLayout(btn_row)

    # ---- Category selection -----------------------------------------------

    def _select_category(self, name: str) -> None:
        # Check the right tab button
        for btn in self._cat_group.buttons():
            if btn.text() == name:
                btn.setChecked(True)
                break

        # Clear preset grid
        while self._preset_grid.count():
            item = self._preset_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        presets = PRESETS.get(name, [])
        if not presets:
            # Custom — show just the dimension inputs
            hint = QLabel("Enter custom dimensions in the settings panel →")
            hint.setObjectName("SettingLabel")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setWordWrap(True)
            self._preset_grid.addWidget(hint, 0, 0, 1, 3)
            return

        cols = 3
        for i, (pname, pw, ph, pdpi) in enumerate(presets):
            card = self._create_preset_card(pname, pw, ph, pdpi)
            self._preset_grid.addWidget(card, i // cols, i % cols)

        # Fill remaining with stretch
        rows = (len(presets) + cols - 1) // cols
        self._preset_grid.setRowStretch(rows, 1)

    def _create_preset_card(self, name: str, w: int, h: int, dpi: int) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("PresetCard")
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(90)
        btn.setMaximumWidth(180)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(btn)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Aspect ratio preview
        preview = _MiniPreview(w, h)
        preview.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(preview, 0, Qt.AlignmentFlag.AlignHCenter)

        pname = QLabel(name)
        pname.setObjectName("PresetName")
        pname.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pname.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(pname)

        size_text = QLabel(f"{w} × {h}")
        size_text.setObjectName("PresetSize")
        size_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        size_text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(size_text)

        btn.clicked.connect(lambda _, pw=w, ph=h, pd=dpi: self._apply_preset(pw, ph, pd))

        return btn

    def _apply_preset(self, w: int, h: int, dpi: int) -> None:
        self._suppress_ratio = True
        self._width_spin.setValue(w)
        self._height_spin.setValue(h)
        self._suppress_ratio = False
        self._aspect_ratio = w / max(h, 1)

        # Set DPI
        for i in range(self._dpi_combo.count()):
            if self._dpi_combo.itemData(i) == dpi:
                self._dpi_combo.setCurrentIndex(i)
                break
        else:
            self._dpi_combo.setCurrentText(f"{dpi} DPI")

        # Auto-detect orientation
        if w >= h:
            self._landscape_btn.setChecked(True)
        else:
            self._portrait_btn.setChecked(True)

        self._update_preview()

    # ---- Dimension handlers ------------------------------------------------

    def _on_width_changed(self, val: int) -> None:
        if self._aspect_locked and not self._suppress_ratio:
            self._suppress_ratio = True
            new_h = max(1, round(val / self._aspect_ratio))
            self._height_spin.setValue(new_h)
            self._suppress_ratio = False
        self._auto_detect_orientation()
        self._update_preview()

    def _on_height_changed(self, val: int) -> None:
        if self._aspect_locked and not self._suppress_ratio:
            self._suppress_ratio = True
            new_w = max(1, round(val * self._aspect_ratio))
            self._width_spin.setValue(new_w)
            self._suppress_ratio = False
        self._auto_detect_orientation()
        self._update_preview()

    def _on_lock_toggled(self, checked: bool) -> None:
        self._aspect_locked = checked
        if checked:
            w = self._width_spin.value()
            h = self._height_spin.value()
            self._aspect_ratio = w / max(h, 1)

    def _auto_detect_orientation(self) -> None:
        w = self._width_spin.value()
        h = self._height_spin.value()
        if w >= h:
            self._landscape_btn.setChecked(True)
        else:
            self._portrait_btn.setChecked(True)

    def _set_orientation(self, orient: str) -> None:
        w = self._width_spin.value()
        h = self._height_spin.value()
        if orient == "landscape" and h > w:
            self._swap_dimensions()
        elif orient == "portrait" and w > h:
            self._swap_dimensions()

    def _swap_dimensions(self) -> None:
        self._suppress_ratio = True
        w = self._width_spin.value()
        h = self._height_spin.value()
        self._width_spin.setValue(h)
        self._height_spin.setValue(w)
        if self._aspect_locked:
            self._aspect_ratio = h / max(w, 1)
        self._suppress_ratio = False
        self._update_preview()

    # ---- Background --------------------------------------------------------

    def _set_bg(self, color: QColor, transparent: bool) -> None:
        self._bg_color = color
        self._bg_transparent = transparent
        self._preview.set_background(color, transparent)

    def _pick_custom_bg(self) -> None:
        color = QColorDialog.getColor(self._bg_color, self, "Background Color")
        if color.isValid():
            self._set_bg(color, False)

    # ---- Preview + file size ------------------------------------------------

    def _update_preview(self) -> None:
        w = self._width_spin.value()
        h = self._height_spin.value()
        self._preview.set_dimensions(w, h)

        # File size estimate
        mode = self._color_mode_combo.currentText()
        channels = _CHANNEL_MAP.get(mode, 3) + 1  # +alpha
        size_bytes = w * h * channels
        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            size_str = f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 ** 3:
            size_str = f"{size_bytes / 1024 ** 2:.1f} MB"
        else:
            size_str = f"{size_bytes / 1024 ** 3:.2f} GB"
        self._size_label.setText(f"Estimated uncompressed: {size_str}")

    # ---- Public API --------------------------------------------------------

    def get_values(self) -> tuple[int, int, int]:
        """Return (width, height, dpi)."""
        dpi = 72
        idx = self._dpi_combo.currentIndex()
        if idx >= 0:
            data = self._dpi_combo.itemData(idx)
            if data is not None:
                dpi = int(data)
            else:
                try:
                    dpi = int(self._dpi_combo.currentText().replace(" DPI", ""))
                except ValueError:
                    dpi = 72
        return self._width_spin.value(), self._height_spin.value(), dpi

    def get_background_color(self) -> tuple[QColor, bool]:
        """Return (color, is_transparent)."""
        return self._bg_color, self._bg_transparent

    def get_color_mode(self) -> str:
        return self._color_mode_combo.currentText()


class _MiniPreview(QWidget):
    """Tiny aspect-ratio preview in preset cards."""

    def __init__(self, w: int, h: int, parent=None) -> None:
        super().__init__(parent)
        self._w = w
        self._h = h
        self.setFixedSize(50, 40)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        area_w = self.width() - 4
        area_h = self.height() - 4
        scale = min(area_w / self._w, area_h / self._h)
        rect_w = max(int(self._w * scale), 4)
        rect_h = max(int(self._h * scale), 4)
        x = (self.width() - rect_w) // 2
        y = (self.height() - rect_h) // 2

        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.setBrush(QColor(255, 255, 255, 20))
        p.drawRoundedRect(x, y, rect_w, rect_h, 2, 2)
        p.end()
