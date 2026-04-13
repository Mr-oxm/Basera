"""New Project dialog — professional template-based project creation.

Features:
* 7 template categories with named presets and aspect-ratio previews
* Custom dimension fields with lock-aspect-ratio toggle
* Portrait / Landscape swap that auto-detects orientation
* Units dropdown (px, in, cm, mm, pt) — live conversion of W/H values
* Resolution / DPI presets (physical-unit aware)
* Color Mode (RGB / CMYK / LAB / Grayscale) + Color Profile
* Background colour swatches (white, black, transparent, custom)
* Live preview box showing aspect ratio and current unit dimensions
* Estimated uncompressed file size calculation
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QDoubleSpinBox, QComboBox,
    QWidget, QScrollArea, QFrame, QButtonGroup,
    QSizePolicy, QColorDialog, QStyleOption,
)

from ..styles import render_qss


# ---------------------------------------------------------------------------
# Template presets: (name, width_px, height_px, dpi)
# ---------------------------------------------------------------------------

PRESETS = {
    "Custom": [],
    "Print": [
        ("A4",         2480,  3508, 300),
        ("A3",         3508,  4961, 300),
        ("A5",         1748,  2480, 300),
        ("Letter",     2550,  3300, 300),
        ("Legal",      2550,  4200, 300),
        ("Tabloid",    3300,  5100, 300),
        ("B5",         2079,  2953, 300),
        ("5 × 7 in",   1500,  2100, 300),
        ("4 × 6 in",   1200,  1800, 300),
    ],
    "Web": [
        ("1920 × 1080",          1920,  1080, 72),
        ("1280 × 720",           1280,   720, 72),
        ("1366 × 768",           1366,   768, 72),
        ("800 × 600",             800,   600, 72),
        ("Banner 728 × 90",       728,    90, 72),
        ("Favicon 64 × 64",        64,    64, 72),
        ("OG Image 1200 × 630",  1200,   630, 72),
    ],
    "Photo": [
        ("Full HD (1920 × 1080)",   1920,  1080,  72),
        ("4K UHD (3840 × 2160)",    3840,  2160,  72),
        ("8K (7680 × 4320)",        7680,  4320,  72),
        ("5 × 7 Print",             1500,  2100, 300),
        ("8 × 10 Print",            2400,  3000, 300),
        ("Square 1:1 (2000)",       2000,  2000,  72),
        ("3:2 (3000 × 2000)",       3000,  2000,  72),
        ("4:3 (2800 × 2100)",       2800,  2100,  72),
    ],
    "Social Media": [
        ("Instagram Post (1080²)",           1080,  1080, 72),
        ("Instagram Story (1080 × 1920)",    1080,  1920, 72),
        ("Facebook Cover (820 × 312)",        820,   312, 72),
        ("Facebook Post (1200 × 630)",       1200,   630, 72),
        ("Twitter Post (1600 × 900)",        1600,   900, 72),
        ("Twitter Header (1500 × 500)",      1500,   500, 72),
        ("LinkedIn Banner (1584 × 396)",     1584,   396, 72),
        ("YouTube Thumbnail (1280 × 720)",   1280,   720, 72),
        ("Pinterest Pin (1000 × 1500)",      1000,  1500, 72),
        ("TikTok (1080 × 1920)",             1080,  1920, 72),
    ],
    "Video": [
        ("1080p (1920 × 1080)",     1920,  1080, 72),
        ("720p (1280 × 720)",       1280,   720, 72),
        ("4K (3840 × 2160)",        3840,  2160, 72),
        ("2K (2560 × 1440)",        2560,  1440, 72),
        ("DCI 4K (4096 × 2160)",    4096,  2160, 72),
        ("Ultrawide (2560 × 1080)", 2560,  1080, 72),
        ("Vertical 9:16 (1080 × 1920)", 1080, 1920, 72),
    ],
    "Art": [
        ("Square Canvas (4000²)",         4000,  4000, 300),
        ("A3 Landscape",                  4961,  3508, 300),
        ("A2 Portrait",                   4961,  7016, 300),
        ("Digital Painting (3000 × 2000)", 3000, 2000, 150),
        ("Pixel Art 64 × 64",               64,    64,  72),
        ("Pixel Art 128 × 128",            128,   128,  72),
        ("Pixel Art 256 × 256",            256,   256,  72),
        ("Icon 512 × 512",                 512,   512,  72),
    ],
}

UNITS = ["px", "in", "cm", "mm", "pt"]

COLOR_MODES = ["RGB", "CMYK", "LAB", "Grayscale"]

# Per-mode: (profile_list, default_profile_index)
_COLOR_PROFILES: dict[str, list[str]] = {
    "RGB": [
        "sRGB IEC61966-2.1",
        "Adobe RGB (1998)",
        "ProPhoto RGB",
        "Display P3",
        "Linear sRGB",
    ],
    "CMYK": [
        "U.S. Web Coated (SWOP) v2",
        "U.S. Sheetfed Coated v2",
        "Europe ISO Coated FOGRA27",
        "Japan Color 2001 Coated",
    ],
    "LAB": [
        "D50 Illuminant",
        "D65 Illuminant",
    ],
    "Grayscale": [
        "Gray Gamma 2.2",
        "Gray Gamma 1.8",
        "Dot Gain 20%",
        "sGray",
    ],
}

DPI_PRESETS = [72, 96, 150, 200, 300, 600, 1200]

# Bytes per channel per color mode (8-bit, no alpha for size estimate)
_CHANNEL_MAP = {"RGB": 3, "CMYK": 4, "LAB": 3, "Grayscale": 1}


# ---------------------------------------------------------------------------
# Unit conversion helpers
# ---------------------------------------------------------------------------

def px_per_unit(unit: str, dpi: int) -> float:
    """Return how many document pixels correspond to one unit."""
    if unit == "px":
        return 1.0
    if unit == "in":
        return float(dpi)
    if unit == "cm":
        return dpi / 2.54
    if unit == "mm":
        return dpi / 25.4
    if unit == "pt":
        return dpi / 72.0
    return 1.0


def _spinbox_config(unit: str) -> tuple[float, float, int, float]:
    """Return (min, max, decimals, step) for a dimension spinbox in *unit*."""
    if unit == "px":
        return 1.0, 30000.0, 0, 1.0
    if unit == "in":
        return 0.01, 200.0, 3, 0.01
    if unit == "cm":
        return 0.01, 500.0, 2, 0.1
    if unit == "mm":
        return 0.1, 5000.0, 1, 1.0
    if unit == "pt":
        return 1.0, 100000.0, 1, 1.0
    return 1.0, 30000.0, 0, 1.0


# ---------------------------------------------------------------------------
# Transparent / checkerboard swatch button
# ---------------------------------------------------------------------------

class _TransparentSwatch(QPushButton):
    """Swatch button that paints a proper checkerboard pattern for transparency."""

    _LIGHT = QColor(220, 220, 220)
    _DARK  = QColor(170, 170, 170)
    _CHECK_COLOR = QColor(74, 179, 255)   # accent highlight when selected

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setObjectName("BgSwatch")
        self.setToolTip("Transparent")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cell = max(4, min(w, h) // 4)

        # Checkerboard fill
        for row in range(h // cell + 1):
            for col in range(w // cell + 1):
                c = self._LIGHT if (row + col) % 2 == 0 else self._DARK
                x0, y0 = col * cell, row * cell
                cw = min(cell, w - x0)
                ch = min(cell, h - y0)
                if cw > 0 and ch > 0:
                    p.fillRect(x0, y0, cw, ch, c)

        # Hover overlay
        if self.underMouse():
            p.fillRect(0, 0, w, h, QColor(255, 255, 255, 40))

        # Checked / selected border
        pen_width = 2 if self.isChecked() else 1
        pen_color = self._CHECK_COLOR if self.isChecked() else QColor(100, 100, 100, 120)
        p.setPen(QPen(pen_color, pen_width))
        p.setBrush(Qt.BrushStyle.NoBrush)
        half = pen_width / 2
        p.drawRoundedRect(
            QRect(int(half), int(half), w - pen_width, h - pen_width),
            3, 3,
        )
        p.end()


# ---------------------------------------------------------------------------
# Live aspect-ratio preview widget
# ---------------------------------------------------------------------------

class _AspectPreview(QWidget):
    """Live aspect-ratio preview with background color and dimension label."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("LivePreview")
        self.setMinimumSize(180, 140)
        self._w = 1920
        self._h = 1080
        self._bg_color = QColor(255, 255, 255)
        self._transparent = False
        self._label = "1920 × 1080 px"

    def set_dimensions(self, w: int, h: int, label: str = "") -> None:
        self._w = max(w, 1)
        self._h = max(h, 1)
        self._label = label if label else f"{w} × {h} px"
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

        scale = min(area_w / self._w, area_h / self._h)
        rect_w = int(self._w * scale)
        rect_h = int(self._h * scale)
        x = (self.width() - rect_w) // 2
        y = (self.height() - rect_h) // 2

        # Drop shadow
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 30))
        p.drawRoundedRect(x + 3, y + 3, rect_w, rect_h, 4, 4)

        # Background fill
        if self._transparent:
            checker = 8
            for cy in range(y, y + rect_h, checker):
                for cx in range(x, x + rect_w, checker):
                    row = (cy - y) // checker
                    col = (cx - x) // checker
                    c = QColor(200, 200, 200) if (row + col) % 2 == 0 else QColor(160, 160, 160)
                    p.setBrush(c)
                    cw = min(checker, x + rect_w - cx)
                    ch = min(checker, y + rect_h - cy)
                    p.drawRect(cx, cy, cw, ch)
        else:
            p.setBrush(self._bg_color)
            p.drawRoundedRect(x, y, rect_w, rect_h, 4, 4)

        # Border
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.drawRoundedRect(x, y, rect_w, rect_h, 4, 4)

        # Dimension label below preview
        p.setPen(QColor(180, 180, 180))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(x, y + rect_h + 14, self._label)

        p.end()


