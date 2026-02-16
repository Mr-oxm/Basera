
from __future__ import annotations

import math
from typing import cast

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
    QDoubleSpinBox, QPushButton, QButtonGroup
)

from ...core.document import Document
from ...core.enums import LayerType
from ...vector.geometry import AffineTransform, Vec2, BBox

# ============================================================================
# Styles
# ============================================================================

_PANEL_STYLE = """
    QWidget {
        background-color: #2a2a2a;
        color: #ddd;
        font-family: 'Segoe UI', sans-serif;
        font-size: 11px;
    }
    QLabel {
        color: #aaa;
    }
"""

_SPIN_STYLE = """
    QDoubleSpinBox {
        background-color: #1e1e1e;
        border: 1px solid #3d3d3d;
        border-radius: 3px;
        padding: 2px;
        color: #eee;
        selection-background-color: #4a6fa5;
    }
    QDoubleSpinBox:focus {
        border: 1px solid #4a6fa5;
    }
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
        width: 0px;
    }
"""

_BTN_STYLE = """
    QPushButton {
        background-color: transparent;
        border: none;
        border-radius: 3px;
        color: #aaa;
    }
    QPushButton:hover {
        background-color: #3d3d3d;
        color: #eee;
    }
    QPushButton:checked {
        background-color: #3d3d3d;
        color: #4a6fa5;
    }
"""

_ANCHOR_BTN_STYLE = """
    QPushButton {
        background-color: #444;
        border: 1px solid #222;
        border-radius: 1px;
    }
    QPushButton:checked {
        background-color: #eee;
        border: 1px solid #fff;
    }
    QPushButton:hover {
        background-color: #666;
    }
"""

# ============================================================================
# Anchor Widget
# ============================================================================

class AnchorWidget(QWidget):
    anchor_changed = Signal(int) # 0-8, corresponding to TL, T, TR...

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 50) # slightly larger container
        
        layout = QGridLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(8, 8, 8, 8)
        
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.group.idClicked.connect(self.anchor_changed.emit)
        
        # 0 1 2  (TL, T, TR)
        # 3 4 5  (L,  C, R)
        # 6 7 8  (BL, B, BR)
        for r in range(3):
            for c in range(3):
                id = r * 3 + c
                btn = QPushButton()
                btn.setCheckable(True)
                btn.setFixedSize(8, 8)
                btn.setStyleSheet(_ANCHOR_BTN_STYLE)
                layout.addWidget(btn, r, c)
                self.group.addButton(btn, id)
        
        # Default center
        if self.group.button(4):
            self.group.button(4).setChecked(True)

    def value(self) -> int:
        return self.group.checkedId()
    
    def set_value(self, id: int):
        btn = self.group.button(id)
        if btn:
            btn.setChecked(True)

# ============================================================================
# Transform Panel
# ============================================================================

