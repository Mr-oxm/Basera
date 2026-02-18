"""Selection tool properties bar — mode, feather, tolerance, actions."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSpinBox, QWidget

from .base import ACCENT, LABEL, SPIN, make_separator

_SEL_MODE_BTN = """
    QPushButton {
        font-size: 10px; padding: 2px 8px;
        background: transparent; border: 1px solid #444; border-radius: 4px;
        color: #999; min-height: 22px; max-height: 22px;
    }
    QPushButton:hover { background: rgba(255,255,255,0.07); color: #ccc; }
    QPushButton:checked { background: rgba(74,111,165,0.35); color: #ddeeff; border-color: #5a8abf; }
"""

_SEL_ACTION_BTN = """
    QPushButton {
        font-size: 10px; padding: 2px 8px;
        background: #383838; border: 1px solid #444; border-radius: 4px;
        color: #bbb; min-height: 22px; max-height: 22px;
    }
    QPushButton:hover { background: rgba(255,255,255,0.07); color: #ccc; border-color: #5a8abf; }
    QPushButton:pressed { background: rgba(74,111,165,0.35); }
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

        lbl2 = QLabel("Feather")
        lbl2.setStyleSheet(LABEL)
        layout.addWidget(lbl2)
        self._feather_spin = QSpinBox()
        self._feather_spin.setRange(0, 100)
        self._feather_spin.setValue(0)
        self._feather_spin.setSuffix(" px")
        self._feather_spin.setFixedWidth(70)
        self._feather_spin.setMaximumHeight(22)
        self._feather_spin.setStyleSheet(SPIN.format(max_w=70, accent=ACCENT))
        self._feather_spin.valueChanged.connect(
            lambda v: self.property_changed.emit("feather", v))
        layout.addWidget(self._feather_spin)

        self._tol_label = QLabel("Tolerance")
        self._tol_label.setStyleSheet(LABEL)
        layout.addWidget(self._tol_label)
        self._tolerance_spin = QSpinBox()
        self._tolerance_spin.setRange(0, 255)
        self._tolerance_spin.setValue(32)
        self._tolerance_spin.setFixedWidth(60)
        self._tolerance_spin.setMaximumHeight(22)
        self._tolerance_spin.setStyleSheet(SPIN.format(max_w=60, accent=ACCENT))
        self._tolerance_spin.valueChanged.connect(
            lambda v: self.property_changed.emit("tolerance", v))
        layout.addWidget(self._tolerance_spin)

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
        self._tol_label.setVisible(is_wand)
        self._tolerance_spin.setVisible(is_wand)
        self._contiguous_btn.setVisible(is_wand)

    def sync_from_tool(self, tool) -> None:
        self.blockSignals(True)
        try:
            if hasattr(tool, "feather"):
                self._feather_spin.setValue(tool.feather)
            if hasattr(tool, "tolerance"):
                self._tolerance_spin.setValue(tool.tolerance)
            if hasattr(tool, "contiguous"):
                self._contiguous_btn.setChecked(tool.contiguous)
            if hasattr(tool, "mode"):
                for k, btn in self._mode_btns.items():
                    btn.setChecked(k == tool.mode)
        finally:
            self.blockSignals(False)
