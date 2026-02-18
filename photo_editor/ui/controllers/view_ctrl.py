"""View state — zoom, pan, rulers, guides, grid."""

from __future__ import annotations

from PySide6.QtCore import QPointF


class ViewController:
    """Handles zoom, pan, view toggles (grid/rulers/guides), and guide management."""

    def __init__(self) -> None:
        self._mw = None

    def wire(self, main_window) -> None:
        """Connect to main window and wire menu/panel/canvas signals."""
        self._mw = main_window
        mw = main_window

        # Menu: zoom and view toggles
        a = mw._menu.actions_map
        a["zoom_in"].triggered.connect(lambda: self.on_zoom(1.25))
        a["zoom_out"].triggered.connect(lambda: self.on_zoom(1 / 1.25))
        a["zoom_fit"].triggered.connect(self.on_zoom_fit)
        a["zoom_100"].triggered.connect(self.on_zoom_100)
        a["toggle_grid"].triggered.connect(self.on_toggle_grid)
        a["toggle_rulers"].triggered.connect(self.on_toggle_rulers)
        a["toggle_guides"].triggered.connect(self.on_toggle_guides)

        # Props panel zoom bar
        mw._props_panel.zoom_action.connect(self.on_zoom_action)

        # Ruler guide signals (rulers created in _build_ui)
        for ruler in (mw._h_ruler, mw._v_ruler):
            ruler.guide_created.connect(self.on_guide_created)
            ruler.guide_moved.connect(self.on_guide_moved)
            ruler.guide_deleted.connect(self.on_guide_deleted)

        # Canvas guide drag
        mw._canvas.guide_drag_moved.connect(self.on_canvas_guide_drag_moved)
        mw._canvas.guide_drag_released.connect(self.on_canvas_guide_drag_released)

    def on_zoom(self, factor: float) -> None:
        mw = self._mw
        mw._canvas.set_zoom(mw._canvas.zoom * factor)
        mw._status.set_zoom(mw._canvas.zoom)
        self.update_rulers()

    def on_zoom_fit(self) -> None:
        mw = self._mw
        mw._canvas.zoom_to_fit()
        mw._status.set_zoom(mw._canvas.zoom)

    def on_zoom_100(self) -> None:
        mw = self._mw
        mw._canvas.set_zoom(1.0)
        mw._status.set_zoom(1.0)

    def on_zoom_action(self, action: str) -> None:
        """Handle zoom actions from the zoom properties bar."""
        mw = self._mw
        canvas = mw._canvas
        if action == "zoom_in":
            canvas.set_zoom(canvas.zoom * 1.5)
        elif action == "zoom_out":
            canvas.set_zoom(canvas.zoom / 1.5)
        elif action == "fit":
            if mw._doc:
                vw = canvas.width()
                vh = canvas.height()
                scale = min(vw / mw._doc.width, vh / mw._doc.height) * 0.95
                canvas.set_zoom(scale)
                canvas._pan = QPointF(0, 0)
                canvas.update()
        elif action == "reset":
            canvas.set_zoom(1.0)
            canvas._pan = QPointF(0, 0)
            canvas.update()
        mw._status.set_zoom(canvas.zoom)

    def on_zoom_tool(self, factor: float) -> None:
        """Called when the zoom tool requests a zoom change."""
        mw = self._mw
        mw._canvas.set_zoom(mw._canvas.zoom * factor)
        mw._status.set_zoom(mw._canvas.zoom)
        self.update_rulers()

    def on_pan_tool(self, dx_screen: float, dy_screen: float) -> None:
        """Called when the pan tool requests a pan delta (screen pixels)."""
        canvas = self._mw._canvas
        canvas._pan += QPointF(dx_screen, dy_screen)
        canvas.update()

    def on_toggle_grid(self) -> None:
        mw = self._mw
        mw._show_grid = not getattr(mw, "_show_grid", False)
        state = "on" if mw._show_grid else "off"
        mw.statusBar().showMessage(f"Grid {state} (not yet implemented)", 2000)

    def on_toggle_rulers(self) -> None:
        mw = self._mw
        mw._rulers_visible = not mw._rulers_visible
        mw._ruler_corner.setVisible(mw._rulers_visible)
        mw._h_ruler.setVisible(mw._rulers_visible)
        mw._v_ruler.setVisible(mw._rulers_visible)
        state = "on" if mw._rulers_visible else "off"
        mw.statusBar().showMessage(f"Rulers {state}", 2000)

    def on_toggle_guides(self) -> None:
        mw = self._mw
        mw._show_guides = not getattr(mw, "_show_guides", True)
        mw._canvas.set_guides(mw._guides if mw._show_guides else [])
        state = "on" if mw._show_guides else "off"
        mw.statusBar().showMessage(f"Guides {state}", 2000)

    def on_guide_created(self, guide) -> None:
        mw = self._mw
        mw._guides.append(guide)
        mw._canvas.set_preview_guide(None)
        mw._canvas.set_guides(mw._guides)
        mw._h_ruler.set_guides(mw._guides)
        mw._v_ruler.set_guides(mw._guides)

    def on_guide_moved(self, guide, new_pos: float) -> None:
        mw = self._mw
        guide.position = new_pos
        if guide not in mw._guides:
            mw._canvas.set_preview_guide(guide)
        else:
            mw._canvas.set_guides(mw._guides)
        mw._h_ruler.set_guides(mw._guides)
        mw._v_ruler.set_guides(mw._guides)

    def on_guide_deleted(self, guide) -> None:
        mw = self._mw
        if guide in mw._guides:
            mw._guides.remove(guide)
        mw._canvas.set_preview_guide(None)
        mw._canvas.set_guides(mw._guides)
        mw._h_ruler.set_guides(mw._guides)
        mw._v_ruler.set_guides(mw._guides)

    def on_canvas_guide_drag_moved(self, guide, new_pos: float) -> None:
        mw = self._mw
        guide.position = new_pos
        mw._canvas.set_guides(mw._guides)
        mw._h_ruler.set_guides(mw._guides)
        mw._v_ruler.set_guides(mw._guides)

    def on_canvas_guide_drag_released(self, guide, pos: float, delete: bool) -> None:
        mw = self._mw
        if delete:
            if guide in mw._guides:
                mw._guides.remove(guide)
        else:
            guide.position = pos
        mw._canvas.set_guides(mw._guides)
        mw._h_ruler.set_guides(mw._guides)
        mw._v_ruler.set_guides(mw._guides)

    def update_rulers(self) -> None:
        """Sync rulers with current canvas zoom/pan state."""
        mw = self._mw
        if not hasattr(mw, '_h_ruler') or not mw._rulers_visible:
            return
        dr = mw._canvas._doc_rect()
        dw = mw._canvas._doc_w or 1
        dh = mw._canvas._doc_h or 1

        h_zoom = dr.width() / dw
        h_origin = dr.left()
        mw._h_ruler.set_view_params(h_zoom, h_origin, dw)

        v_zoom = dr.height() / dh
        v_origin = dr.top()
        mw._v_ruler.set_view_params(v_zoom, v_origin, dh)

        from ..widgets.rulers import RULER_SIZE
        mw._h_ruler.set_perp_view_params(v_zoom, v_origin + RULER_SIZE, dh)
        mw._v_ruler.set_perp_view_params(h_zoom, h_origin + RULER_SIZE, dw)

        from ...core.enums import LayerType
        layer = mw._doc.layers.active_layer if mw._doc else None
        if layer and layer.layer_type not in (LayerType.GROUP, LayerType.MASK):
            lx, ly = layer.position
            lh, lw = layer.pixels.shape[:2]
            mw._h_ruler.set_layer_bounds(float(lx), float(lx + lw))
            mw._v_ruler.set_layer_bounds(float(ly), float(ly + lh))
        else:
            mw._h_ruler.set_layer_bounds(None, None)
            mw._v_ruler.set_layer_bounds(None, None)

        mw._h_ruler.set_guides(mw._guides)
        mw._v_ruler.set_guides(mw._guides)