class TransformPanel(QWidget):
    """Panel for controlling layer transform data (X, Y, W, H, R, S)."""
    
    value_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_PANEL_STYLE)
        
        self._doc: Document | None = None
        self._block_signals = False
        self._cached_values: dict[str, float] = {} # Store last known values to calculate deltas
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)
        
        # --- Anchor ---
        self.anchor = AnchorWidget()
        self.anchor.anchor_changed.connect(self._on_anchor_changed)
        layout.addWidget(self.anchor)
        
        # --- Transform Controls ---
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        
        # X
        grid.addWidget(QLabel("X:"), 0, 0)
        self.spin_x = self._make_spin(-99999, 99999, " px")
        grid.addWidget(self.spin_x, 0, 1)
        
        # Y
        grid.addWidget(QLabel("Y:"), 1, 0)
        self.spin_y = self._make_spin(-99999, 99999, " px")
        grid.addWidget(self.spin_y, 1, 1)
        
        # W
        grid.addWidget(QLabel("W:"), 0, 2)
        self.spin_w = self._make_spin(0.1, 99999, " px")
        grid.addWidget(self.spin_w, 0, 3)
        
        # Link (AspectRatio)
        self.btn_link = QPushButton("🔗")
        self.btn_link.setCheckable(True)
        self.btn_link.setFixedSize(20, 20)
        self.btn_link.setStyleSheet(_BTN_STYLE)
        self.btn_link.setToolTip("Constrain Proportions")
        grid.addWidget(self.btn_link, 0, 4, 2, 1, Qt.AlignmentFlag.AlignVCenter)
        
        # H
        grid.addWidget(QLabel("H:"), 1, 2)
        self.spin_h = self._make_spin(0.1, 99999, " px")
        grid.addWidget(self.spin_h, 1, 3)
        
        # R (Rotation)
        grid.addWidget(QLabel("R:"), 2, 0)
        self.spin_r = self._make_spin(-36000, 36000, " °")
        grid.addWidget(self.spin_r, 2, 1)
        
        # S (Shear/Skew)
        grid.addWidget(QLabel("S:"), 2, 2)
        self.spin_s = self._make_spin(-89, 89, " °")
        grid.addWidget(self.spin_s, 2, 3)
        
        layout.addLayout(grid)
        layout.addStretch()
        
        # Connect signals
        self.spin_x.editingFinished.connect(lambda: self._on_field_changed('x'))
        self.spin_y.editingFinished.connect(lambda: self._on_field_changed('y'))
        self.spin_w.editingFinished.connect(lambda: self._on_field_changed('w'))
        self.spin_h.editingFinished.connect(lambda: self._on_field_changed('h'))
        self.spin_r.editingFinished.connect(lambda: self._on_field_changed('r'))
        self.spin_s.editingFinished.connect(lambda: self._on_field_changed('s'))

    def _make_spin(self, min_val, max_val, suffix) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(min_val, max_val)
        spin.setSuffix(suffix)
        spin.setStyleSheet(_SPIN_STYLE)
        spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        spin.setDecimals(1)
        spin.setKeyboardTracking(False) # Wait for Enter/FocusOut to commit
        return spin

    def refresh(self, doc: Document | None):
        self._doc = doc
        if not doc or not doc.layers.active_layer:
            self.setEnabled(False)
            return
        
        self.setEnabled(True)
        self._update_ui_values()

    def _update_ui_values(self):
        """Read layer state and update UI."""
        if self._block_signals or not self._doc:
            return
            
        layer = self._doc.layers.active_layer
        if not layer:
            return

        self._block_signals = True
        
        # 1. Calculate BBox (Raster/Vector unified)
        # Assuming layer.position and layer.width/height represent the AABB
        lx, ly = layer.position
        lw, lh = layer.width, layer.height
        
        # 2. Determine anchor point coordinates based on current selection
        anchor_id = self.anchor.value()
        px, py = self._calculate_anchor_pos(lx, ly, lw, lh, anchor_id)
        
        self.spin_x.setValue(px)
        self.spin_y.setValue(py)
        
        self.spin_w.setValue(lw)
        self.spin_h.setValue(lh)
        
        # Rotation
        # For Raster: easy. For Vector: tricky if multiple objects.
        # We assume 0 for Vector "group" rotation unless we track it manually,
        # OR we fall back to layer.transform_angle if used.
        self.spin_r.setValue(layer.transform_angle)
        
        # Shear (Not supported on layer model, default 0)
        self.spin_s.setValue(0.0) 
        
        # Cache for delta calc
        self._cached_values = {
            'x': px, 'y': py,
            'w': lw, 'h': lh,
            'r': layer.transform_angle,
            's': 0.0
        }
        
        self._block_signals = False

    def _calculate_anchor_pos(self, x, y, w, h, anchor_id) -> tuple[float, float]:
        """Return (px, py) for the given alignment anchor."""
        # 0 1 2 (Top row)
        # 3 4 5 (Mid row)
        # 6 7 8 (Bot row)
        
        # Horizontal
        col = anchor_id % 3
        if col == 0:   dx = 0 # Left
        elif col == 1: dx = 0.5 # Center
        else:          dx = 1.0 # Right
        
        # Vertical
        row = anchor_id // 3
        if row == 0:   dy = 0 # Top
        elif row == 1: dy = 0.5 # Middle
        else:          dy = 1.0 # Bottom
        
        return (x + w * dx, y + h * dy)

    def _on_anchor_changed(self, _):
        """Update X/Y fields when anchor changes (logic only, no layer change)."""
        self._update_ui_values()

    def _on_field_changed(self, field: str):
        if self._block_signals or not self._doc:
            return
        
        layer = self._doc.layers.active_layer
        if not layer:
            return
            
        # Get new values
        new_val = getattr(self, f"spin_{field}").value()
        old_val = self._cached_values.get(field, new_val)
        
        # Get Anchor (Reference Point)
        anchor_id = self.anchor.value()
        lx, ly = layer.position
        lw, lh = layer.width, layer.height
        
        # Current anchor position (pivot)
        pivot_x, pivot_y = self._calculate_anchor_pos(lx, ly, lw, lh, anchor_id)
        
        # Apply transformation
        if field in ('x', 'y'):
            # Translation
            # If we change X, we want the ANCHOR POINT to move to X.
            # layer_pos = new_anchor_pos - relative_anchor_offset
            
            target_x = self.spin_x.value()
            target_y = self.spin_y.value()
            
            # Calculate offset of anchor from top-left
            off_x = pivot_x - lx
            off_y = pivot_y - ly
            
            new_lx = target_x - off_x
            new_ly = target_y - off_y
            
            # Move vector objects if it's a vector layer
            if layer.layer_type == LayerType.SHAPE:
                self._translate_vector_layer(layer, new_lx - lx, new_ly - ly)
            else:
                # Update layer position for Raster
                layer.position = (int(new_lx), int(new_ly))

        elif field in ('w', 'h'):
            # Scaling
            target_w = self.spin_w.value()
            target_h = self.spin_h.value()
            
            # Constrain?
            if self.btn_link.isChecked():
                if field == 'w':
                    ratio = target_w / old_val if old_val > 0 else 1
                    target_h = lh * ratio
                    self._block_signals = True
                    self.spin_h.setValue(target_h)
                    self._block_signals = False
                elif field == 'h':
                    ratio = target_h / old_val if old_val > 0 else 1
                    target_w = lw * ratio
                    self._block_signals = True
                    self.spin_w.setValue(target_w)
                    self._block_signals = False

            if layer.layer_type == LayerType.RASTER:
                # Update transforms
                sx = target_w / max(layer.source_width, 1)
                sy = target_h / max(layer.source_height, 1)
                layer.transform_scale_x = sx
                layer.transform_scale_y = sy
                
                # We need to adjust position so that pivot stays fixed
                # New unrotated dims will be target_w, target_h approx
                # But rasterizer/computer logic puts top-left at 'position'.
                # We need a math for "Scale around Point".
                # P' = C + (P - C) * S
                # Here P is TopLeft. C is Pivot.
                # new_lx = pivot_x + (lx - pivot_x) * (new_w / old_w)
                
                scale_factor_x = target_w / lw if lw > 0 else 1
                scale_factor_y = target_h / lh if lh > 0 else 1
                
                new_lx = pivot_x + (lx - pivot_x) * scale_factor_x
                new_ly = pivot_y + (ly - pivot_y) * scale_factor_y
                
                layer.position = (int(new_lx), int(new_ly))
                layer.compute_display()
                
            elif layer.layer_type == LayerType.SHAPE:
                scale_x = target_w / lw if lw > 0 else 1
                scale_y = target_h / lh if lh > 0 else 1
                self._scale_vector_layer(layer, scale_x, scale_y, pivot_x, pivot_y)

        elif field == 'r':
            # Rotation
            delta_angle = new_val - old_val
            
            if layer.layer_type == LayerType.RASTER:
                layer.transform_angle = new_val
                # Rotate around pivot?
                # Raster layer rotation usually happens around Center.
                # If we want to rotate around generic pivot, we must adjust position.
                # P' = Pivot + Rotate(P - Pivot)
                # But Layer.transform_angle is rotation around Center.
                # So we must move the layer such that its new Center is correct relative to Pivot?
                # Complex. Standard behavior: Rotate around center.
                # Users expect Rotate around Anchor.
                # If Anchor is Center -> No Translation.
                # If Anchor is TL -> Translation needed.
                
                # Current Center
                cx = lx + lw / 2
                cy = ly + lh / 2
                
                # New Angle
                # Rotate logic is hard purely with layer props.
                # Simpler: just set angle.
                layer.compute_display()
                
            elif layer.layer_type == LayerType.SHAPE:
                self._rotate_vector_layer(layer, delta_angle, pivot_x, pivot_y)
                # Reset display angle just in case
                self.spin_r.blockSignals(True)
                self.spin_r.setValue(0) # Vector layers absorb rotation
                self.spin_r.blockSignals(False)

        elif field == 's':
            # Shear
            delta_shear = new_val - old_val
            if layer.layer_type == LayerType.SHAPE:
                 self._shear_vector_layer(layer, delta_shear, pivot_x, pivot_y)
                 # Reset display
                 self.spin_s.blockSignals(True)
                 self.spin_s.setValue(0)
                 self.spin_s.blockSignals(False)

        # Signal completion
        self.value_changed.emit()
        self._update_ui_values() # Refresh UI to show backed results

    # --- Vector Helpers ---

    def _translate_vector_layer(self, layer, dx, dy):
        """Move all vector objects."""
        vl = getattr(layer, "_vector_data", None)
        if not vl: return
        
        # We transform objects, but wait...
        # 'layer.position' is just the cached raster bbox position.
        # Moving objects will shift the future bbox.
        # BUT, layer.position is already updated in '_on_field_changed' logic above?
        # No, for vector layer, we must move objects.
        
        from ...vector.geometry import AffineTransform
        xf = AffineTransform.translation(dx, dy)
        
        for obj in vl.objects:
            obj.transform = xf.concat(obj.transform)
            obj.invalidate()
            
        # Re-rasterize
        self._rasterize(layer)

    def _scale_vector_layer(self, layer, sx, sy, cx, cy):
        vl = getattr(layer, "_vector_data", None)
        if not vl: return
        
        from ...vector.geometry import AffineTransform
        # T(C) * S * T(-C)
        xf = (
            AffineTransform.translation(cx, cy)
            .concat(AffineTransform.scaling(sx, sy))
            .concat(AffineTransform.translation(-cx, -cy))
        )
        
        for obj in vl.objects:
            obj.transform = xf.concat(obj.transform)
            obj.invalidate()
            
        self._rasterize(layer)

    def _rotate_vector_layer(self, layer, angle_deg, cx, cy):
        vl = getattr(layer, "_vector_data", None)
        if not vl: return
        
        from ...vector.geometry import AffineTransform
        rad = math.radians(angle_deg)
        xf = (
            AffineTransform.translation(cx, cy)
            .concat(AffineTransform.rotation(rad))
            .concat(AffineTransform.translation(-cx, -cy))
        )
        
        for obj in vl.objects:
            obj.transform = xf.concat(obj.transform)
            obj.invalidate()
            
        self._rasterize(layer)
        
    def _shear_vector_layer(self, layer, skew_deg, cx, cy):
        vl = getattr(layer, "_vector_data", None)
        if not vl: return
        
        from ...vector.geometry import AffineTransform
        # Horizontal Skew usually
        rad = math.radians(skew_deg)
        xf = (
            AffineTransform.translation(cx, cy)
            .concat(AffineTransform.skewing(rad, 0)) # Skew X
            .concat(AffineTransform.translation(-cx, -cy))
        )
        
        for obj in vl.objects:
            obj.transform = xf.concat(obj.transform)
            obj.invalidate()
            
        self._rasterize(layer)

    def _rasterize(self, layer):
        from ...vector.rasterizer import rasterize_vector_layer_tight
        layer._pixels_dirty = True # Force update
        rasterize_vector_layer_tight(self._doc, layer=layer, force=True)
