"""Export dialog — multi-format export with quality, size, and metadata controls.

Supported formats: JPEG, PNG, WEBP, AVIF, TIFF, BMP, PSD, HEIC, SVG, PDF, .basera
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QDoubleSpinBox, QComboBox,
    QCheckBox, QWidget, QScrollArea, QFrame,
    QButtonGroup, QFileDialog,
)

from ..styles import render_qss
from ...utils.image_io import can_save_extension


# ---------------------------------------------------------------------------
# Format definitions
# ---------------------------------------------------------------------------

ALL_FORMATS = [
    {"ext": "jpeg",   "name": "JPEG",    "lossy": True,  "desc": "Joint Photographic Experts Group"},
    {"ext": "png",    "name": "PNG",     "lossy": False, "desc": "Portable Network Graphics"},
    {"ext": "webp",   "name": "WEBP",    "lossy": True,  "desc": "Web Picture format"},
    {"ext": "avif",   "name": "AVIF",    "lossy": True,  "desc": "AV1 Image File Format"},
    {"ext": "tiff",   "name": "TIFF",    "lossy": False, "desc": "Tagged Image File Format"},
    {"ext": "bmp",    "name": "BMP",     "lossy": False, "desc": "Bitmap Image"},
    {"ext": "psd",    "name": "PSD",     "lossy": False, "desc": "Adobe Photoshop Document"},
    {"ext": "heic",   "name": "HEIC",    "lossy": True,  "desc": "High Efficiency Image Container"},
    {"ext": "svg",    "name": "SVG",     "lossy": False, "desc": "Scalable Vector Graphics"},
    {"ext": "pdf",    "name": "PDF",     "lossy": False, "desc": "Portable Document Format"},
    {"ext": "basera", "name": ".basera", "lossy": False, "desc": "Basera Project File"},
]

SIZE_PRESETS = [
    ("0.25×", 0.25),
    ("0.5×",  0.50),
    ("0.75×", 0.75),
    ("1× (Original)", 1.0),
    ("1.5×",  1.50),
    ("2×",    2.00),
    ("3×",    3.00),
    ("4×",    4.00),
]

SUBSAMPLING_OPTIONS = ["4:4:4 (Best)", "4:2:2", "4:2:0 (Smallest)"]

EXPORT_UNITS = ["px", "in", "cm", "mm", "pt"]
DPI_PRESETS  = [72, 96, 150, 200, 300, 600, 1200]

# Formats that flatten transparency onto a solid background colour
_FLAT_FORMATS = {"jpeg", "bmp", "pdf"}


# ---------------------------------------------------------------------------
# Unit conversion helpers  (mirrored from new_project_dialog)
# ---------------------------------------------------------------------------

def _px_per_unit(unit: str, dpi: int) -> float:
    if unit == "px": return 1.0
    if unit == "in": return float(dpi)
    if unit == "cm": return dpi / 2.54
    if unit == "mm": return dpi / 25.4
    if unit == "pt": return dpi / 72.0
    return 1.0


def _spinbox_cfg(unit: str) -> tuple[float, float, int, float]:
    """Return (min, max, decimals, step) for a dimension spinbox."""
    if unit == "px": return 1.0,      32000.0, 0, 1.0
    if unit == "in": return 0.01,       400.0, 3, 0.01
    if unit == "cm": return 0.01,      1000.0, 2, 0.1
    if unit == "mm": return 0.1,      10000.0, 1, 1.0
    if unit == "pt": return 1.0,     100000.0, 1, 1.0
    return 1.0, 32000.0, 0, 1.0


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class ExportDialog(QDialog):
    """Multi-format export dialog with quality, sizing, and metadata controls."""

    def __init__(self, parent=None, document=None) -> None:
        super().__init__(parent)
        self.setObjectName("ExportDialog")
        self.setWindowTitle("Export")
        self.setMinimumSize(700, 560)
        self.resize(780, 620)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        self._doc = document

        # --- pixel-space source of truth ---
        self._orig_w: int   = document.width  if document else 1920
        self._orig_h: int   = document.height if document else 1080
        self._width_px:  float = float(self._orig_w)
        self._height_px: float = float(self._orig_h)
        self._aspect_ratio_px: float = self._orig_w / max(self._orig_h, 1.0)
        self._aspect_locked: bool = True
        self._suppress_change: bool = False

        # unit / dpi state – default from document if available
        doc_unit = getattr(document, "unit", "px") if document else "px"
        self._current_unit: str = doc_unit if doc_unit in EXPORT_UNITS else "px"
        self._current_dpi:  int = int(getattr(document, "dpi", 72)) if document else 72

        # jpeg/bmp/pdf background colour
        self._jpeg_bg_color: QColor = QColor(255, 255, 255)

        self._formats = [f for f in ALL_FORMATS if can_save_extension(f".{f['ext']}")]
        if not self._formats:
            self._formats = [{"ext": "png", "name": "PNG", "lossy": False,
                              "desc": "Portable Network Graphics"}]
        self._selected_format = self._formats[0]

        self._build_ui()
        self._apply_theme()
        self._select_format(self._formats[0])

    def _apply_theme(self) -> None:
        from ..theme import ThemeManager
        palette = ThemeManager.instance().active_palette
        self.setStyleSheet(render_qss("export_dialog.qss", palette))

    # =========================================================================
    # UI construction
    # =========================================================================

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        title = QLabel("Export")
        title.setObjectName("ExportTitle")
        root.addWidget(title)

        body = QHBoxLayout()
        body.setSpacing(16)

        # ---- Left: format list ----
        left = QVBoxLayout()
        left.setSpacing(6)

        fmt_hdr = QLabel("FORMAT")
        fmt_hdr.setObjectName("ExportSectionHeader")
        left.addWidget(fmt_hdr)

        fmt_scroll = QScrollArea()
        fmt_scroll.setWidgetResizable(True)
        fmt_scroll.setFrameShape(QFrame.Shape.NoFrame)
        fmt_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        fmt_scroll.setObjectName("FormatScrollArea")

        fmt_container = QWidget()
        fmt_container.setObjectName("FormatScrollContainer")
        fmt_layout = QVBoxLayout(fmt_container)
        fmt_layout.setSpacing(4)
        fmt_layout.setContentsMargins(0, 0, 0, 0)

        self._fmt_group = QButtonGroup(self)
        self._fmt_group.setExclusive(True)

        for fmt in self._formats:
            btn = QPushButton(f"  {fmt['name']}")
            btn.setObjectName("FormatCard")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(fmt["desc"])
            self._fmt_group.addButton(btn)
            btn.clicked.connect(lambda _, f=fmt: self._select_format(f))
            fmt_layout.addWidget(btn)

        fmt_layout.addStretch()
        fmt_scroll.setWidget(fmt_container)
        left.addWidget(fmt_scroll, 1)

        body.addLayout(left, 1)

        # ---- Right: settings panel ----
        settings = QWidget()
        settings.setObjectName("ExportSettingsPanel")
        self._settings_layout = QVBoxLayout(settings)
        self._settings_layout.setContentsMargins(14, 10, 14, 10)
        self._settings_layout.setSpacing(7)

        self._quality_section   = self._build_quality_section()
        self._settings_layout.addWidget(self._quality_section)

        self._subsample_section = self._build_subsample_section()
        self._settings_layout.addWidget(self._subsample_section)

        self._bg_color_section  = self._build_bg_color_section()
        self._settings_layout.addWidget(self._bg_color_section)

        div = QFrame()
        div.setObjectName("ExportDivider")
        div.setFrameShape(QFrame.Shape.HLine)
        self._settings_layout.addWidget(div)

        self._build_dimensions_section(self._settings_layout)

        div2 = QFrame()
        div2.setObjectName("ExportDivider")
        div2.setFrameShape(QFrame.Shape.HLine)
        self._settings_layout.addWidget(div2)

        self._build_metadata_section(self._settings_layout)

        self._size_estimate = QLabel("")
        self._size_estimate.setObjectName("ExportSizeEstimate")
        self._size_estimate.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._settings_layout.addWidget(self._size_estimate)

        self._settings_layout.addStretch()
        body.addWidget(settings, 2)
        root.addLayout(body, 1)

        # ---- Bottom buttons ----
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("ExportCancelButton")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        clipboard_btn = QPushButton("Copy to Clipboard")
        clipboard_btn.setObjectName("ClipboardButton")
        clipboard_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clipboard_btn.clicked.connect(self._on_copy_clipboard)
        btn_row.addWidget(clipboard_btn)

        export_btn = QPushButton("Export")
        export_btn.setObjectName("ExportButton")
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.clicked.connect(self._on_export)
        btn_row.addWidget(export_btn)

        root.addLayout(btn_row)

        # Initialise dimension spinboxes for the starting unit
        self._configure_spinboxes(self._current_unit)
        self._sync_spinboxes_from_px()

    # =========================================================================
    # Section builders
    # =========================================================================

    def _build_quality_section(self) -> QWidget:
        w = QWidget()
        w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QHBoxLayout()
        lbl = QLabel("Quality")
        lbl.setObjectName("ExportSettingLabel")
        header.addWidget(lbl)
        self._quality_value = QLabel("85%")
        self._quality_value.setObjectName("QualityValue")
        header.addWidget(self._quality_value)
        header.addStretch()
        layout.addLayout(header)

        self._quality_slider = QSlider(Qt.Orientation.Horizontal)
        self._quality_slider.setObjectName("QualitySlider")
        self._quality_slider.setRange(1, 100)
        self._quality_slider.setValue(85)
        self._quality_slider.valueChanged.connect(
            lambda v: (self._quality_value.setText(f"{v}%"), self._update_size_estimate())
        )
        layout.addWidget(self._quality_slider)
        return w

    def _build_subsample_section(self) -> QWidget:
        w = QWidget()
        w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        lbl = QLabel("Chroma Subsampling")
        lbl.setObjectName("ExportSettingLabel")
        layout.addWidget(lbl)

        self._subsample_combo = QComboBox()
        self._subsample_combo.setObjectName("SettingCombo")
        self._subsample_combo.addItems(SUBSAMPLING_OPTIONS)
        layout.addWidget(self._subsample_combo)
        return w

    def _build_bg_color_section(self) -> QWidget:
        w = QWidget()
        w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        lbl = QLabel("Background Color")
        lbl.setObjectName("ExportSettingLabel")
        layout.addWidget(lbl)

        row = QHBoxLayout()
        row.setSpacing(8)

        self._jpeg_bg_swatch = QFrame()
        self._jpeg_bg_swatch.setObjectName("BgColorSwatch")
        self._jpeg_bg_swatch.setFixedSize(22, 22)
        row.addWidget(self._jpeg_bg_swatch)

        pick_btn = QPushButton("Pick Color…")
        pick_btn.setObjectName("BgColorPickButton")
        pick_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pick_btn.clicked.connect(self._on_pick_bg_color)
        row.addWidget(pick_btn)

        hint = QLabel("Used for transparent areas")
        hint.setObjectName("ExportHint")
        row.addWidget(hint, 1)

        layout.addLayout(row)
        self._update_bg_swatch()
        return w

    def _build_dimensions_section(self, parent_layout: QVBoxLayout) -> None:
        # Section header
        lbl = QLabel("Dimensions")
        lbl.setObjectName("ExportSettingLabel")
        parent_layout.addWidget(lbl)

        # ---- W  🔗  H ----
        dim_row = QHBoxLayout()
        dim_row.setSpacing(6)

        w_col = QVBoxLayout()
        w_col.setSpacing(2)
        w_lbl = QLabel("W")
        w_lbl.setObjectName("DimLabel")
        w_col.addWidget(w_lbl)
        self._width_spin = QDoubleSpinBox()
        self._width_spin.setObjectName("DimInput")
        self._width_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._width_spin.valueChanged.connect(self._on_w_changed)
        w_col.addWidget(self._width_spin)
        dim_row.addLayout(w_col)

        self._link_btn = QPushButton("🔗")
        self._link_btn.setObjectName("LinkButton")
        self._link_btn.setCheckable(True)
        self._link_btn.setChecked(True)
        self._link_btn.setToolTip("Lock aspect ratio")
        self._link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._link_btn.toggled.connect(self._on_lock_toggled)
        dim_row.addWidget(self._link_btn, 0, Qt.AlignmentFlag.AlignBottom)

        h_col = QVBoxLayout()
        h_col.setSpacing(2)
        h_lbl = QLabel("H")
        h_lbl.setObjectName("DimLabel")
        h_col.addWidget(h_lbl)
        self._height_spin = QDoubleSpinBox()
        self._height_spin.setObjectName("DimInput")
        self._height_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._height_spin.valueChanged.connect(self._on_h_changed)
        h_col.addWidget(self._height_spin)
        dim_row.addLayout(h_col)

        parent_layout.addLayout(dim_row)

        # ---- Units + Resolution ----
        units_row = QHBoxLayout()
        units_row.setSpacing(8)

        u_col = QVBoxLayout()
        u_col.setSpacing(2)
        u_col.addWidget(self._make_sub_label("Units"))
        self._units_combo = QComboBox()
        self._units_combo.setObjectName("SettingCombo")
        self._units_combo.addItems(EXPORT_UNITS)
        self._units_combo.blockSignals(True)
        if self._current_unit in EXPORT_UNITS:
            self._units_combo.setCurrentIndex(EXPORT_UNITS.index(self._current_unit))
        self._units_combo.blockSignals(False)
        self._units_combo.currentIndexChanged.connect(self._on_unit_changed)
        u_col.addWidget(self._units_combo)
        units_row.addLayout(u_col)

        dpi_col = QVBoxLayout()
        dpi_col.setSpacing(2)
        dpi_col.addWidget(self._make_sub_label("Resolution"))
        self._dpi_combo = QComboBox()
        self._dpi_combo.setObjectName("SettingCombo")
        self._dpi_combo.setEditable(True)
        for d in DPI_PRESETS:
            self._dpi_combo.addItem(f"{d} DPI", d)
        self._dpi_combo.blockSignals(True)
        for i in range(self._dpi_combo.count()):
            if self._dpi_combo.itemData(i) == self._current_dpi:
                self._dpi_combo.setCurrentIndex(i)
                break
        else:
            self._dpi_combo.setCurrentText(f"{self._current_dpi} DPI")
        self._dpi_combo.blockSignals(False)
        self._dpi_combo.currentIndexChanged.connect(self._on_dpi_changed)
        self._dpi_combo.lineEdit().editingFinished.connect(self._on_dpi_edited)
        dpi_col.addWidget(self._dpi_combo)
        units_row.addLayout(dpi_col)

        parent_layout.addLayout(units_row)

        # ---- Scale preset + Reset ----
        scale_row = QHBoxLayout()
        scale_row.setSpacing(6)
        scale_row.addWidget(self._make_sub_label("Scale:"))

        self._size_combo = QComboBox()
        self._size_combo.setObjectName("SizePresetCombo")
        for name, scale in SIZE_PRESETS:
            self._size_combo.addItem(name, scale)
        self._size_combo.setCurrentIndex(3)  # 1× default
        self._size_combo.currentIndexChanged.connect(self._on_preset_changed)
        scale_row.addWidget(self._size_combo, 1)

        reset_btn = QPushButton("Reset")
        reset_btn.setObjectName("ResetDimsBtn")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setToolTip("Reset to original document size")
        reset_btn.clicked.connect(self._on_reset_dims)
        scale_row.addWidget(reset_btn)

        parent_layout.addLayout(scale_row)

    def _build_metadata_section(self, parent_layout: QVBoxLayout) -> None:
        lbl = QLabel("Metadata")
        lbl.setObjectName("ExportSettingLabel")
        parent_layout.addWidget(lbl)

        self._meta_exif = QCheckBox("Include EXIF data")
        self._meta_exif.setObjectName("MetadataCheck")
        self._meta_exif.setChecked(True)
        parent_layout.addWidget(self._meta_exif)

        self._meta_icc = QCheckBox("Embed ICC profile")
        self._meta_icc.setObjectName("MetadataCheck")
        self._meta_icc.setChecked(True)
        parent_layout.addWidget(self._meta_icc)

        self._meta_xmp = QCheckBox("Include XMP metadata")
        self._meta_xmp.setObjectName("MetadataCheck")
        parent_layout.addWidget(self._meta_xmp)

    @staticmethod
    def _make_sub_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("ExportHint")
        return lbl

    # =========================================================================
    # Format selection
    # =========================================================================

    def _select_format(self, fmt: dict) -> None:
        self._selected_format = fmt
        ext = fmt["ext"]

        for btn in self._fmt_group.buttons():
            if btn.text().strip() == fmt["name"]:
                btn.setChecked(True)
                break

        self._quality_section.setVisible(fmt.get("lossy", False))
        self._subsample_section.setVisible(ext == "jpeg")
        self._bg_color_section.setVisible(ext in _FLAT_FORMATS)
        self._update_size_estimate()

    # =========================================================================
    # Dimension / unit handlers
    # =========================================================================

    def _configure_spinboxes(self, unit: str) -> None:
        """Update range / decimals / step for the given unit.

        Signals are blocked so that Qt's internal clamping of the current
        value to the new range does NOT trigger _on_w_changed / _on_h_changed
        and therefore does NOT overwrite _width_px / _height_px.
        """
        mn, mx, dec, step = _spinbox_cfg(unit)
        for spin in (self._width_spin, self._height_spin):
            spin.blockSignals(True)
            spin.setDecimals(dec)
            spin.setSingleStep(step)
            spin.setRange(mn, mx)
            spin.blockSignals(False)

    def _sync_spinboxes_from_px(self) -> None:
        """Push _width_px / _height_px → spinboxes in the current unit."""
        ppu = _px_per_unit(self._current_unit, self._current_dpi)
        for spin, px_val in (
            (self._width_spin,  self._width_px),
            (self._height_spin, self._height_px),
        ):
            spin.blockSignals(True)
            spin.setValue(px_val / ppu)
            spin.blockSignals(False)
        self._update_size_estimate()

    def _on_w_changed(self, val: float) -> None:
        if self._suppress_change:
            return
        ppu = _px_per_unit(self._current_unit, self._current_dpi)
        self._width_px = max(1.0, val * ppu)
        if self._aspect_locked:
            self._suppress_change = True
            self._height_px = self._width_px / max(self._aspect_ratio_px, 1e-9)
            self._height_spin.setValue(self._height_px / ppu)
            self._suppress_change = False
        self._update_size_estimate()

    def _on_h_changed(self, val: float) -> None:
        if self._suppress_change:
            return
        ppu = _px_per_unit(self._current_unit, self._current_dpi)
        self._height_px = max(1.0, val * ppu)
        if self._aspect_locked:
            self._suppress_change = True
            self._width_px = self._height_px * self._aspect_ratio_px
            self._width_spin.setValue(self._width_px / ppu)
            self._suppress_change = False
        self._update_size_estimate()

    def _on_lock_toggled(self, checked: bool) -> None:
        self._aspect_locked = checked
        if checked:
            self._aspect_ratio_px = self._width_px / max(self._height_px, 1.0)

    def _on_unit_changed(self, idx: int) -> None:
        new_unit = EXPORT_UNITS[idx]
        if new_unit == self._current_unit:
            return
        self._current_unit = new_unit
        # blockSignals is handled inside configure/sync; no suppress flag needed
        self._configure_spinboxes(new_unit)
        self._sync_spinboxes_from_px()

    def _on_dpi_changed(self, _idx: int) -> None:
        new_dpi = self._get_dpi_from_combo()
        if new_dpi != self._current_dpi:
            self._apply_dpi_change(new_dpi)

    def _on_dpi_edited(self) -> None:
        new_dpi = self._get_dpi_from_combo()
        if new_dpi != self._current_dpi:
            self._apply_dpi_change(new_dpi)

    def _apply_dpi_change(self, new_dpi: int) -> None:
        """DPI changed — for physical units keep displayed size, update pixel store."""
        if self._current_unit != "px":
            new_ppu = _px_per_unit(self._current_unit, new_dpi)
            # Read displayed (physical) values before changing dpi
            w_disp = self._width_spin.value()
            h_disp = self._height_spin.value()
            self._width_px  = max(1.0, w_disp * new_ppu)
            self._height_px = max(1.0, h_disp * new_ppu)
        self._current_dpi = new_dpi
        self._update_size_estimate()

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

    def _on_preset_changed(self, index: int) -> None:
        scale = self._size_combo.itemData(index)
        if scale is not None:
            self._width_px  = max(1.0, self._orig_w * scale)
            self._height_px = max(1.0, self._orig_h * scale)
            self._sync_spinboxes_from_px()

    def _on_reset_dims(self) -> None:
        self._width_px  = float(self._orig_w)
        self._height_px = float(self._orig_h)
        self._sync_spinboxes_from_px()
        for i in range(self._size_combo.count()):
            if self._size_combo.itemData(i) == 1.0:
                self._size_combo.blockSignals(True)
                self._size_combo.setCurrentIndex(i)
                self._size_combo.blockSignals(False)
                break

    # =========================================================================
    # Background colour
    # =========================================================================

    def _on_pick_bg_color(self) -> None:
        color = QColorDialog.getColor(self._jpeg_bg_color, self, "Background Color")
        if color.isValid():
            self._jpeg_bg_color = color
            self._update_bg_swatch()

    def _update_bg_swatch(self) -> None:
        c = self._jpeg_bg_color.name()
        self._jpeg_bg_swatch.setStyleSheet(
            f"background-color: {c}; border: 1px solid rgba(128,128,128,0.5); border-radius: 5px;"
        )

    # =========================================================================
    # Size estimate
    # =========================================================================

    def _update_size_estimate(self) -> None:
        w = max(1, round(self._width_px))
        h = max(1, round(self._height_px))
        fmt = self._selected_format

        if fmt["ext"] in ("jpeg", "webp", "avif", "heic"):
            q = self._quality_slider.value()
            ratio = 0.05 + (q / 100) * 0.4
            size_bytes = int(w * h * 3 * ratio)
        elif fmt["ext"] == "png":
            size_bytes = int(w * h * 4 * 0.5)
        elif fmt["ext"] in ("tiff", "bmp"):
            size_bytes = w * h * 4
        elif fmt["ext"] == "psd":
            size_bytes = w * h * 4 * 2
        else:
            size_bytes = w * h * 4

        if size_bytes < 1024:
            size_str = f"~{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            size_str = f"~{size_bytes / 1024:.0f} KB"
        elif size_bytes < 1024 ** 3:
            size_str = f"~{size_bytes / 1024**2:.1f} MB"
        else:
            size_str = f"~{size_bytes / 1024**3:.2f} GB"

        # Dimension label — show physical size when not in px mode
        if self._current_unit == "px":
            dim_label = f"{w} × {h} px"
        else:
            ppu = _px_per_unit(self._current_unit, self._current_dpi)
            wu  = self._width_px  / ppu
            hu  = self._height_px / ppu
            dec = _spinbox_cfg(self._current_unit)[2]
            fmt_str = f".{dec}f"
            dim_label = (
                f"{wu:{fmt_str}} × {hu:{fmt_str}} {self._current_unit}"
                f"  ({w} × {h} px)"
            )

        self._size_estimate.setText(f"{size_str}  ·  {dim_label}")

    # =========================================================================
    # Actions
    # =========================================================================

    def _on_export(self) -> None:
        fmt = self._selected_format
        ext = fmt["ext"]
        if ext == "jpeg":
            ext = "jpg"
        filt = f"{fmt['name']} Files (*.{ext})"
        path, _ = QFileDialog.getSaveFileName(self, "Export As", "", filt)
        if path:
            if not path.lower().endswith(f".{ext}"):
                path += f".{ext}"
            self._export_path = path
            self.accept()

    def _on_copy_clipboard(self) -> None:
        self._export_path = "__clipboard__"
        self.accept()

    # =========================================================================
    # Public API
    # =========================================================================

    def get_export_settings(self) -> dict:
        """Return full export configuration. Width/height are always in pixels."""
        fmt = self._selected_format
        bg  = self._jpeg_bg_color
        return {
            "format":       fmt["ext"],
            "format_name":  fmt["name"],
            "path":         getattr(self, "_export_path", None),
            "quality":      self._quality_slider.value() if fmt.get("lossy") else 100,
            "width":        max(1, round(self._width_px)),
            "height":       max(1, round(self._height_px)),
            "subsampling":  self._subsample_combo.currentText(),
            "jpeg_bg":      (bg.red(), bg.green(), bg.blue()),
            "include_exif": self._meta_exif.isChecked(),
            "embed_icc":    self._meta_icc.isChecked(),
            "include_xmp":  self._meta_xmp.isChecked(),
            "clipboard":    getattr(self, "_export_path", "") == "__clipboard__",
        }
