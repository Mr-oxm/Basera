"""Gradient tool — handles overlay, type, opacity, reverse."""

from __future__ import annotations

from ...core.enums import ToolType
from .base import ControllerBase


class GradientController(ControllerBase):
    """Handles gradient tool setup and gradient properties bar."""

    def __init__(self) -> None:
        super().__init__()

    def wire(self, main_window) -> None:
        """Connect to main window and wire panel signals."""
        super().wire(main_window)
        mw = self.mw

        mw._props_panel.gradient_property_changed.connect(self.on_gradient_prop_changed)

    def setup(self) -> None:
        """Wire callbacks for the gradient tool (called when gradient tool is selected)."""
        mw = self.mw
        tool = mw._tools.active_tool
        if tool is None:
            return
        tool.set_preview_callback(self.ctx.schedule_render)
        tool.set_handles_callback(self.on_gradient_handles)
        # Restore handles if the tool still has an active editing session
        if tool.is_editing:
            tool._emit_handles(True)

    def on_gradient_handles(self, start, end, stops, visible) -> None:
        mw = self.mw
        mw._canvas.set_gradient_handles(start, end, stops, visible)

    def on_gradient_prop_changed(self, key: str, value: object) -> None:
        mw = self.mw
        tool = mw._tools.active_tool
        if tool is None or mw._tools.active_type != ToolType.GRADIENT:
            return
        if key == "gradient_type":
            tool.gradient_type = str(value)
            if tool.is_editing:
                tool._reapply_gradient()
                self.ctx.refresh()
        elif key == "opacity":
            tool.opacity = float(value)
            if tool.is_editing:
                tool._reapply_gradient()
                self.ctx.refresh()
        elif key == "reverse":
            tool.reverse_gradient()
            self.ctx.refresh()
        elif key == "gradient_fill":
            fill = value
            if hasattr(fill, "stops"):
                tool.stops = list(fill.stops)
            from ...core.color import LinearGradient, RadialGradient
            from ...core.color_engine import ConicalGradient, DiamondGradient
            _cls_map = {
                LinearGradient: "linear",
                RadialGradient: "radial",
                ConicalGradient: "conical",
                DiamondGradient: "diamond",
            }
            gtype = _cls_map.get(type(fill))
            if gtype:
                tool.gradient_type = gtype
            self.ctx.refresh()
