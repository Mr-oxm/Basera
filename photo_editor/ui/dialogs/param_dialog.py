"""Factory for parameter dialogs (generic sliders vs specialized UIs)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtWidgets import QDialog, QWidget

from ...processors import ImageProcessor
from .filter_dialog import FilterDialog


@dataclass
class ParamDialogOptions:
    """Optional context for adjustment/filter parameter dialogs."""

    #: Composited document RGBA float32 [0,1] for histograms / analysis; may be None.
    composite_fn: Callable[[], Any] | None = None
    #: One-shot canvas click → document *(x, y)* in pixel coords; returns a cancel callable.
    canvas_pick_connect: Callable[[Callable[[int, int], None]], Callable[[], None]] | None = None


def create_param_dialog(
    title: str,
    processor: ImageProcessor,
    params: dict,
    parent: QWidget | None = None,
    options: ParamDialogOptions | None = None,
) -> QDialog:
    """Return a dialog with ``params_changed`` and ``get_params()`` APIs."""
    opts = options or ParamDialogOptions()
    if processor.name == "Curves":
        from .adjustments.curves_dialog import CurvesDialog

        return CurvesDialog(title, params, parent=parent)
    if processor.name == "Levels":
        from .adjustments.levels_dialog import LevelsDialog

        return LevelsDialog(title, params, parent=parent, composite_fn=opts.composite_fn)
    if processor.name == "Hue/Saturation":
        from .adjustments.hue_saturation_dialog import HueSaturationDialog

        return HueSaturationDialog(
            title,
            params,
            parent=parent,
            composite_fn=opts.composite_fn,
            canvas_pick_connect=opts.canvas_pick_connect,
        )
    if processor.name == "Color Balance":
        from .adjustments.color_balance_dialog import ColorBalanceDialog

        return ColorBalanceDialog(title, params, parent=parent)
    if processor.name == "Brightness/Contrast":
        from .adjustments.brightness_contrast_dialog import BrightnessContrastDialog

        return BrightnessContrastDialog(title, params, parent=parent)
    if processor.name == "Vibrance":
        from .adjustments.vibrance_dialog import VibranceDialog

        return VibranceDialog(title, params, parent=parent)
    if processor.name == "White Balance":
        from .adjustments.white_balance_dialog import WhiteBalanceDialog

        return WhiteBalanceDialog(
            title,
            params,
            parent=parent,
            composite_fn=opts.composite_fn,
            canvas_pick_connect=opts.canvas_pick_connect,
        )
    if processor.name == "Recolor":
        from .adjustments.recolor_dialog import RecolorDialog

        return RecolorDialog(title, params, parent=parent)
    if processor.name == "Split Toning":
        from .adjustments.split_toning_dialog import SplitToningDialog

        return SplitToningDialog(title, params, parent=parent)
    if processor.name == "Normals":
        from .adjustments.normals_dialog import NormalsDialog

        return NormalsDialog(title, params, parent=parent)
    return FilterDialog(title, params, parent=parent)
