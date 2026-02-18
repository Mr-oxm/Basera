"""Vector tool properties bar — Pen / Node / Shape tools."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QWidget,
)

from ...widgets.color_dropdown import ColorDropdown
from ....core.color import Color, LinearGradient, RadialGradient
from ....core.color_engine import ConicalGradient, DiamondGradient
from ....vector.style import FillPaint, SolidPaint, GradientPaint, GradientType, GradientStop as VecGradientStop
from .base import ACCENT, COMBO, FLAT_BTN, LABEL, SPIN, make_separator


class VectorPropertiesBar(QWidget):
    """Horizontal bar that adapts to the active vector tool: Pen, Node, or Shape."""

    from PySide6.QtCore import Signal
    property_changed = Signal(str, object)
    action_requested = Signal(str)

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
        self._fill_btn = ColorDropdown(show_gradient=True, parent=self)
        self._fill_btn.setFixedSize(36, 24)
        self._fill_btn.color_changed.connect(self._on_fill_changed)
        self._fill_btn.color_committed.connect(self._on_fill_changed)
        self._fill_btn.gradient_changed.connect(self._on_fill_gradient_changed)
        layout.addWidget(self._fill_btn)

        layout.addSpacing(4)

        lbl_stroke = QLabel("Stroke")
        lbl_stroke.setStyleSheet(LABEL)
        layout.addWidget(lbl_stroke)
        self._stroke_btn = ColorDropdown(show_gradient=True, parent=self)
        self._stroke_btn.setFixedSize(36, 24)
        self._stroke_btn.color_changed.connect(self._on_stroke_changed)
        self._stroke_btn.color_committed.connect(self._on_stroke_changed)
        self._stroke_btn.gradient_changed.connect(self._on_stroke_gradient_changed)
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

        btn_css = FLAT_BTN.format()

        self._sharp_btn = QPushButton("■ Sharp")
        self._sharp_btn.setFixedHeight(24)
        self._sharp_btn.setStyleSheet(btn_css)
        self._sharp_btn.setToolTip("Set selected nodes to sharp (straight)")
        self._sharp_btn.clicked.connect(lambda: self.action_requested.emit("set_sharp"))
        layout.addWidget(self._sharp_btn)

        self._smooth_btn = QPushButton("● Smooth")
        self._smooth_btn.setFixedHeight(24)
        self._smooth_btn.setStyleSheet(btn_css)
        self._smooth_btn.setToolTip("Set selected nodes to smooth (collinear handles)")
        self._smooth_btn.clicked.connect(lambda: self.action_requested.emit("set_smooth"))
        layout.addWidget(self._smooth_btn)

        self._symmetric_btn = QPushButton("◆ Symmetric")
        self._symmetric_btn.setFixedHeight(24)
        self._symmetric_btn.setStyleSheet(btn_css)
        self._symmetric_btn.setToolTip("Set selected nodes to symmetric (equal handles)")
        self._symmetric_btn.clicked.connect(lambda: self.action_requested.emit("set_symmetric"))
        layout.addWidget(self._symmetric_btn)

        self._sep_node_types = make_separator()
        layout.addWidget(self._sep_node_types)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setFixedHeight(24)
        self._delete_btn.setStyleSheet(btn_css)
        self._delete_btn.setToolTip("Delete selected nodes (or whole object)")
        self._delete_btn.clicked.connect(lambda: self.action_requested.emit("delete_nodes"))
        layout.addWidget(self._delete_btn)

        self._break_btn = QPushButton("Break")
        self._break_btn.setFixedHeight(24)
        self._break_btn.setStyleSheet(btn_css)
        self._break_btn.setToolTip("Break path at selected nodes")
        self._break_btn.clicked.connect(lambda: self.action_requested.emit("break_path"))
        layout.addWidget(self._break_btn)

        self._selall_btn = QPushButton("Sel All")
        self._selall_btn.setFixedHeight(24)
        self._selall_btn.setStyleSheet(btn_css)
        self._selall_btn.setToolTip("Select all nodes (Ctrl+A)")
        self._selall_btn.clicked.connect(lambda: self.action_requested.emit("select_all"))
        layout.addWidget(self._selall_btn)

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

    def set_stroke_color(self, r: float, g: float, b: float, a: float) -> None:
        self._stroke_btn.set_color(Color(r, g, b, a))

    def set_stroke_paint(self, paint: FillPaint) -> None:
        self._stroke_btn.set_paint(paint)

    def set_stroke_width(self, val: float) -> None:
        self._stroke_w.blockSignals(True)
        self._stroke_w.setValue(val)
        self._stroke_w.blockSignals(False)

    def sync_from_tool(self, tool, mode: str) -> None:
        self.set_mode(mode)
        if mode in ("pen", "shape", "node"):
            fill_synced = False
            stroke_synced = False
            hit_obj = getattr(tool, "_hit_object", None)
            if hit_obj is not None and hasattr(hit_obj, "style"):
                style = hit_obj.style
                if style is not None:
                    fill = getattr(style, "fill", None)
                    if fill is not None:
                        fill_paint = getattr(fill, "paint", None)
                        if fill_paint is not None:
                            self.set_fill_paint(fill_paint)
                            fill_synced = True
                    stroke = getattr(style, "stroke", None)
                    if stroke is not None:
                        stroke_paint = getattr(stroke, "paint", None)
                        if stroke_paint is not None:
                            self.set_stroke_paint(stroke_paint)
                            stroke_synced = True
                        sw = getattr(stroke, "width", None)
                        if sw is not None:
                            self.set_stroke_width(sw)

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
