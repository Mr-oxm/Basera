"""Slider-based parameter dialog for filters and adjustments."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal

from .adjustments.adjustment_preview_timing import PREVIEW_DEBOUNCE_MS
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QLabel, QScrollArea, QSlider, QVBoxLayout, QWidget,
)

# Smart range inference by parameter name keywords
_RANGE_HINTS: dict[str, tuple[int, int]] = {
    "brightness": (-100, 100), "contrast": (-100, 100),
    "hue": (-180, 180), "saturation": (-100, 100), "lightness": (-100, 100),
    "vibrance": (-100, 100), "exposure": (-50, 50), "offset": (-50, 50),
    "threshold": (0, 255), "levels": (2, 30), "density": (0, 100),
    "amount": (-200, 200), "radius": (0, 250), "distance": (0, 200),
    "angle": (0, 360), "size": (0, 100), "strength": (0, 100),
    "wavelength": (1, 500), "amplitude": (1, 200),
    "intensity": (0, 200), "ambient": (0, 100), "soften": (0, 20),
    "depth": (0, 30), "altitude": (0, 90), "blade_count": (3, 8),
    "scale": (1, 100), "octaves": (1, 8), "seed": (0, 999),
    "height": (1, 10), "spread": (0, 100), "choke": (0, 100),
    # Color Balance RGB tuples flattened to _r, _g, _b
    "shadows": (-100, 100), "midtones": (-100, 100), "highlights": (-100, 100),
    "shadow": (0, 255), "highlight": (0, 255),
    # Color channels
    "red": (0, 100), "green": (0, 100), "blue": (0, 100),
    "yellow": (0, 100), "cyan": (0, 100), "magenta": (0, 100),
    "black": (-100, 100),
    # Photo filter / color picker
    "color": (0, 255),
    # Channel mixer
    "red_red": (-200, 200), "red_green": (-200, 200), "red_blue": (-200, 200),
    "green_red": (-200, 200), "green_green": (-200, 200), "green_blue": (-200, 200),
    "blue_red": (-200, 200), "blue_green": (-200, 200), "blue_blue": (-200, 200),
    # Input/output levels
    "input_black": (0, 255), "input_white": (0, 255),
    "output_black": (0, 255), "output_white": (0, 255),
    "gamma": (0, 30),
}


class FilterDialog(QDialog):
    """Builds sliders automatically from a params dict."""

    # Emitted (debounced) whenever the user changes any parameter.
    params_changed = Signal(dict)

    def __init__(self, title: str, params: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        self._raw = dict(params)      # original types preserved
        self._flat: dict[str, object] = {}  # flattened for UI
        self._widgets: dict[str, QWidget] = {}

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._emit_params)

        self._flatten_params()
        self._build_ui()

    # ---- Flatten complex types into individual controls ----------------------

    def _flatten_params(self) -> None:
        for key, val in self._raw.items():
            if isinstance(val, (list, tuple)) and val and isinstance(val[0], (int, float)):
                # Numeric tuple → individual sliders (e.g. color → color_r, color_g, color_b)
                suffixes = ["_r", "_g", "_b", "_a"] if len(val) <= 4 else [f"_{i}" for i in range(len(val))]
                for i, v in enumerate(val):
                    self._flat[f"{key}{suffixes[i]}"] = v
            elif isinstance(val, (int, float, bool, str)):
                self._flat[key] = val
            # Skip complex types (list of tuples, etc.)

    # ---- Build UI -----------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(6)

        for key, val in self._flat.items():
            if isinstance(val, bool):
                cb = QCheckBox(self._label(key))
                cb.setChecked(val)
                cb.toggled.connect(lambda v, k=key: self._set(k, v))
                layout.addWidget(cb)
                self._widgets[key] = cb

            elif isinstance(val, (int, float)):
                lo, hi = self._guess_range(key, val)
                is_float = isinstance(val, float) and hi <= 10
                scale = 10 if is_float else 1
                row = QHBoxLayout()
                lbl = QLabel(self._label(key))
                lbl.setFixedWidth(120)
                row.addWidget(lbl)
                slider = QSlider(Qt.Orientation.Horizontal)
                slider.setRange(int(lo * scale), int(hi * scale))
                slider.setValue(int(val * scale))
                val_lbl = QLabel(self._fmt(val))
                val_lbl.setFixedWidth(50)
                val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                slider.valueChanged.connect(
                    lambda v, k=key, s=scale, vl=val_lbl: self._on_slider(k, v, s, vl),
                )
                row.addWidget(slider, 1)
                row.addWidget(val_lbl)
                layout.addLayout(row)
                self._widgets[key] = slider

            elif isinstance(val, str):
                row = QHBoxLayout()
                row.addWidget(QLabel(self._label(key)))
                combo = QComboBox()
                options = self._guess_options(key, val)
                combo.addItems(options)
                combo.setCurrentText(val)
                combo.currentTextChanged.connect(lambda v, k=key: self._set(k, v))
                row.addWidget(combo, 1)
                layout.addLayout(row)
                self._widgets[key] = combo

        layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # ---- Helpers ------------------------------------------------------------

    def _on_slider(self, key: str, raw_val: int, scale: int, label: QLabel) -> None:
        val = raw_val / scale if scale > 1 else raw_val
        label.setText(self._fmt(val))
        self._set(key, val)

    def _set(self, key: str, value: object) -> None:
        orig = self._flat.get(key)
        # IMPORTANT: check bool BEFORE int because bool is a subclass of int
        if isinstance(orig, bool):
            self._flat[key] = bool(value)
        elif isinstance(orig, int) and isinstance(value, (int, float)):
            self._flat[key] = int(value)
        else:
            self._flat[key] = value
        # Schedule debounced preview update
        self._preview_timer.start()

    def _emit_params(self) -> None:
        """Emit the reconstructed params dict for live preview."""
        self.params_changed.emit(self.get_params())

    def get_params(self) -> dict:
        """Reconstruct the original param shapes from flat values."""
        result = dict(self._raw)
        for key, orig in self._raw.items():
            if isinstance(orig, (list, tuple)) and orig and isinstance(orig[0], (int, float)):
                suffixes = ["_r", "_g", "_b", "_a"] if len(orig) <= 4 else [f"_{i}" for i in range(len(orig))]
                vals = [self._flat.get(f"{key}{suffixes[i]}", orig[i]) for i in range(len(orig))]
                result[key] = type(orig)(vals)
            elif key in self._flat:
                result[key] = self._flat[key]
        return result

    @staticmethod
    def _guess_range(key: str, default: int | float) -> tuple[int, int]:
        low = key.lower()
        # Check exact key first, then key without last suffix, then each word
        candidates = [low]
        if "_" in low:
            candidates.append(low.rsplit("_", 1)[0])
        candidates.extend(low.split("_"))
        for candidate in candidates:
            if candidate in _RANGE_HINTS:
                return _RANGE_HINTS[candidate]
        # Check if any hint keyword is contained in the key
        for hint_key, (lo, hi) in _RANGE_HINTS.items():
            if hint_key in low:
                return lo, hi
        if isinstance(default, float):
            if 0 <= default <= 1:
                return 0, 1
            return int(default - 100), int(default + 100)
        d = int(default)
        if d == 0:
            return -100, 100
        if d > 0:
            return 0, max(d * 4, 255)
        return d * 4, abs(d) * 4

    @staticmethod
    def _guess_options(key: str, current: str) -> list[str]:
        k = key.lower()
        if "type" in k:
            return ["sine", "triangle", "square"]
        if "direction" in k:
            return ["horizontal", "vertical"]
        if "position" in k:
            return ["outside", "inside", "center"]
        if "range" in k or "color_range" in k:
            return ["reds", "yellows", "greens", "cyans", "blues", "magentas",
                    "whites", "neutrals", "blacks"]
        return [current]

    @staticmethod
    def _label(key: str) -> str:
        return key.replace("_", " ").title()

    @staticmethod
    def _fmt(v: int | float) -> str:
        return f"{v:.1f}" if isinstance(v, float) else str(int(v))
