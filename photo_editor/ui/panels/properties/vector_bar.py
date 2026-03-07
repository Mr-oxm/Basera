"""Vector tool properties bar — Pen / Node / Shape tools."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QWidget,
)
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QIcon

from ...icons import vector_bool_icon, vector_node_icon
from ...widgets.color_dropdown import ColorDropdown
from ....core.color import Color, LinearGradient, RadialGradient
from ....core.color_engine import ConicalGradient, DiamondGradient
from ....vector.style import FillPaint, SolidPaint, GradientPaint, GradientType, GradientStop as VecGradientStop
from .base import ACCENT, COMBO, FLAT_BTN, LABEL, SPIN, make_separator

_VECTOR_BTN = """
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

_BOOL_BTN = """
    QPushButton {
        font-size: 10px; padding: 2px 6px; font-weight: 600;
        background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.06); border-radius: 4px;
        color: #8090a0; min-height: 22px; max-height: 22px;
    }
    QPushButton:hover {
        background: rgba(60,130,220,0.25); color: #c0d0e0;
        border: 1px solid rgba(60,130,220,0.4);
    }
    QPushButton:pressed {
        background: rgba(60,130,220,0.35); color: #ffffff;
        border: 1px solid rgba(60,130,220,0.6);
    }
    QPushButton:disabled {
        background: rgba(0,0,0,0.12); color: #505458;
        border: 1px solid rgba(255,255,255,0.02);
    }
    QPushButton:checked {
        background: rgba(60,130,220,0.35); color: #ffffff;
        border: 1px solid rgba(60,130,220,0.6);
    }
"""

_BOOL_APPLY_BTN = """
    QPushButton {
        font-size: 10.5px; padding: 2px 10px; font-weight: 600;
        background: rgba(40,160,80,0.3); border: 1px solid rgba(40,160,80,0.4); border-radius: 4px;
        color: #a0e0b0; min-height: 22px; max-height: 22px;
    }
    QPushButton:hover { background: rgba(40,160,80,0.45); color: #ffffff; }
    QPushButton:pressed { background: rgba(40,160,80,0.6); color: #ffffff; }
"""

_BOOL_CANCEL_BTN = """
    QPushButton {
        font-size: 10.5px; padding: 2px 10px; font-weight: 600;
        background: rgba(200,60,60,0.25); border: 1px solid rgba(200,60,60,0.3); border-radius: 4px;
        color: #e0a0a0; min-height: 22px; max-height: 22px;
    }
    QPushButton:hover { background: rgba(200,60,60,0.4); color: #ffffff; }
    QPushButton:pressed { background: rgba(200,60,60,0.55); color: #ffffff; }
"""

_SUBTRACT_LBL = """
    QLabel {
        font-size: 9px; color: #7090b0; padding: 0 2px;
    }
"""

