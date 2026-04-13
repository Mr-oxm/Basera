"""Export dialog — multi-format export with quality, size, and metadata controls.

Supported formats: JPEG, PNG, WEBP, AVIF, TIFF, BMP, PSD, HEIC, SVG, PDF, .basera
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QSlider, QSpinBox, QComboBox,
    QCheckBox, QWidget, QScrollArea, QFrame,
    QButtonGroup, QSizePolicy, QFileDialog,
    QGraphicsDropShadowEffect, QApplication,
)

from ..styles import render_qss
from ...utils.image_io import can_save_extension


# ---------------------------------------------------------------------------
# Format definitions
# ---------------------------------------------------------------------------

ALL_FORMATS = [
    {"ext": "jpeg", "name": "JPEG", "lossy": True, "desc": "Joint Photographic Experts Group"},
    {"ext": "png", "name": "PNG", "lossy": False, "desc": "Portable Network Graphics"},
    {"ext": "webp", "name": "WEBP", "lossy": True, "desc": "Web Picture format"},
    {"ext": "avif", "name": "AVIF", "lossy": True, "desc": "AV1 Image File Format"},
    {"ext": "tiff", "name": "TIFF", "lossy": False, "desc": "Tagged Image File Format"},
    {"ext": "bmp", "name": "BMP", "lossy": False, "desc": "Bitmap Image"},
    {"ext": "psd", "name": "PSD", "lossy": False, "desc": "Adobe Photoshop Document"},
    {"ext": "heic", "name": "HEIC", "lossy": True, "desc": "High Efficiency Image Container"},
    {"ext": "svg", "name": "SVG", "lossy": False, "desc": "Scalable Vector Graphics"},
    {"ext": "pdf", "name": "PDF", "lossy": False, "desc": "Portable Document Format"},
    {"ext": "basera", "name": ".basera", "lossy": False, "desc": "Basera Project File"},
]

SIZE_PRESETS = [
    ("0.25×", 0.25),
    ("0.5×", 0.5),
    ("0.75×", 0.75),
    ("1× (Original)", 1.0),
    ("1.5×", 1.5),
    ("2×", 2.0),
    ("3×", 3.0),
    ("4×", 4.0),
    ("Custom", None),
]

SUBSAMPLING_OPTIONS = ["4:4:4 (Best)", "4:2:2", "4:2:0 (Smallest)"]


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
        self._formats = [f for f in ALL_FORMATS if can_save_extension(f".{f['ext']}")]
        if not self._formats:
            # Failsafe: PNG should always be available with Pillow.
            self._formats = [{"ext": "png", "name": "PNG", "lossy": False, "desc": "Portable Network Graphics"}]
        self._selected_format = self._formats[0]

        self._build_ui()
        self._apply_theme()
        self._select_format(self._formats[0])

    def _apply_theme(self) -> None:
        from ..theme import ThemeManager
        palette = ThemeManager.instance().active_palette
        self.setStyleSheet(render_qss("export_dialog.qss", palette))

    # ---- UI ---------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        # Title
        title = QLabel("Export")
        title.setObjectName("ExportTitle")
        root.addWidget(title)

        # Body: left (format list) | right (settings)
        body = QHBoxLayout()
        body.setSpacing(16)

        # ---- Left: format cards ----
        left = QVBoxLayout()
        left.setSpacing(6)

        fmt_label = QLabel("FORMAT")
        fmt_label.setObjectName("ExportSettingLabel")
        fmt_label.setStyleSheet("font-size: 10px; font-weight: 700; letter-spacing: 0.06em;")
        left.addWidget(fmt_label)

        fmt_scroll = QScrollArea()
        fmt_scroll.setWidgetResizable(True)
        fmt_scroll.setFrameShape(QFrame.Shape.NoFrame)
        fmt_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        fmt_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        fmt_container = QWidget()
        fmt_container.setStyleSheet("background: transparent;")
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
        right = QVBoxLayout()
        right.setSpacing(12)

        settings = QWidget()
        settings.setObjectName("ExportSettingsPanel")
        self._settings_layout = QVBoxLayout(settings)
        self._settings_layout.setContentsMargins(16, 14, 16, 14)
        self._settings_layout.setSpacing(12)

        # Quality slider (for lossy formats)
        self._quality_section = QWidget()
        q_layout = QVBoxLayout(self._quality_section)
        q_layout.setContentsMargins(0, 0, 0, 0)
        q_layout.setSpacing(6)

        q_header = QHBoxLayout()
        q_label = QLabel("Quality")
        q_label.setObjectName("ExportSettingLabel")
        q_header.addWidget(q_label)
        self._quality_value = QLabel("85%")
        self._quality_value.setObjectName("QualityValue")
        q_header.addWidget(self._quality_value)
        q_header.addStretch()
        q_layout.addLayout(q_header)

        self._quality_slider = QSlider(Qt.Orientation.Horizontal)
        self._quality_slider.setObjectName("QualitySlider")
        self._quality_slider.setRange(1, 100)
        self._quality_slider.setValue(85)
        self._quality_slider.valueChanged.connect(
            lambda v: self._quality_value.setText(f"{v}%")
        )
        q_layout.addWidget(self._quality_slider)

        self._settings_layout.addWidget(self._quality_section)

        # Subsampling (JPEG-specific)
        self._subsample_section = QWidget()
        ss_layout = QVBoxLayout(self._subsample_section)
        ss_layout.setContentsMargins(0, 0, 0, 0)
        ss_layout.setSpacing(4)
        ss_label = QLabel("Chroma Subsampling")
        ss_label.setObjectName("ExportSettingLabel")
        ss_layout.addWidget(ss_label)
        self._subsample_combo = QComboBox()
        self._subsample_combo.setObjectName("SubsamplingCombo")
        self._subsample_combo.addItems(SUBSAMPLING_OPTIONS)
        ss_layout.addWidget(self._subsample_combo)
        self._settings_layout.addWidget(self._subsample_section)

        # Size presets
        size_section = QVBoxLayout()
        size_section.setSpacing(4)
        size_label = QLabel("Export Size")
        size_label.setObjectName("ExportSettingLabel")
        size_section.addWidget(size_label)

        self._size_combo = QComboBox()
        self._size_combo.setObjectName("SizePresetCombo")
        for name, scale in SIZE_PRESETS:
            self._size_combo.addItem(name, scale)
        self._size_combo.setCurrentIndex(3)  # 1× default
        self._size_combo.currentIndexChanged.connect(self._on_size_changed)
        size_section.addWidget(self._size_combo)

        # Custom size spinners (hidden by default)
        self._custom_size_row = QHBoxLayout()
        self._custom_size_row.setSpacing(8)

        self._export_w = QSpinBox()
        self._export_w.setRange(1, 30000)
        self._export_w.setPrefix("W: ")
        self._export_w.setObjectName("DimInput")
        self._custom_size_row.addWidget(self._export_w)

        self._export_h = QSpinBox()
        self._export_h.setRange(1, 30000)
        self._export_h.setPrefix("H: ")
        self._export_h.setObjectName("DimInput")
        self._custom_size_row.addWidget(self._export_h)

        self._custom_size_widget = QWidget()
        self._custom_size_widget.setLayout(self._custom_size_row)
        self._custom_size_widget.setVisible(False)
        size_section.addWidget(self._custom_size_widget)

        self._settings_layout.addLayout(size_section)

        # Metadata toggles
        meta_section = QVBoxLayout()
        meta_section.setSpacing(6)
        meta_label = QLabel("Metadata")
        meta_label.setObjectName("ExportSettingLabel")
        meta_section.addWidget(meta_label)

        self._meta_exif = QCheckBox("Include EXIF data")
        self._meta_exif.setObjectName("MetadataCheck")
        self._meta_exif.setChecked(True)
        meta_section.addWidget(self._meta_exif)

        self._meta_icc = QCheckBox("Embed ICC profile")
        self._meta_icc.setObjectName("MetadataCheck")
        self._meta_icc.setChecked(True)
        meta_section.addWidget(self._meta_icc)

        self._meta_xmp = QCheckBox("Include XMP metadata")
        self._meta_xmp.setObjectName("MetadataCheck")
        meta_section.addWidget(self._meta_xmp)

        self._settings_layout.addLayout(meta_section)

        # Size estimate
        self._size_estimate = QLabel("")
        self._size_estimate.setObjectName("ExportSizeEstimate")
        self._size_estimate.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._settings_layout.addWidget(self._size_estimate)

        self._settings_layout.addStretch()

        right.addWidget(settings, 1)

        body.addLayout(right, 2)
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

        clipboard_btn = QPushButton("📋 Copy to Clipboard")
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

        # Set initial doc dimensions
        if self._doc:
            self._export_w.setValue(self._doc.width)
            self._export_h.setValue(self._doc.height)

    # ---- Format selection --------------------------------------------------

    def _select_format(self, fmt: dict) -> None:
        self._selected_format = fmt

        # Check the button
        for btn in self._fmt_group.buttons():
            if btn.text().strip() == fmt["name"]:
                btn.setChecked(True)
                break

        # Show/hide quality for lossy formats
        is_lossy = fmt.get("lossy", False)
        self._quality_section.setVisible(is_lossy)

        # Show/hide subsampling for JPEG
        is_jpeg = fmt["ext"] == "jpeg"
        self._subsample_section.setVisible(is_jpeg)

        # Update size estimate
        self._update_size_estimate()

    # ---- Size handling -----------------------------------------------------

    def _on_size_changed(self, index: int) -> None:
        scale = self._size_combo.itemData(index)
        if scale is None:
            # Custom
            self._custom_size_widget.setVisible(True)
        else:
            self._custom_size_widget.setVisible(False)
            if self._doc:
                self._export_w.setValue(max(1, int(self._doc.width * scale)))
                self._export_h.setValue(max(1, int(self._doc.height * scale)))
        self._update_size_estimate()

    def _update_size_estimate(self) -> None:
        w = self._export_w.value()
        h = self._export_h.value()
        fmt = self._selected_format

        # Rough estimate
        if fmt["ext"] in ("jpeg", "webp", "avif", "heic"):
            q = self._quality_slider.value()
            ratio = 0.05 + (q / 100) * 0.4  # rough compression ratio
            size_bytes = int(w * h * 3 * ratio)
        elif fmt["ext"] == "png":
            size_bytes = int(w * h * 4 * 0.5)  # rough PNG compression
        elif fmt["ext"] in ("tiff", "bmp"):
            size_bytes = w * h * 4
        elif fmt["ext"] == "psd":
            size_bytes = w * h * 4 * 2  # rough multi-layer estimate
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

        self._size_estimate.setText(f"Estimated file size: {size_str} ({w}×{h})")

    # ---- Actions -----------------------------------------------------------

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

    # ---- Public API --------------------------------------------------------

    def get_export_settings(self) -> dict:
        """Return full export configuration."""
        fmt = self._selected_format
        return {
            "format": fmt["ext"],
            "format_name": fmt["name"],
            "path": getattr(self, "_export_path", None),
            "quality": self._quality_slider.value() if fmt.get("lossy") else 100,
            "width": self._export_w.value(),
            "height": self._export_h.value(),
            "subsampling": self._subsample_combo.currentText(),
            "include_exif": self._meta_exif.isChecked(),
            "embed_icc": self._meta_icc.isChecked(),
            "include_xmp": self._meta_xmp.isChecked(),
            "clipboard": getattr(self, "_export_path", "") == "__clipboard__",
        }