# ---------------------------------------------------------------------------
# Tiny preset card preview
# ---------------------------------------------------------------------------

class _MiniPreview(QWidget):
    """Aspect-ratio thumbnail shown inside a preset card."""

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


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class NewProjectDialog(QDialog):
    """Professional New Project dialog with templates, unit conversion, color settings, and preview."""

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
        self._aspect_ratio_px = 1920 / 1080  # always stored in pixel space
        self._suppress_change = False        # guards all cross-signal loops

        # Internal pixel dimensions (source of truth)
        self._width_px = 1920.0
        self._height_px = 1080.0
        self._current_unit = "px"
        self._current_dpi = 72

        # Exclusive group for preset cards — recreated on every category switch
        self._preset_group = QButtonGroup(self)
        self._preset_group.setExclusive(True)

        self._build_ui()
        self._apply_theme()
        self._select_category("Photo")
        self._update_preview()

    # ---- Theme ---------------------------------------------------------------

    def _apply_theme(self) -> None:
        from ..theme import ThemeManager
        palette = ThemeManager.instance().active_palette
        self.setStyleSheet(render_qss("new_project_dialog.qss", palette))

    # ---- UI construction ----------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        title = QLabel("New Project")
        title.setObjectName("DialogTitle")
        root.addWidget(title)

        body = QHBoxLayout()
        body.setSpacing(16)

        # ---- Left: category tabs + preset grid ----
        left = QVBoxLayout()
        left.setSpacing(10)

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

        # ---- Right: settings + preview ----
        right = QVBoxLayout()
        right.setSpacing(12)

        settings = QWidget()
        settings.setObjectName("SettingsPanel")
        settings_layout = QVBoxLayout(settings)
        settings_layout.setContentsMargins(16, 14, 16, 14)
        settings_layout.setSpacing(10)

        # --- Dimensions section ---
        dim_title = QLabel("DIMENSIONS")
        dim_title.setObjectName("SettingLabel")
        dim_title.setStyleSheet("font-size: 10px; font-weight: 700; letter-spacing: 0.06em;")
        settings_layout.addWidget(dim_title)

        dim_row = QHBoxLayout()
        dim_row.setSpacing(8)

        w_col = QVBoxLayout()
        w_col.setSpacing(2)
        w_col.addWidget(self._make_dim_label("W"))
        self._width_spin = QDoubleSpinBox()
        self._width_spin.setObjectName("DimInput")
        self._width_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._width_spin.valueChanged.connect(self._on_width_changed)
        w_col.addWidget(self._width_spin)
        dim_row.addLayout(w_col)

        self._link_btn = QPushButton("🔗")
        self._link_btn.setObjectName("LinkButton")
        self._link_btn.setCheckable(True)
        self._link_btn.setToolTip("Lock aspect ratio")
        self._link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._link_btn.toggled.connect(self._on_lock_toggled)
        dim_row.addWidget(self._link_btn, 0, Qt.AlignmentFlag.AlignBottom)

        h_col = QVBoxLayout()
        h_col.setSpacing(2)
        h_col.addWidget(self._make_dim_label("H"))
        self._height_spin = QDoubleSpinBox()
        self._height_spin.setObjectName("DimInput")
        self._height_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._height_spin.valueChanged.connect(self._on_height_changed)
        h_col.addWidget(self._height_spin)
        dim_row.addLayout(h_col)

        settings_layout.addLayout(dim_row)

        # Orientation toggle
        orient_row = QHBoxLayout()
        orient_row.setSpacing(6)
        self._orient_group = QButtonGroup(self)

        self._landscape_btn = QPushButton("▭  Landscape")
        self._landscape_btn.setObjectName("OrientationButton")
        self._landscape_btn.setCheckable(True)
        self._landscape_btn.setChecked(True)
        self._landscape_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._orient_group.addButton(self._landscape_btn)
        self._landscape_btn.clicked.connect(lambda: self._set_orientation("landscape"))
        orient_row.addWidget(self._landscape_btn)

        self._portrait_btn = QPushButton("▯  Portrait")
        self._portrait_btn.setObjectName("OrientationButton")
        self._portrait_btn.setCheckable(True)
        self._portrait_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._orient_group.addButton(self._portrait_btn)
        self._portrait_btn.clicked.connect(lambda: self._set_orientation("portrait"))
        orient_row.addWidget(self._portrait_btn)

        orient_row.addStretch()
        settings_layout.addLayout(orient_row)

        # --- Units + DPI row ---
        units_row = QHBoxLayout()
        units_row.setSpacing(10)

        u_col = QVBoxLayout()
        u_col.setSpacing(2)
        u_col.addWidget(self._make_setting_label("Units"))
        self._units_combo = QComboBox()
        self._units_combo.setObjectName("SettingCombo")
        self._units_combo.addItems(UNITS)
        self._units_combo.currentIndexChanged.connect(self._on_unit_changed)
        u_col.addWidget(self._units_combo)
        units_row.addLayout(u_col)

        dpi_col = QVBoxLayout()
        dpi_col.setSpacing(2)
        dpi_col.addWidget(self._make_setting_label("Resolution"))
        self._dpi_combo = QComboBox()
        self._dpi_combo.setObjectName("SettingCombo")
        self._dpi_combo.setEditable(True)
        for d in DPI_PRESETS:
            self._dpi_combo.addItem(f"{d} DPI", d)
        self._dpi_combo.setCurrentText("72 DPI")
        self._dpi_combo.currentIndexChanged.connect(self._on_dpi_changed)
        self._dpi_combo.lineEdit().editingFinished.connect(self._on_dpi_edited)
        dpi_col.addWidget(self._dpi_combo)
        units_row.addLayout(dpi_col)

        settings_layout.addLayout(units_row)

        # --- Color mode + profile row ---
        color_row = QHBoxLayout()
        color_row.setSpacing(10)

        cm_col = QVBoxLayout()
        cm_col.setSpacing(2)
        cm_col.addWidget(self._make_setting_label("Color Mode"))
        self._color_mode_combo = QComboBox()
        self._color_mode_combo.setObjectName("SettingCombo")
        self._color_mode_combo.addItems(COLOR_MODES)
        self._color_mode_combo.currentTextChanged.connect(self._on_color_mode_changed)
        cm_col.addWidget(self._color_mode_combo)
        color_row.addLayout(cm_col)

        cp_col = QVBoxLayout()
        cp_col.setSpacing(2)
        cp_col.addWidget(self._make_setting_label("Color Profile"))
        self._profile_combo = QComboBox()
        self._profile_combo.setObjectName("SettingCombo")
        cp_col.addWidget(self._profile_combo)
        color_row.addLayout(cp_col)

        settings_layout.addLayout(color_row)

        # --- Background swatches ---
        bg_col = QVBoxLayout()
        bg_col.setSpacing(6)
        bg_col.addWidget(self._make_setting_label("Background"))

        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(8)
        self._bg_group = QButtonGroup(self)
        self._bg_color = QColor(255, 255, 255)
        self._bg_transparent = False

        for label, color, transp in [
            ("White",       QColor(255, 255, 255), False),
            ("Black",       QColor(0, 0, 0),       False),
            ("Transparent", QColor(0, 0, 0, 0),    True),
        ]:
            if transp:
                btn = _TransparentSwatch()
            else:
                btn = QPushButton()
                btn.setObjectName("BgSwatch")
                btn.setCheckable(True)
                btn.setToolTip(label)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(f"QPushButton {{ background: {color.name()}; }}")
            self._bg_group.addButton(btn)
            btn.clicked.connect(lambda _, c=color, t=transp: self._set_bg(c, t))
            swatch_row.addWidget(btn)
            if label == "White":
                btn.setChecked(True)

        custom_btn = QPushButton("+")
        custom_btn.setObjectName("BgSwatch")
        custom_btn.setToolTip("Custom color")
        custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        custom_btn.clicked.connect(self._pick_custom_bg)
        swatch_row.addWidget(custom_btn)
        swatch_row.addStretch()

        bg_col.addLayout(swatch_row)
        settings_layout.addLayout(bg_col)

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

        # --- Bottom buttons ---
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("CancelButton")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._create_btn = QPushButton("Create Project")
        self._create_btn.setObjectName("CreateButton")
        self._create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._create_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._create_btn)

        root.addLayout(btn_row)

        # Initialise spinbox ranges/decimals and populate profile list
        self._configure_spinboxes("px")
        self._on_color_mode_changed("RGB")
        self._sync_spinboxes_from_px()

    # ---- Small label factories ----------------------------------------------

    @staticmethod
    def _make_dim_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("DimLabel")
        return lbl

    @staticmethod
    def _make_setting_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("SettingLabel")
        return lbl

    # ---- Category selection -------------------------------------------------

    def _select_category(self, name: str) -> None:
        for btn in self._cat_group.buttons():
            if btn.text() == name:
                btn.setChecked(True)
                break

        # Clear old preset cards
        while self._preset_grid.count():
            item = self._preset_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Reset the exclusive preset group (old buttons are being destroyed)
        for b in list(self._preset_group.buttons()):
            self._preset_group.removeButton(b)

        presets = PRESETS.get(name, [])
        if not presets:
            hint = QLabel("Enter custom dimensions in the settings panel →")
            hint.setObjectName("SettingLabel")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setWordWrap(True)
            self._preset_grid.addWidget(hint, 0, 0, 1, 3)
            return

        cols = 3
        for i, (pname, pw, ph, pdpi) in enumerate(presets):
            card = self._make_preset_card(pname, pw, ph, pdpi)
            self._preset_group.addButton(card)
            self._preset_grid.addWidget(card, i // cols, i % cols)

        rows = (len(presets) + cols - 1) // cols
        self._preset_grid.setRowStretch(rows, 1)

    def _make_preset_card(self, name: str, w: int, h: int, dpi: int) -> QPushButton:
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

        preview = _MiniPreview(w, h)
        preview.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(preview, 0, Qt.AlignmentFlag.AlignHCenter)

        name_lbl = QLabel(name)
        name_lbl.setObjectName("PresetName")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(name_lbl)

        size_lbl = QLabel(f"{w} × {h}")
        size_lbl.setObjectName("PresetSize")
        size_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        size_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(size_lbl)

        btn.clicked.connect(lambda _, pw=w, ph=h, pd=dpi: self._apply_preset(pw, ph, pd))
        return btn

    def _apply_preset(self, w: int, h: int, dpi: int) -> None:
        """Apply a preset — sets DPI first, then converts w/h to current unit."""
        self._suppress_change = True
        try:
            # Set DPI
            self._set_dpi(dpi)
            # Store pixel dimensions
            self._width_px = float(w)
            self._height_px = float(h)
            self._aspect_ratio_px = w / max(h, 1.0)
            # Update spinboxes in current unit
            self._sync_spinboxes_from_px()
            # Auto-detect orientation
            self._update_orientation_buttons()
        finally:
            self._suppress_change = False
        self._update_preview()

    # ---- Dimension spinbox handlers -----------------------------------------

    def _on_width_changed(self, val: float) -> None:
        if self._suppress_change:
            return
        ppu = px_per_unit(self._current_unit, self._current_dpi)
        self._width_px = max(1.0, val * ppu)
        if self._aspect_locked:
            self._suppress_change = True
            new_h_px = self._width_px / max(self._aspect_ratio_px, 1e-9)
            self._height_px = max(1.0, new_h_px)
            new_h_unit = self._height_px / ppu
            self._height_spin.setValue(new_h_unit)
            self._suppress_change = False
        self._update_orientation_buttons()
        self._update_preview()

    def _on_height_changed(self, val: float) -> None:
        if self._suppress_change:
            return
        ppu = px_per_unit(self._current_unit, self._current_dpi)
        self._height_px = max(1.0, val * ppu)
        if self._aspect_locked:
            self._suppress_change = True
            new_w_px = self._height_px * self._aspect_ratio_px
            self._width_px = max(1.0, new_w_px)
            new_w_unit = self._width_px / ppu
            self._width_spin.setValue(new_w_unit)
            self._suppress_change = False
        self._update_orientation_buttons()
        self._update_preview()

    def _on_lock_toggled(self, checked: bool) -> None:
        self._aspect_locked = checked
        if checked:
            self._aspect_ratio_px = self._width_px / max(self._height_px, 1.0)

    # ---- Unit handling -------------------------------------------------------

    def _on_unit_changed(self, idx: int) -> None:
        new_unit = UNITS[idx]
        if new_unit == self._current_unit:
            return
        self._current_unit = new_unit
        self._suppress_change = True
        try:
            self._configure_spinboxes(new_unit)
            self._sync_spinboxes_from_px()
        finally:
            self._suppress_change = False
        self._update_preview()

    def _configure_spinboxes(self, unit: str) -> None:
        mn, mx, dec, step = _spinbox_config(unit)
        for spin in (self._width_spin, self._height_spin):
            spin.setDecimals(dec)
            spin.setSingleStep(step)
            spin.setRange(mn, mx)

    def _sync_spinboxes_from_px(self) -> None:
        """Push internal pixel values to spinboxes in current unit."""
        ppu = px_per_unit(self._current_unit, self._current_dpi)
        self._suppress_change = True
        try:
            self._width_spin.setValue(self._width_px / ppu)
            self._height_spin.setValue(self._height_px / ppu)
        finally:
            self._suppress_change = False

    # ---- DPI handling -------------------------------------------------------

    def _get_dpi_from_combo(self) -> int:
        idx = self._dpi_combo.currentIndex()
        if idx >= 0:
            data = self._dpi_combo.itemData(idx)
            if data is not None:
                return int(data)
        try:
            return max(1, int(self._dpi_combo.currentText().replace(" DPI", "").strip()))
        except ValueError:
            return 72

    def _set_dpi(self, dpi: int) -> None:
        """Set the DPI combo to the given value without triggering double-updates."""
        for i in range(self._dpi_combo.count()):
            if self._dpi_combo.itemData(i) == dpi:
                self._dpi_combo.setCurrentIndex(i)
                return
        self._dpi_combo.setCurrentText(f"{dpi} DPI")

    def _on_dpi_changed(self, _idx: int) -> None:
        """DPI preset changed — physical size stays constant; pixel count updates."""
        new_dpi = self._get_dpi_from_combo()
        if new_dpi == self._current_dpi:
            return
        self._apply_dpi_change(new_dpi)

    def _on_dpi_edited(self) -> None:
        """User typed a custom DPI value — same physical-size-stable logic."""
        new_dpi = self._get_dpi_from_combo()
        if new_dpi != self._current_dpi:
            self._apply_dpi_change(new_dpi)

    def _apply_dpi_change(self, new_dpi: int) -> None:
        """Core DPI change handler.

        For physical units (in / cm / mm / pt) the displayed value (e.g. 10.0 in)
        is kept constant and the internal pixel store is recalculated so that
        ``get_values()`` returns a higher pixel count at the new DPI.
        For pixels the spinbox value is already in pixels and does not change.
        """
        if self._current_unit != "px":
            # Physical size stays the same; update the pixel backing store.
            new_ppu = px_per_unit(self._current_unit, new_dpi)
            self._suppress_change = True
            self._width_px = max(1.0, self._width_spin.value() * new_ppu)
            self._height_px = max(1.0, self._height_spin.value() * new_ppu)
            self._suppress_change = False
        self._current_dpi = new_dpi
        self._update_preview()

    # ---- Orientation --------------------------------------------------------

    def _update_orientation_buttons(self) -> None:
        if self._width_px >= self._height_px:
            self._landscape_btn.setChecked(True)
        else:
            self._portrait_btn.setChecked(True)

    def _set_orientation(self, orient: str) -> None:
        if orient == "landscape" and self._height_px > self._width_px:
            self._swap_dimensions()
        elif orient == "portrait" and self._width_px > self._height_px:
            self._swap_dimensions()

    def _swap_dimensions(self) -> None:
        self._width_px, self._height_px = self._height_px, self._width_px
        if self._aspect_locked:
            self._aspect_ratio_px = self._height_px / max(self._width_px, 1.0)
        self._sync_spinboxes_from_px()
        self._update_preview()

    # ---- Color mode → profile list ------------------------------------------

    def _on_color_mode_changed(self, mode: str) -> None:
        profiles = _COLOR_PROFILES.get(mode, ["Default"])
        self._profile_combo.clear()
        self._profile_combo.addItems(profiles)
        self._update_preview()

    # ---- Background ---------------------------------------------------------

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
        w_px = max(1, round(self._width_px))
        h_px = max(1, round(self._height_px))
        self._preview.set_dimensions(w_px, h_px, label=self._dimension_label())

        mode = self._color_mode_combo.currentText()
        channels = _CHANNEL_MAP.get(mode, 3) + 1  # +1 for alpha channel
        size_bytes = w_px * h_px * channels
        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            size_str = f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 ** 3:
            size_str = f"{size_bytes / 1024 ** 2:.1f} MB"
        else:
            size_str = f"{size_bytes / 1024 ** 3:.2f} GB"
        self._size_label.setText(f"Estimated uncompressed: {size_str}")

    def _dimension_label(self) -> str:
        """Human-readable dimension string in the current unit."""
        unit = self._current_unit
        ppu = px_per_unit(unit, self._current_dpi)
        w_u = self._width_px / ppu
        h_u = self._height_px / ppu
        if unit == "px":
            return f"{int(round(w_u))} × {int(round(h_u))} px"
        dec = _spinbox_config(unit)[2]
        fmt = f".{dec}f"
        return f"{w_u:{fmt}} × {h_u:{fmt}} {unit}  ({int(round(self._width_px))} × {int(round(self._height_px))} px)"

    # ---- Public API ---------------------------------------------------------

    def get_values(self) -> tuple[int, int, int]:
        """Return (width_px, height_px, dpi) — always in pixels."""
        return (
            max(1, round(self._width_px)),
            max(1, round(self._height_px)),
            self._current_dpi,
        )

    def get_color_mode(self) -> str:
        """Return the selected color mode (e.g. 'RGB', 'CMYK')."""
        return self._color_mode_combo.currentText()

    def get_color_profile(self) -> str:
        """Return the selected color profile (e.g. 'sRGB IEC61966-2.1')."""
        return self._profile_combo.currentText()

    def get_unit(self) -> str:
        """Return the display unit selected by the user (e.g. 'px', 'cm')."""
        return self._current_unit

    def get_background_color(self) -> tuple[QColor, bool]:
        """Return (color, is_transparent)."""
        return self._bg_color, self._bg_transparent

    def set_from_document(self, doc: object) -> None:
        """Pre-populate every setting from an existing document object.

        Accepts any object with ``width``, ``height``, ``dpi``, ``unit``,
        ``color_mode``, and ``color_profile`` attributes (all optional).
        Useful for "Edit Document Settings" flows.
        """
        self._width_px = float(getattr(doc, "width", self._width_px))
        self._height_px = float(getattr(doc, "height", self._height_px))
        self._aspect_ratio_px = self._width_px / max(self._height_px, 1.0)

        # DPI
        new_dpi = int(getattr(doc, "dpi", self._current_dpi))
        self._current_dpi = new_dpi
        self._set_dpi(new_dpi)

        # Unit — set before syncing spinboxes
        unit = getattr(doc, "unit", "px")
        if unit in UNITS:
            self._suppress_change = True
            self._current_unit = unit
            self._configure_spinboxes(unit)
            self._units_combo.setCurrentIndex(UNITS.index(unit))
            self._suppress_change = False

        # Color mode (also repopulates profile list via signal)
        mode = getattr(doc, "color_mode", "RGB")
        if mode in COLOR_MODES:
            self._color_mode_combo.setCurrentText(mode)

        # Color profile — find after mode has been set (profile list updated)
        profile = getattr(doc, "color_profile", "")
        idx_p = self._profile_combo.findText(profile)
        if idx_p >= 0:
            self._profile_combo.setCurrentIndex(idx_p)

        self._sync_spinboxes_from_px()
        self._update_orientation_buttons()
        self._update_preview()
