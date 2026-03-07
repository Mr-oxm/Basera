"""Crop tool — canvas/layer crop, properties bar."""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QMessageBox

from ...core.enums import LayerType
from .base import ControllerBase


class CropController(ControllerBase):
    """Handles crop tool setup, overlay, apply/cancel, and canvas/layer crop."""

    def __init__(self) -> None:
        super().__init__()

    def wire(self, main_window) -> None:
        """Connect to main window and wire panel signals."""
        super().wire(main_window)
        mw = self.mw

        mw._props_panel.crop_property_changed.connect(self.on_crop_prop_changed)
        mw._props_panel.crop_apply.connect(self.on_crop_apply)
        mw._props_panel.crop_cancel.connect(self.on_crop_cancel)

    def setup(self) -> None:
        """Wire callbacks for the crop tool (called when crop tool is selected)."""
        mw = self.mw
        tool = mw._tools.active_tool
        if tool is None:
            return
        tool.set_overlay_callback(self.on_crop_overlay)
        tool.set_crop_callback(self.on_crop_execute)
        tool.set_cancel_callback(lambda: mw._canvas.set_crop_box(None))
        if self.doc is not None:
            tool.auto_box_for_layer(self.doc)
            mw._props_panel.crop_bar.sync_from_tool(tool)

    def on_crop_overlay(self, box) -> None:
        mw = self.mw
        mw._canvas.set_crop_box(box)
        if box is not None:
            mw._props_panel.crop_bar.set_dimensions(*box)
        else:
            mw._props_panel.crop_bar.clear_dimensions()

    def on_crop_prop_changed(self, key: str, value: object) -> None:
        from ...core.enums import ToolType
        mw = self.mw
        tool = mw._tools.active_tool
        if tool is None or mw._tools.active_type != ToolType.CROP:
            return
        if key == "crop_mode":
            from ...tools.crop_tool import CropMode
            tool.mode = CropMode.CANVAS if value == "canvas" else CropMode.LAYER

    def on_crop_apply(self) -> None:
        mw = self.mw
        from ...core.enums import ToolType
        tool = mw._tools.active_tool
        if tool is None or mw._tools.active_type != ToolType.CROP:
            return
        if self.doc is None:
            return
        tool.apply(self.doc)

    def on_crop_cancel(self) -> None:
        mw = self.mw
        from ...core.enums import ToolType
        tool = mw._tools.active_tool
        if tool is None or mw._tools.active_type != ToolType.CROP:
            return
        tool.cancel()

    def on_crop_execute(self, x: int, y: int, w: int, h: int, mode) -> None:
        from ...tools.crop_tool import CropMode
        if self.doc is None:
            return
        if mode == CropMode.CANVAS:
            self.crop_canvas(x, y, w, h)
        else:
            self.crop_layer(x, y, w, h)

    def crop_canvas(self, x: int, y: int, w: int, h: int) -> None:
        doc = self.doc
        if doc is None:
            return
        doc.save_snapshot("Crop Canvas")
        for layer in doc.layers:
            px, py = layer.position
            layer.position = (px - x, py - y)
        doc.resize(w, h)
        self.ctx.refresh()

    def crop_layer(self, x: int, y: int, w: int, h: int) -> None:
        mw = self.mw
        doc = self.doc
        if doc is None:
            return
        layer = doc.layers.active_layer
        if layer is None:
            return
        if layer.layer_type != LayerType.RASTER:
            reply = QMessageBox.warning(
                mw,
                "Rasterize Layer",
                "This layer must be rasterized before it can be cropped.\n"
                "Once rasterized the layer will no longer be editable "
                "in its original form.\n\nRasterize the layer?",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Ok:
                return
            doc.save_snapshot(f"Rasterize {layer.name}")
            layer.layer_type = LayerType.RASTER
            if hasattr(layer, "_text_data"):
                try:
                    del layer._text_data
                except AttributeError:
                    layer._text_data = None
            layer.rasterize_transform()
        doc.save_snapshot("Crop Layer")
        px, py = layer.position
        lh, lw = layer.pixels.shape[:2]
        sy0 = max(0, y - py)
        sx0 = max(0, x - px)
        sy1 = min(lh, y + h - py)
        sx1 = min(lw, x + w - px)
        if sy1 > sy0 and sx1 > sx0:
            cropped = layer.pixels[sy0:sy1, sx0:sx1].copy()
        else:
            cropped = np.zeros((max(1, h), max(1, w), 4), dtype=np.float32)
        layer.pixels = cropped
        layer.position = (x, y)
        # Clear stale non-destructive transform source so the bounding box
        # matches the new cropped pixels and subsequent transforms operate
        # on the cropped data instead of reverting to the pre-crop image.
        layer.rasterize_transform()
        self.ctx.refresh()
