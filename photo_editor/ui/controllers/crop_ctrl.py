"""Crop tool — canvas/layer crop, properties bar."""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QMessageBox

from ...core.enums import LayerType


class CropController:
    """Handles crop tool setup, overlay, apply/cancel, and canvas/layer crop."""

    def __init__(self) -> None:
        self._mw = None

    def wire(self, main_window) -> None:
        """Connect to main window and wire panel signals."""
        self._mw = main_window
        mw = main_window

        mw._props_panel.crop_property_changed.connect(self.on_crop_prop_changed)
        mw._props_panel.crop_apply.connect(self.on_crop_apply)
        mw._props_panel.crop_cancel.connect(self.on_crop_cancel)

    def setup(self) -> None:
        """Wire callbacks for the crop tool (called when crop tool is selected)."""
        mw = self._mw
        tool = mw._tools.active_tool
        if tool is None:
            return
        tool.set_overlay_callback(self.on_crop_overlay)
        tool.set_crop_callback(self.on_crop_execute)
        tool.set_cancel_callback(lambda: mw._canvas.set_crop_box(None))
        if mw._doc is not None:
            tool.auto_box_for_layer(mw._doc)
            mw._props_panel.crop_bar.sync_from_tool(tool)

    def on_crop_overlay(self, box) -> None:
        mw = self._mw
        mw._canvas.set_crop_box(box)
        if box is not None:
            mw._props_panel.crop_bar.set_dimensions(*box)
        else:
            mw._props_panel.crop_bar.clear_dimensions()

    def on_crop_prop_changed(self, key: str, value: object) -> None:
        from ...core.enums import ToolType
        mw = self._mw
        tool = mw._tools.active_tool
        if tool is None or mw._tools.active_type != ToolType.CROP:
            return
        if key == "crop_mode":
            from ...tools.crop_tool import CropMode
            tool.mode = CropMode.CANVAS if value == "canvas" else CropMode.LAYER

    def on_crop_apply(self) -> None:
        mw = self._mw
        from ...core.enums import ToolType
        tool = mw._tools.active_tool
        if tool is None or mw._tools.active_type != ToolType.CROP:
            return
        if mw._doc is None:
            return
        tool.apply(mw._doc)

    def on_crop_cancel(self) -> None:
        mw = self._mw
        from ...core.enums import ToolType
        tool = mw._tools.active_tool
        if tool is None or mw._tools.active_type != ToolType.CROP:
            return
        tool.cancel()

    def on_crop_execute(self, x: int, y: int, w: int, h: int, mode) -> None:
        from ...tools.crop_tool import CropMode
        mw = self._mw
        if mw._doc is None:
            return
        if mode == CropMode.CANVAS:
            self.crop_canvas(x, y, w, h)
        else:
            self.crop_layer(x, y, w, h)

    def crop_canvas(self, x: int, y: int, w: int, h: int) -> None:
        mw = self._mw
        doc = mw._doc
        if doc is None:
            return
        doc.save_snapshot("Crop Canvas")
        for layer in doc.layers:
            px, py = layer.position
            layer.position = (px - x, py - y)
        doc.resize(w, h)
        mw._refresh()

    def crop_layer(self, x: int, y: int, w: int, h: int) -> None:
        mw = self._mw
        doc = mw._doc
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
        mw._refresh()
