"""Selection tool properties bar — mode, feather, tolerance, actions."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSpinBox, QWidget

from .base import ACCENT, LABEL, SPIN, make_separator, CompactPropertyWidget

_SEL_MODE_BTN = """
    QPushButton {
        font-size: 10.5px; padding: 2px 8px; font-weight: 500;
        background: transparent; border: 1px solid transparent; border-radius: 4px;
        color: #b0b4b8; min-height: 22px; max-height: 22px;
    }
    QPushButton:hover { 
        background: rgba(255,255,255,0.05); color: #e0e4e8; 
        border: 1px solid rgba(255,255,255,0.1); 
    }
    QPushButton:checked { 
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(110,180,255,0.25), stop:1 rgba(110,180,255,0.1)); 
        color: #ffffff; border: 1px solid rgba(110,180,255,0.4); 
    }
"""

_SEL_ACTION_BTN = """
    QPushButton {
        font-size: 10.5px; padding: 2px 8px; font-weight: 500;
        background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.05); border-radius: 4px;
        color: #b0b4b8; min-height: 22px; max-height: 22px; border-bottom: 1px solid rgba(255,255,255,0.1);
    }
    QPushButton:hover { 
        background: rgba(0,0,0,0.3); color: #e0e4e8; 
        border: 1px solid rgba(255,255,255,0.15); 
    }
    QPushButton:pressed { 
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(110,180,255,0.25), stop:1 rgba(110,180,255,0.1)); 
        color: #ffffff; border: 1px solid rgba(110,180,255,0.4); 
    }
"""


class SelectionPropertiesBar(QWidget):
    """Horizontal bar for selection tools: mode, feather, tolerance, actions."""

    from PySide6.QtCore import Signal
    property_changed = Signal(str, object)
    action_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        lbl = QLabel("Mode")
        lbl.setStyleSheet(LABEL)
        layout.addWidget(lbl)

        self._mode_btns: dict[str, QPushButton] = {}
        for mode_key, mode_label in [
            ("new", "New"), ("add", "Add"), ("subtract", "Sub"), ("intersect", "Int"),
        ]:
            btn = QPushButton(mode_label)
            btn.setCheckable(True)
            btn.setStyleSheet(_SEL_MODE_BTN)
            btn.setToolTip({"new": "New Selection", "add": "Add to Selection (Shift)",
                            "subtract": "Subtract from Selection (Alt)",
                            "intersect": "Intersect with Selection (Shift+Alt)"}[mode_key])
            btn.clicked.connect(lambda checked, m=mode_key: self._set_mode(m))
            layout.addWidget(btn)
            self._mode_btns[mode_key] = btn
        self._mode_btns["new"].setChecked(True)

        layout.addWidget(make_separator())

        self._feather_widget = CompactPropertyWidget(
            "feather", "Feather", 0, 0, 100, 1.0, decimals=0, suffix=" px", parent=self
        )
        self._feather_widget.value_changed.connect(lambda k, v: self.property_changed.emit("feather", v))
        layout.addWidget(self._feather_widget)

        self._tolerance_widget = CompactPropertyWidget(
            "tolerance", "Tolerance", 32, 0, 255, 1.0, decimals=0, suffix="", parent=self
        )
        self._tolerance_widget.value_changed.connect(lambda k, v: self.property_changed.emit("tolerance", v))
        layout.addWidget(self._tolerance_widget)

        self._contiguous_btn = QPushButton("Contiguous")
        self._contiguous_btn.setCheckable(True)
        self._contiguous_btn.setChecked(True)
        self._contiguous_btn.setStyleSheet(_SEL_MODE_BTN)
        self._contiguous_btn.setToolTip("Select only connected pixels")
        self._contiguous_btn.toggled.connect(
            lambda v: self.property_changed.emit("contiguous", v))
        layout.addWidget(self._contiguous_btn)

        layout.addWidget(make_separator())

        for action, label, tip in [
            ("delete", "Delete", "Delete selected pixels (Del)"),
            ("fill_fg", "Fill FG", "Fill with foreground color (Alt+Backspace)"),
            ("fill_bg", "Fill BG", "Fill with background color (Ctrl+Backspace)"),
            ("duplicate", "Duplicate", "Create new layer from selection (Ctrl+J)"),
            ("invert", "Invert", "Invert selection"),
            ("deselect", "Deselect", "Clear selection (Ctrl+D)"),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(_SEL_ACTION_BTN)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _=False, a=action: self.action_requested.emit(a))
            layout.addWidget(btn)

        layout.addStretch()

    def _set_mode(self, mode: str) -> None:
        for k, btn in self._mode_btns.items():
            btn.setChecked(k == mode)
        self.property_changed.emit("mode", mode)

    def set_wand_mode(self, is_wand: bool) -> None:
        self._tolerance_widget.setVisible(is_wand)
        self._contiguous_btn.setVisible(is_wand)

    def sync_from_tool(self, tool) -> None:
        self.blockSignals(True)
        try:
            if hasattr(tool, "feather"):
                self._feather_widget.set_value(tool.feather)
            if hasattr(tool, "tolerance"):
                self._tolerance_widget.set_value(tool.tolerance)
            if hasattr(tool, "contiguous"):
                self._contiguous_btn.setChecked(tool.contiguous)
            if hasattr(tool, "mode"):
                for k, btn in self._mode_btns.items():
                    btn.setChecked(k == tool.mode)
        finally:
            self.blockSignals(False)
