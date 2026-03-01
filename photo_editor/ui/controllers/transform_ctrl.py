"""Image transforms — flip, rotate, alignment, Move tool transform box."""

from __future__ import annotations

from ...core.enums import LayerType, ToolType
from ...transforms.transform_engine import TransformEngine


class TransformController:
    """Handles flip, rotate, and alignment/distribution from Move tool bar."""

    def __init__(self) -> None:
        self._mw = None

    def wire(self, main_window) -> None:
        """Connect to main window and wire menu/panel signals."""
        self._mw = main_window
        mw = main_window

        a = mw._menu.actions_map
        a["flip_h"].triggered.connect(lambda: self.on_transform("flip_h"))
        a["flip_v"].triggered.connect(lambda: self.on_transform("flip_v"))
        a["rotate_cw"].triggered.connect(lambda: self.on_transform("rotate_cw"))
        a["rotate_ccw"].triggered.connect(lambda: self.on_transform("rotate_ccw"))

        mw._props_panel.align_requested.connect(self.on_align_requested)

    def on_transform(self, op: str) -> None:
        if not self._mw._doc or not self._mw._doc.layers.active_layer:
            return
        layer = self._mw._doc.layers.active_layer
        if layer.locked:
            return
        self._mw._doc.save_snapshot(op.replace("_", " ").title())
        px = layer.pixels
        if op == "flip_h":
            layer.pixels = TransformEngine.flip_h(px)
        elif op == "flip_v":
            layer.pixels = TransformEngine.flip_v(px)
        elif op == "rotate_cw":
            layer.pixels = TransformEngine.rotate(px, -90)
        elif op == "rotate_ccw":
            layer.pixels = TransformEngine.rotate(px, 90)
        self._mw._refresh()

    def on_align_requested(self, action: str) -> None:
        """Handle alignment/distribution from the Move properties bar."""
        mw = self._mw
        if mw._doc is None:
            return
        from ...tools.move_tool import MoveTool
        method = getattr(MoveTool, action, None)
        if method is not None:
            method(mw._doc)
            mw._refresh()

    def update_transform_box(self) -> None:
        """Show transform bounding box when the Move tool is active."""
        mw = self._mw
        if mw._tools.active_type != ToolType.MOVE or not mw._doc:
            mw._canvas.set_transform_box(None)
            return
        layer = mw._doc.layers.active_layer
        if not layer:
            mw._canvas.set_transform_box(None)
            return

        # Multi-selection: display a union bounding box (with rotation)
        sel = mw._doc.layers.selected_indices
        if len(sel) > 1:
            from ...tools.move.hit_test import multi_bbox
            tool = mw._tools.active_tool
            angle = 0.0
            if tool is not None:
                angle = getattr(tool, '_current_angle', 0.0)

            # During an active rotation or resize drag, use the stored
            # original bbox so the visual box stays a fixed size and
            # rotates/scales with the drag instead of jittering.
            orig = getattr(tool, '_multi_orig_bbox', None) if tool else None
            if orig is not None and angle != 0.0:
                mw._canvas.set_transform_box(orig, angle)
            else:
                mb = multi_bbox(mw._doc)
                if mb:
                    mw._canvas.set_transform_box(mb, angle)
                else:
                    mw._canvas.set_transform_box(None)
            return

        if mw._doc.selection.active and mw._doc.selection._mask is not None:
            import numpy as np
            mask = mw._doc.selection._mask
            rows = np.any(mask > 0.5, axis=1)
            cols = np.any(mask > 0.5, axis=0)
            if np.any(rows) and np.any(cols):
                y0, y1 = int(np.where(rows)[0][0]), int(np.where(rows)[0][-1])
                x0, x1 = int(np.where(cols)[0][0]), int(np.where(cols)[0][-1])
                tool = mw._tools.active_tool
                fdx = fdy = 0
                if tool is not None and getattr(tool, '_floating', False):
                    fdx = getattr(tool, '_float_dx', 0)
                    fdy = getattr(tool, '_float_dy', 0)
                mw._canvas.set_transform_box(
                    (x0 + fdx, y0 + fdy, x1 - x0 + 1, y1 - y0 + 1))
            else:
                mw._canvas.set_transform_box(None)
            return

        if layer.layer_type == LayerType.GROUP:
            box = self._group_bbox(layer)
            mw._canvas.set_transform_box(box if box else None)
            return

        tool = mw._tools.active_tool
        info = None
        if hasattr(tool, "rotation_info_for"):
            info = tool.rotation_info_for(layer)
        if info is not None:
            bw, bh, angle = info
            lx, ly = layer.position
            cx = lx + layer.width / 2
            cy = ly + layer.height / 2
            box = (int(cx - bw / 2), int(cy - bh / 2), bw, bh)
            mw._canvas.set_transform_box(box, angle)
            return
        if layer.transform_angle != 0.0 and layer.transform_base_w > 0:
            bw = layer.transform_base_w
            bh = layer.transform_base_h
            lx, ly = layer.position
            cx = lx + layer.width / 2
            cy = ly + layer.height / 2
            box = (int(cx - bw / 2), int(cy - bh / 2), bw, bh)
            mw._canvas.set_transform_box(box, layer.transform_angle)
            return
        lx, ly = layer.position
        mw._canvas.set_transform_box((lx, ly, layer.width, layer.height))

    def _group_bbox(self, group) -> tuple[int, int, int, int] | None:
        """Compute bounding box for a group from its children."""
        mw = self._mw
        min_x, min_y = float("inf"), float("inf")
        max_x, max_y = float("-inf"), float("-inf")
        found = False
        for child in mw._doc.layers:
            if child.parent_id != group.id:
                continue
            cx, cy = child.position
            min_x = min(min_x, cx)
            min_y = min(min_y, cy)
            max_x = max(max_x, cx + child.width)
            max_y = max(max_y, cy + child.height)
            found = True
        if not found:
            return None
        return (int(min_x), int(min_y), int(max_x - min_x), int(max_y - min_y))
