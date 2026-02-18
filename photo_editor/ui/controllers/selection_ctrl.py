"""Selection operations — select all, feather, grow, fill, cut/copy/paste."""

from __future__ import annotations

from PySide6.QtWidgets import QInputDialog


class SelectionController:
    """Handles selection modify, fill, cut/copy/paste, and selection-to-mask."""

    def __init__(self) -> None:
        self._mw = None

    def wire(self, main_window) -> None:
        """Connect to main window and wire menu/panel signals."""
        self._mw = main_window
        mw = main_window

        # Menu
        a = mw._menu.actions_map
        a["select_all"].triggered.connect(self.on_select_all)
        a["deselect"].triggered.connect(self.on_deselect)
        a["invert_sel"].triggered.connect(self.on_invert_sel)
        a["feather_sel"].triggered.connect(self.on_feather_sel)
        a["grow_sel"].triggered.connect(self.on_grow_sel)
        a["shrink_sel"].triggered.connect(self.on_shrink_sel)
        a["delete_sel"].triggered.connect(self.on_delete_selection)
        a["fill_fg"].triggered.connect(lambda: self.on_fill_selection("fg"))
        a["fill_bg"].triggered.connect(lambda: self.on_fill_selection("bg"))
        a["cut"].triggered.connect(self.on_cut)
        a["copy"].triggered.connect(self.on_copy)
        a["paste"].triggered.connect(self.on_paste)
        a["duplicate_sel"].triggered.connect(self.on_duplicate_selection)
        a["selection_to_mask"].triggered.connect(self.on_selection_to_mask)

        # Props panel selection bar
        mw._props_panel.selection_property_changed.connect(self.on_sel_prop_changed)
        mw._props_panel.selection_action.connect(self.on_sel_action)

    def update_selection_overlay(self) -> None:
        mw = self._mw
        if mw._doc and mw._doc.selection._mask is not None:
            if mw._doc.selection._mask.max() > 0:
                mw._canvas.set_selection_mask(mw._doc.selection._mask)
                return
        mw._canvas.set_selection_mask(None)

    def extract_layer_mask(self, doc_mask, lx: int, ly: int, w: int, h: int):
        """Extract the portion of the doc-level selection mask that overlaps the layer."""
        import numpy as np
        dh, dw = doc_mask.shape[:2]
        dst_y1 = max(0, ly)
        dst_y2 = min(dh, ly + h)
        dst_x1 = max(0, lx)
        dst_x2 = min(dw, lx + w)
        if dst_y2 <= dst_y1 or dst_x2 <= dst_x1:
            return None
        layer_mask = np.zeros((h, w), dtype=np.float32)
        src_y1 = dst_y1 - ly
        src_y2 = dst_y2 - ly
        src_x1 = dst_x1 - lx
        src_x2 = dst_x2 - lx
        layer_mask[src_y1:src_y2, src_x1:src_x2] = doc_mask[dst_y1:dst_y2, dst_x1:dst_x2]
        return layer_mask

    def on_select_all(self) -> None:
        if self._mw._doc:
            self._mw._doc.selection.select_all()
            self.update_selection_overlay()

    def on_deselect(self) -> None:
        if self._mw._doc:
            self._mw._doc.selection.deselect()
            self.update_selection_overlay()

    def on_invert_sel(self) -> None:
        if self._mw._doc:
            self._mw._doc.selection.invert()
            self.update_selection_overlay()

    def on_feather_sel(self) -> None:
        if not self._mw._doc or not self._mw._doc.selection.active:
            return
        radius, ok = QInputDialog.getInt(
            self._mw, "Feather Selection", "Feather radius (px):", 5, 1, 250
        )
        if ok:
            self._mw._doc.selection.feather(radius)
            self.update_selection_overlay()

    def on_grow_sel(self) -> None:
        if not self._mw._doc or not self._mw._doc.selection.active:
            return
        pixels, ok = QInputDialog.getInt(
            self._mw, "Grow Selection", "Grow by (px):", 5, 1, 250
        )
        if ok:
            self._mw._doc.selection.grow(pixels)
            self.update_selection_overlay()

    def on_shrink_sel(self) -> None:
        if not self._mw._doc or not self._mw._doc.selection.active:
            return
        pixels, ok = QInputDialog.getInt(
            self._mw, "Shrink Selection", "Shrink by (px):", 5, 1, 250
        )
        if ok:
            self._mw._doc.selection.shrink(pixels)
            self.update_selection_overlay()

    def on_delete_selection(self) -> None:
        mw = self._mw
        if not mw._doc:
            return
        layer = mw._doc.layers.active_layer
        if layer is None:
            return
        mask = mw._doc.selection._mask
        if mask is None:
            return
        mw._doc._snapshot("Delete Selection")
        lx, ly = layer.position
        h, w = layer.pixels.shape[:2]
        layer_mask = self.extract_layer_mask(mask, lx, ly, w, h)
        if layer_mask is not None:
            layer.pixels[..., 3] *= (1.0 - layer_mask)
        mw._refresh()

    def on_fill_selection(self, which: str) -> None:
        mw = self._mw
        if not mw._doc:
            return
        layer = mw._doc.layers.active_layer
        if layer is None:
            return
        import numpy as np

        if which == "fg":
            color = mw._color_panel._mgr.foreground.to_array()
        else:
            color = mw._color_panel._mgr.background.to_array()
        if len(color) < 4:
            color = np.array([*color[:3], 1.0], dtype=np.float32)
        mw._doc._snapshot("Fill Selection")
        mask = mw._doc.selection._mask
        lx, ly = layer.position
        h, w = layer.pixels.shape[:2]
        if mask is not None:
            layer_mask = self.extract_layer_mask(mask, lx, ly, w, h)
            if layer_mask is not None:
                for c in range(4):
                    layer.pixels[..., c] = (
                        layer.pixels[..., c] * (1.0 - layer_mask)
                        + color[c] * layer_mask
                    )
        else:
            layer.pixels[..., :] = color
        mw._refresh()

    def on_cut(self) -> None:
        self.on_copy()
        self.on_delete_selection()

    def on_copy(self) -> None:
        mw = self._mw
        if not mw._doc:
            return
        layer = mw._doc.layers.active_layer
        if layer is None:
            return
        mask = mw._doc.selection._mask
        lx, ly = layer.position
        h, w = layer.pixels.shape[:2]
        if mask is not None:
            layer_mask = self.extract_layer_mask(mask, lx, ly, w, h)
            if layer_mask is None:
                return
            copied = layer.pixels.copy()
            copied[..., 3] *= layer_mask
        else:
            copied = layer.pixels.copy()
        mw._clipboard = copied.copy()
        mw._clipboard_pos = (lx, ly)
        mw._status.showMessage("Copied to clipboard", 2000)

    def on_paste(self) -> None:
        mw = self._mw
        if not hasattr(mw, "_clipboard") or mw._clipboard is None:
            return
        if not mw._doc:
            return
        from ...core.layer import Layer

        new_layer = Layer(
            name="Pasted Layer",
            width=mw._clipboard.shape[1],
            height=mw._clipboard.shape[0],
        )
        new_layer.pixels = mw._clipboard.copy()
        if hasattr(mw, "_clipboard_pos"):
            new_layer.position = list(mw._clipboard_pos)
        mw._doc._snapshot("Paste")
        mw._doc.layers.add(new_layer)
        mw._refresh()

    def on_duplicate_selection(self) -> None:
        mw = self._mw
        if not mw._doc or not mw._doc.selection.active:
            return
        layer = mw._doc.layers.active_layer
        if layer is None:
            return
        import numpy as np
        from ...core.layer import Layer

        mask = mw._doc.selection._mask
        lx, ly = layer.position
        h, w = layer.pixels.shape[:2]
        layer_mask = self.extract_layer_mask(mask, lx, ly, w, h)
        if layer_mask is None:
            return
        copied = layer.pixels.copy()
        copied[..., 3] *= layer_mask
        alpha = copied[..., 3]
        rows = np.any(alpha > 0, axis=1)
        cols = np.any(alpha > 0, axis=0)
        if not np.any(rows) or not np.any(cols):
            return
        y0, y1 = np.where(rows)[0][[0, -1]]
        x0, x1 = np.where(cols)[0][[0, -1]]
        cropped = copied[y0 : y1 + 1, x0 : x1 + 1].copy()
        new_layer = Layer(
            name=f"{layer.name} copy",
            width=cropped.shape[1],
            height=cropped.shape[0],
        )
        new_layer.pixels = cropped
        new_layer.position = [lx + int(x0), ly + int(y0)]
        mw._doc._snapshot("Duplicate Selection")
        mw._doc.layers.add(new_layer)
        mw._refresh()
        mw._status.showMessage("Duplicated selection to new layer", 2000)

    def on_selection_to_mask(self) -> None:
        if not self._mw._doc:
            return
        if self._mw._doc.selection.active:
            self._mw._doc.selection_to_mask_layer()
            self._mw._refresh()

    def on_sel_prop_changed(self, key: str, value: object) -> None:
        tool = self._mw._tools.active_tool
        if tool is None:
            return
        if key == "mode" and hasattr(tool, "mode"):
            tool.mode = str(value)
        elif key == "feather" and hasattr(tool, "feather"):
            tool.feather = int(value)
        elif key == "tolerance" and hasattr(tool, "tolerance"):
            tool.tolerance = int(value)
        elif key == "contiguous" and hasattr(tool, "contiguous"):
            tool.contiguous = bool(value)

    def on_sel_action(self, action: str) -> None:
        if action == "delete":
            self.on_delete_selection()
        elif action == "fill_fg":
            self.on_fill_selection("fg")
        elif action == "fill_bg":
            self.on_fill_selection("bg")
        elif action == "duplicate":
            self.on_duplicate_selection()
        elif action == "invert":
            self.on_invert_sel()
        elif action == "deselect":
            self.on_deselect()