class VectorPropertiesBar(QWidget):
    """Horizontal bar that adapts to the active vector tool: Pen, Node, or Shape."""

    from PySide6.QtCore import Signal
    property_changed = Signal(str, object)
    action_requested = Signal(str)
    boolean_hover = Signal(str)     # op name on hover, "" on leave
    boolean_hover_end = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        _spin_css = SPIN.format(max_w=55, accent=ACCENT)
        _combo_css = COMBO.format(widget="QComboBox", accent=ACCENT)

        lbl_fill = QLabel("Fill")
        lbl_fill.setStyleSheet(LABEL)
        layout.addWidget(lbl_fill)
        self._fill_btn = ColorDropdown(show_gradient=True, show_none_btn=True, parent=self)
        self._fill_btn.setFixedSize(56, 24)
        self._fill_btn.color_changed.connect(self._on_fill_changed)
        self._fill_btn.color_committed.connect(self._on_fill_changed)
        self._fill_btn.gradient_changed.connect(self._on_fill_gradient_changed)
        self._fill_btn.none_toggled.connect(
            lambda v: self.property_changed.emit("fill_none", v))
        layout.addWidget(self._fill_btn)

        layout.addSpacing(4)

        lbl_stroke = QLabel("Stroke")
        lbl_stroke.setStyleSheet(LABEL)
        layout.addWidget(lbl_stroke)
        self._stroke_btn = ColorDropdown(show_gradient=True, show_none_btn=True, parent=self)
        self._stroke_btn.setFixedSize(56, 24)
        self._stroke_btn.color_changed.connect(self._on_stroke_changed)
        self._stroke_btn.color_committed.connect(self._on_stroke_changed)
        self._stroke_btn.gradient_changed.connect(self._on_stroke_gradient_changed)
        self._stroke_btn.none_toggled.connect(
            lambda v: self.property_changed.emit("stroke_none", v))
        layout.addWidget(self._stroke_btn)

        lbl_sw = QLabel("W")
        lbl_sw.setStyleSheet(LABEL)
        layout.addWidget(lbl_sw)
        self._stroke_w = QDoubleSpinBox()
        self._stroke_w.setRange(0.0, 100.0)
        self._stroke_w.setSingleStep(0.5)
        self._stroke_w.setDecimals(1)
        self._stroke_w.setValue(2.0)
        self._stroke_w.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._stroke_w.setMaximumWidth(48)
        self._stroke_w.setMaximumHeight(22)
        self._stroke_w.setStyleSheet(_spin_css)
        self._stroke_w.valueChanged.connect(lambda v: self.property_changed.emit("stroke_width", v))
        layout.addWidget(self._stroke_w)

        self._sep_fill_stroke = make_separator()
        layout.addWidget(self._sep_fill_stroke)

        self._shape_lbl = QLabel("Shape")
        self._shape_lbl.setStyleSheet(LABEL)
        layout.addWidget(self._shape_lbl)

        self._shape_combo = QComboBox()
        self._shape_combo.setMaximumHeight(24)
        self._shape_combo.setFixedWidth(120)
        self._shape_combo.setStyleSheet(_combo_css)
        self._shape_combo.currentTextChanged.connect(
            lambda t: self.property_changed.emit("shape_type", t))
        layout.addWidget(self._shape_combo)

        self._param_a_lbl = QLabel("")
        self._param_a_lbl.setStyleSheet(LABEL)
        layout.addWidget(self._param_a_lbl)
        self._param_a = QDoubleSpinBox()
        self._param_a.setRange(0.0, 999.0)
        self._param_a.setSingleStep(0.05)
        self._param_a.setDecimals(2)
        self._param_a.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._param_a.setMaximumWidth(55)
        self._param_a.setMaximumHeight(22)
        self._param_a.setStyleSheet(_spin_css)
        self._param_a.valueChanged.connect(lambda v: self.property_changed.emit("param_a", v))
        layout.addWidget(self._param_a)

        self._param_b_lbl = QLabel("")
        self._param_b_lbl.setStyleSheet(LABEL)
        layout.addWidget(self._param_b_lbl)
        self._param_b = QDoubleSpinBox()
        self._param_b.setRange(0.0, 999.0)
        self._param_b.setSingleStep(0.05)
        self._param_b.setDecimals(2)
        self._param_b.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._param_b.setMaximumWidth(55)
        self._param_b.setMaximumHeight(22)
        self._param_b.setStyleSheet(_spin_css)
        self._param_b.valueChanged.connect(lambda v: self.property_changed.emit("param_b", v))
        layout.addWidget(self._param_b)

        self._sep_shape = make_separator()
        layout.addWidget(self._sep_shape)

        from PySide6.QtCore import QSize
        self._sharp_btn = QPushButton(" Sharp")
        self._sharp_btn.setIcon(vector_node_icon("sharp"))
        self._sharp_btn.setIconSize(QSize(16, 16))
        self._sharp_btn.setFixedHeight(24)
        self._sharp_btn.setStyleSheet(_VECTOR_BTN)
        self._sharp_btn.setToolTip("Set selected nodes to sharp (straight)")
        self._sharp_btn.clicked.connect(lambda: self.action_requested.emit("set_sharp"))
        layout.addWidget(self._sharp_btn)

        self._smooth_btn = QPushButton(" Smooth")
        self._smooth_btn.setIcon(vector_node_icon("smooth"))
        self._smooth_btn.setIconSize(QSize(16, 16))
        self._smooth_btn.setFixedHeight(24)
        self._smooth_btn.setStyleSheet(_VECTOR_BTN)
        self._smooth_btn.setToolTip("Set selected nodes to smooth (collinear handles)")
        self._smooth_btn.clicked.connect(lambda: self.action_requested.emit("set_smooth"))
        layout.addWidget(self._smooth_btn)

        self._symmetric_btn = QPushButton(" Symmetric")
        self._symmetric_btn.setIcon(vector_node_icon("symmetric"))
        self._symmetric_btn.setIconSize(QSize(16, 16))
        self._symmetric_btn.setFixedHeight(24)
        self._symmetric_btn.setStyleSheet(_VECTOR_BTN)
        self._symmetric_btn.setToolTip("Set selected nodes to symmetric (equal handles)")
        self._symmetric_btn.clicked.connect(lambda: self.action_requested.emit("set_symmetric"))
        layout.addWidget(self._symmetric_btn)

        self._sep_node_types = make_separator()
        layout.addWidget(self._sep_node_types)

        self._delete_btn = QPushButton(" Delete")
        self._delete_btn.setIcon(vector_node_icon("delete"))
        self._delete_btn.setIconSize(QSize(16, 16))
        self._delete_btn.setFixedHeight(24)
        self._delete_btn.setStyleSheet(_VECTOR_BTN)
        self._delete_btn.setToolTip("Delete selected nodes (or whole object)")
        self._delete_btn.clicked.connect(lambda: self.action_requested.emit("delete_nodes"))
        layout.addWidget(self._delete_btn)

        self._break_btn = QPushButton(" Break")
        self._break_btn.setIcon(vector_node_icon("break"))
        self._break_btn.setIconSize(QSize(16, 16))
        self._break_btn.setFixedHeight(24)
        self._break_btn.setStyleSheet(_VECTOR_BTN)
        self._break_btn.setToolTip("Break path at selected nodes")
        self._break_btn.clicked.connect(lambda: self.action_requested.emit("break_path"))
        layout.addWidget(self._break_btn)

        self._selall_btn = QPushButton(" Sel All")
        self._selall_btn.setIcon(vector_node_icon("select_all"))
        self._selall_btn.setIconSize(QSize(16, 16))
        self._selall_btn.setFixedHeight(24)
        self._selall_btn.setStyleSheet(_VECTOR_BTN)
        self._selall_btn.setToolTip("Select all nodes (Ctrl+A)")
        self._selall_btn.clicked.connect(lambda: self.action_requested.emit("select_all"))
        layout.addWidget(self._selall_btn)

        # ---- Boolean operations group ----
        self._sep_bool = make_separator()
        layout.addWidget(self._sep_bool)

        self._bool_union_btn = self._make_bool_btn(
            "", "Union — combine all shapes (Ctrl+Shift+U)",
            "bool_union", layout, icon_op="union")
        self._bool_subtract_btn = self._make_bool_btn(
            "", "Subtract — cut top from bottom (Ctrl+Shift+S)",
            "bool_subtract", layout, icon_op="subtract")
        self._bool_intersect_btn = self._make_bool_btn(
            "", "Intersect — keep overlap only (Ctrl+Shift+I)",
            "bool_intersect", layout, icon_op="intersect")
        self._bool_exclude_btn = self._make_bool_btn(
            "", "Exclude (XOR) — remove overlap (Ctrl+Shift+E)",
            "bool_exclude", layout, icon_op="exclude")
        self._bool_divide_btn = self._make_bool_btn(
            "", "Divide — split into fragments (Ctrl+Shift+D)",
            "bool_divide", layout, icon_op="divide")

        self._sep_bool2 = make_separator()
        layout.addWidget(self._sep_bool2)

        self._pick_seg_btn = QPushButton("")
        from PySide6.QtCore import QSize
        self._pick_seg_btn.setIcon(vector_bool_icon("pick_segments"))
        self._pick_seg_btn.setIconSize(QSize(16, 16))
        self._pick_seg_btn.setFixedHeight(24)
        self._pick_seg_btn.setCheckable(True)
        self._pick_seg_btn.setStyleSheet(_BOOL_BTN)
        self._pick_seg_btn.setToolTip("Pick Segments — manually select curve segments")
        self._pick_seg_btn.clicked.connect(
            lambda checked: self.action_requested.emit(
                "pick_segments_enter" if checked else "pick_segments_cancel"))
        layout.addWidget(self._pick_seg_btn)

        self._subtract_lbl = QLabel("")
        self._subtract_lbl.setStyleSheet(_SUBTRACT_LBL)
        self._subtract_lbl.setVisible(False)
        layout.addWidget(self._subtract_lbl)

        # ---- Pick-segments mode buttons (Apply / Cancel) ----
        self._ps_apply_btn = QPushButton("\u2713 Apply")
        self._ps_apply_btn.setFixedHeight(24)
        self._ps_apply_btn.setStyleSheet(_BOOL_APPLY_BTN)
        self._ps_apply_btn.setToolTip("Apply — create shapes from included segments")
        self._ps_apply_btn.clicked.connect(
            lambda: self.action_requested.emit("pick_segments_apply"))
        self._ps_apply_btn.setVisible(False)
        layout.addWidget(self._ps_apply_btn)

        self._ps_cancel_btn = QPushButton("\u2715 Cancel")
        self._ps_cancel_btn.setFixedHeight(24)
        self._ps_cancel_btn.setStyleSheet(_BOOL_CANCEL_BTN)
        self._ps_cancel_btn.setToolTip("Cancel — exit pick-segments mode")
        self._ps_cancel_btn.clicked.connect(
            lambda: self.action_requested.emit("pick_segments_cancel"))
        self._ps_cancel_btn.setVisible(False)
        layout.addWidget(self._ps_cancel_btn)

        layout.addStretch()

        self._fill_widgets = [lbl_fill, self._fill_btn]
        self._stroke_widgets = [lbl_stroke, self._stroke_btn, lbl_sw, self._stroke_w]
        self._shape_widgets = [self._shape_lbl, self._shape_combo,
                               self._param_a_lbl, self._param_a,
                               self._param_b_lbl, self._param_b,
                               self._sep_shape]
        self._node_widgets = [self._sharp_btn, self._smooth_btn,
                              self._symmetric_btn, self._sep_node_types,
                              self._delete_btn, self._break_btn,
                              self._selall_btn]
        self._bool_widgets = [
            self._sep_bool,
            self._bool_union_btn, self._bool_subtract_btn,
            self._bool_intersect_btn, self._bool_exclude_btn,
            self._bool_divide_btn,
            self._sep_bool2, self._pick_seg_btn,
            self._subtract_lbl,
        ]
        self._pick_seg_widgets = [self._ps_apply_btn, self._ps_cancel_btn]

        # Track pick-segments mode so set_mode can handle it
        self._in_pick_segments: bool = False

        from ...theme import ThemeManager
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _apply_theme(self, palette: dict) -> None:
        """Update dynamically rendered icons when the theme changes."""
        self._sharp_btn.setIcon(vector_node_icon("sharp"))
        self._smooth_btn.setIcon(vector_node_icon("smooth"))
        self._symmetric_btn.setIcon(vector_node_icon("symmetric"))
        self._delete_btn.setIcon(vector_node_icon("delete"))
        self._break_btn.setIcon(vector_node_icon("break"))
        self._selall_btn.setIcon(vector_node_icon("select_all"))

        self._bool_union_btn.setIcon(vector_bool_icon("union"))
        self._bool_subtract_btn.setIcon(vector_bool_icon("subtract"))
        self._bool_intersect_btn.setIcon(vector_bool_icon("intersect"))
        self._bool_exclude_btn.setIcon(vector_bool_icon("exclude"))
        self._bool_divide_btn.setIcon(vector_bool_icon("divide"))
        self._pick_seg_btn.setIcon(vector_bool_icon("pick_segments"))

    _SHAPE_PARAMS: dict[str, tuple[str, str]] = {
        "Rectangle":      ("Radius", ""),
        "Ellipse":        ("", ""),
        "Polygon":        ("Sides", ""),
        "Star":           ("Points", "Inner"),
        "Line":           ("", ""),
        "Triangle":       ("", ""),
        "Arrow":          ("Head", "Shaft"),
        "Heart":          ("", ""),
        "Diamond":        ("", ""),
        "Cross":          ("Arm", ""),
        "Ring":           ("Thick", ""),
        "Trapezoid":      ("Top", ""),
        "Parallelogram":  ("Skew", ""),
        "Crescent":       ("Offset", ""),
        "Speech Bubble":  ("Tail", ""),
    }

    def set_mode(self, mode: str) -> None:
        is_pen = mode == "pen"
        is_node = mode == "node"
        is_shape = mode == "shape"

        for w in self._fill_widgets:
            w.setVisible(is_pen or is_shape)
        for w in self._stroke_widgets:
            w.setVisible(is_pen or is_shape)
        for w in self._shape_widgets:
            w.setVisible(is_shape)
        for w in self._node_widgets:
            w.setVisible(is_node)
        for w in self._bool_widgets:
            w.setVisible(is_node and not self._in_pick_segments)
        for w in self._pick_seg_widgets:
            w.setVisible(is_node and self._in_pick_segments)

        if is_node:
            for w in self._fill_widgets + self._stroke_widgets:
                w.setVisible(True)

    def populate_shapes(self, shape_names: list[str]) -> None:
        self._shape_combo.blockSignals(True)
        self._shape_combo.clear()
        self._shape_combo.addItems(shape_names)
        self._shape_combo.blockSignals(False)

    def set_shape_type(self, name: str) -> None:
        self._shape_combo.blockSignals(True)
        idx = self._shape_combo.findText(name)
        if idx >= 0:
            self._shape_combo.setCurrentIndex(idx)
        self._shape_combo.blockSignals(False)
        self._update_param_labels(name)

    def _update_param_labels(self, shape_name: str) -> None:
        a, b = self._SHAPE_PARAMS.get(shape_name, ("", ""))
        self._param_a_lbl.setText(a)
        self._param_a_lbl.setVisible(bool(a))
        self._param_a.setVisible(bool(a))
        self._param_b_lbl.setText(b)
        self._param_b_lbl.setVisible(bool(b))
        self._param_b.setVisible(bool(b))

    def set_param_a(self, val: float) -> None:
        self._param_a.blockSignals(True)
        self._param_a.setValue(val)
        self._param_a.blockSignals(False)

    def set_param_b(self, val: float) -> None:
        self._param_b.blockSignals(True)
        self._param_b.setValue(val)
        self._param_b.blockSignals(False)

    def set_fill_color(self, r: float, g: float, b: float, a: float) -> None:
        self._fill_btn.set_color(Color(r, g, b, a))

    def set_fill_paint(self, paint: FillPaint) -> None:
        self._fill_btn.set_paint(paint)

    def set_fill_none(self, is_none: bool) -> None:
        """Reflect fill visibility state on the swatch button."""
        self._fill_btn.set_none(is_none)

    def set_stroke_color(self, r: float, g: float, b: float, a: float) -> None:
        self._stroke_btn.set_color(Color(r, g, b, a))

    def set_stroke_paint(self, paint: FillPaint) -> None:
        self._stroke_btn.set_paint(paint)

    def set_stroke_none(self, is_none: bool) -> None:
        """Reflect stroke visibility state on the swatch button."""
        self._stroke_btn.set_none(is_none)

    def set_stroke_width(self, val: float) -> None:
        self._stroke_w.blockSignals(True)
        self._stroke_w.setValue(val)
        self._stroke_w.blockSignals(False)

    def sync_from_tool(self, tool, mode: str, active_object=None) -> None:
        self.set_mode(mode)
        if mode in ("pen", "shape", "node"):
            fill_synced = False
            stroke_synced = False
            hit_obj = getattr(tool, "_hit_object", None)
            if hit_obj is None:
                hit_obj = active_object
            if hit_obj is not None and hasattr(hit_obj, "style"):
                style = hit_obj.style
                if style is not None:
                    fills = getattr(style, "fills", None)
                    if fills and len(fills) > 0:
                        fill = fills[0]
                        fill_paint = getattr(fill, "paint", None)
                        if fill_paint is not None:
                            self.set_fill_paint(fill_paint)
                            import copy
                            tool.fill_paint = copy.deepcopy(fill_paint)
                            fill_synced = True
                        # Reflect none state: fill exists but is invisible
                        self.set_fill_none(not getattr(fill, "visible", True))
                    else:
                        # No fill entries → treat as none
                        self.set_fill_none(True)
                    strokes = getattr(style, "strokes", None)
                    if strokes and len(strokes) > 0:
                        stroke = strokes[0]
                        stroke_paint = getattr(stroke, "paint", None)
                        if stroke_paint is not None:
                            self.set_stroke_paint(stroke_paint)
                            import copy
                            tool.stroke_paint = copy.deepcopy(stroke_paint)
                            stroke_synced = True
                        # Reflect none state: stroke exists but is invisible
                        self.set_stroke_none(not getattr(stroke, "visible", True))
                        sw = getattr(stroke, "width", None)
                        if sw is not None:
                            self.set_stroke_width(sw)
                            tool.stroke_width = sw
                    else:
                        # No stroke entries → treat as none
                        self.set_stroke_none(True)

            if not fill_synced:
                fp = getattr(tool, "fill_paint", None)
                if fp:
                    self.set_fill_paint(fp)
                else:
                    fc = getattr(tool, "fill_color", (0.7, 0.7, 0.9, 1.0))
                    self.set_fill_color(*fc)

            if not stroke_synced:
                sp = getattr(tool, "stroke_paint", None)
                if sp:
                    self.set_stroke_paint(sp)
                else:
                    sc = getattr(tool, "stroke_color", (0.0, 0.0, 0.0, 1.0))
                    self.set_stroke_color(*sc)

                sw = getattr(tool, "stroke_width", 2.0)
                self.set_stroke_width(sw)
        if mode == "shape":
            from ....vector.shape_tool import VectorShapeType
            names = [st.name.replace("_", " ").capitalize()
                     for st in VectorShapeType]
            self.populate_shapes(names)
            cur = getattr(tool, "shape_type", VectorShapeType.RECTANGLE)
            nice = cur.name.replace("_", " ").capitalize()
            self.set_shape_type(nice)
            self._sync_shape_params(tool, nice)

    def _sync_shape_params(self, tool, shape_name: str) -> None:
        _map_a = {
            "Rectangle": "corner_radius",
            "Polygon": "polygon_sides",
            "Star": "star_points",
            "Arrow": "arrow_head_length",
            "Cross": "cross_arm_ratio",
            "Ring": "ring_thickness",
            "Trapezoid": "trapezoid_top_ratio",
            "Parallelogram": "parallelogram_skew",
            "Crescent": "crescent_offset",
            "Speech bubble": "speech_tail_position",
        }
        _map_b = {
            "Star": "star_inner_ratio",
            "Arrow": "arrow_shaft_width",
        }
        attr_a = _map_a.get(shape_name, "")
        if attr_a:
            self.set_param_a(getattr(tool, attr_a, 0.0))
        attr_b = _map_b.get(shape_name, "")
        if attr_b:
            self.set_param_b(getattr(tool, attr_b, 0.0))

    def _on_fill_changed(self, color) -> None:
        self.property_changed.emit("fill_color",
            (color.r, color.g, color.b, color.a))

    def _on_stroke_changed(self, color) -> None:
        self.property_changed.emit("stroke_color",
            (color.r, color.g, color.b, color.a))

    def _on_fill_gradient_changed(self, fill_obj) -> None:
        paint = self._convert_to_vector_paint(fill_obj)
        self.property_changed.emit("fill_paint", paint)

    def _on_stroke_gradient_changed(self, fill_obj) -> None:
        paint = self._convert_to_vector_paint(fill_obj)
        self.property_changed.emit("stroke_paint", paint)

    # ---- Boolean state API ------------------------------------------------

    def _make_bool_btn(
        self, text: str, tooltip: str, action: str, layout: QHBoxLayout, icon_op: str = ""
    ) -> QPushButton:
        """Create a boolean-operation button with hover event filter."""
        btn = QPushButton(text)
        if icon_op:
            from PySide6.QtCore import QSize
            btn.setIcon(vector_bool_icon(icon_op))
            btn.setIconSize(QSize(16, 16))
        btn.setFixedHeight(24)
        btn.setStyleSheet(_BOOL_BTN)
        btn.setToolTip(tooltip)
        btn.setEnabled(False)  # starts disabled
        btn.clicked.connect(lambda: self.action_requested.emit(action))
        btn.installEventFilter(self)
        btn.setProperty("_bool_action", action)  # for hover detection
        layout.addWidget(btn)
        return btn

    def eventFilter(self, obj, event) -> bool:
        """Emit hover signal when mouse enters/leaves a boolean button."""
        action = obj.property("_bool_action") if obj else None
        if action and isinstance(action, str):
            if event.type() == QEvent.Type.Enter and obj.isEnabled():
                self.boolean_hover.emit(action)
            elif event.type() == QEvent.Type.Leave:
                self.boolean_hover_end.emit()
        return super().eventFilter(obj, event)

    def update_boolean_state(
        self,
        selected_count: int,
        top_name: str = "",
        bottom_name: str = "",
    ) -> None:
        """Enable/disable boolean buttons based on selection count."""
        has2 = selected_count >= 2
        self._bool_union_btn.setEnabled(has2)
        self._bool_subtract_btn.setEnabled(selected_count == 2)
        self._bool_intersect_btn.setEnabled(has2)
        self._bool_exclude_btn.setEnabled(selected_count == 2)
        self._bool_divide_btn.setEnabled(has2)
        self._pick_seg_btn.setEnabled(has2)

        self._subtract_lbl.setVisible(False)

    def enter_pick_segments(self) -> None:
        """Switch toolbar to pick-segments Apply/Cancel mode."""
        self._in_pick_segments = True
        self._pick_seg_btn.blockSignals(True)
        self._pick_seg_btn.setChecked(True)
        self._pick_seg_btn.blockSignals(False)
        # Hide normal node + boolean widgets
        for w in self._node_widgets + self._bool_widgets:
            w.setVisible(False)
        for w in self._fill_widgets + self._stroke_widgets:
            w.setVisible(False)
        # Show apply/cancel
        for w in self._pick_seg_widgets:
            w.setVisible(True)

    def exit_pick_segments(self) -> None:
        """Restore toolbar after leaving pick-segments mode."""
        self._in_pick_segments = False
        self._pick_seg_btn.blockSignals(True)
        self._pick_seg_btn.setChecked(False)
        self._pick_seg_btn.blockSignals(False)
        for w in self._pick_seg_widgets:
            w.setVisible(False)
        # Restore full node mode
        self.set_mode("node")

    def _convert_to_vector_paint(self, fill) -> FillPaint:
        if isinstance(fill, (LinearGradient, RadialGradient, ConicalGradient, DiamondGradient)):
            gtype = GradientType.LINEAR
            if isinstance(fill, RadialGradient):
                gtype = GradientType.RADIAL
            elif isinstance(fill, ConicalGradient):
                gtype = GradientType.CONICAL
            elif isinstance(fill, DiamondGradient):
                gtype = GradientType.DIAMOND

            stops = [
                VecGradientStop(s.position, (s.color.r, s.color.g, s.color.b, s.color.a))
                for s in fill.stops
            ]

            return GradientPaint(
                gradient_type=gtype,
                stops=stops,
            )
        return SolidPaint((0, 0, 0, 1))
