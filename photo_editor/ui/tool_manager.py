"""Manages tool instances and dispatches canvas events to the active tool."""

from __future__ import annotations

import numpy as np

from ..core.document import Document
from ..core.enums import ToolType
from ..tools.brush import BrushTool
from ..tools.clone_stamp import CloneStampTool
from ..tools.eraser import EraserTool
from ..tools.gradient_tool import GradientTool
from ..tools.healing_brush import HealingBrushTool
from ..tools.paint_bucket import PaintBucketTool
from ..tools.selection_tools import (
    EllipseSelectTool, LassoTool, MagicWandTool, RectSelectTool,
)
from ..tools.shape_tool import ShapeTool
from ..tools.text_tool import TextTool
from ..tools.tool_base import Tool
from ..tools.transform_tool import TransformTool


class ToolManager:
    """Creates, selects, and dispatches events to tool instances."""

    def __init__(self) -> None:
        self._tools: dict[ToolType, Tool] = {
            ToolType.BRUSH: BrushTool(),
            ToolType.ERASER: EraserTool(),
            ToolType.CLONE_STAMP: CloneStampTool(),
            ToolType.HEALING_BRUSH: HealingBrushTool(),
            ToolType.GRADIENT: GradientTool(),
            ToolType.PAINT_BUCKET: PaintBucketTool(),
            ToolType.RECT_SELECT: RectSelectTool(),
            ToolType.ELLIPSE_SELECT: EllipseSelectTool(),
            ToolType.LASSO: LassoTool(),
            ToolType.MAGIC_WAND: MagicWandTool(),
            ToolType.TEXT: TextTool(),
            ToolType.SHAPE: ShapeTool(),
            ToolType.TRANSFORM: TransformTool(),
        }
        self._active_type = ToolType.BRUSH

    # ---- Selection ----------------------------------------------------------

    @property
    def active_tool(self) -> Tool | None:
        return self._tools.get(self._active_type)

    @property
    def active_type(self) -> ToolType:
        return self._active_type

    def select(self, tool_type: ToolType) -> None:
        old = self.active_tool
        if old:
            old.deactivate()
        self._active_type = tool_type
        new_tool = self.active_tool
        if new_tool:
            new_tool.activate()

    # ---- Dispatch -----------------------------------------------------------

    def on_press(self, doc: Document | None, x: int, y: int, pressure: float = 1.0) -> None:
        tool = self.active_tool
        if tool and doc:
            tool.on_press(doc, x, y, pressure)

    def on_move(self, doc: Document | None, x: int, y: int, pressure: float = 1.0) -> None:
        tool = self.active_tool
        if tool and doc:
            tool.on_move(doc, x, y, pressure)

    def on_release(self, doc: Document | None, x: int, y: int) -> None:
        tool = self.active_tool
        if tool and doc:
            tool.on_release(doc, x, y)

    # ---- Color --------------------------------------------------------------

    def set_foreground_color(self, rgba: np.ndarray) -> None:
        for tt in (ToolType.BRUSH, ToolType.PAINT_BUCKET, ToolType.SHAPE, ToolType.TEXT):
            tool = self._tools.get(tt)
            if tool and hasattr(tool, "color"):
                tool.color = rgba.copy()

    # ---- Properties ---------------------------------------------------------

    def get_properties(self) -> dict[str, tuple[float, float, float]]:
        """Return {name: (current_value, min, max)} for the active tool."""
        tool = self.active_tool
        if tool is None:
            return {}
        defs: dict[str, tuple[float, float, float]] = {}
        _RANGES = {
            "size": (1, 500), "hardness": (0, 1), "opacity": (0, 1),
            "flow": (0, 1), "tolerance": (0, 255), "feather": (0, 100),
            "font_size": (6, 200),
        }
        for attr, (lo, hi) in _RANGES.items():
            if hasattr(tool, attr):
                defs[attr] = (getattr(tool, attr), lo, hi)
        return defs

    def set_property(self, key: str, value: float) -> None:
        tool = self.active_tool
        if tool and hasattr(tool, key):
            if isinstance(getattr(tool, key), int):
                setattr(tool, key, int(value))
            else:
                setattr(tool, key, float(value))
