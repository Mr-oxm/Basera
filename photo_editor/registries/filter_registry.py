"""Registry for destructive filter processors."""

from __future__ import annotations

from functools import lru_cache
from importlib import import_module

from ..filters.filter_base import Filter

_FILTER_SPECS: dict[str, tuple[str, str]] = {
    "gaussian_blur": ("photo_editor.filters.blur.gaussian_blur", "GaussianBlur"),
    "motion_blur": ("photo_editor.filters.blur.motion_blur", "MotionBlur"),
    "radial_blur": ("photo_editor.filters.blur.radial_blur", "RadialBlur"),
    "surface_blur": ("photo_editor.filters.blur.surface_blur", "SurfaceBlur"),
    "lens_blur": ("photo_editor.filters.blur.lens_blur", "LensBlur"),
    "sharpen": ("photo_editor.filters.sharpen.sharpen", "Sharpen"),
    "unsharp_mask": ("photo_editor.filters.sharpen.unsharp_mask", "UnsharpMask"),
    "smart_sharpen": ("photo_editor.filters.sharpen.smart_sharpen", "SmartSharpen"),
    "add_noise": ("photo_editor.filters.noise.add_noise", "AddNoise"),
    "reduce_noise": ("photo_editor.filters.noise.reduce_noise", "ReduceNoise"),
    "dust__scratches": ("photo_editor.filters.noise.dust_scratches", "DustScratches"),
    "median": ("photo_editor.filters.noise.median", "MedianFilter"),
    "ripple": ("photo_editor.filters.distort.ripple", "Ripple"),
    "wave": ("photo_editor.filters.distort.wave", "Wave"),
    "twirl": ("photo_editor.filters.distort.twirl", "Twirl"),
    "pinch": ("photo_editor.filters.distort.pinch", "Pinch"),
    "perspective": ("photo_editor.filters.distort.perspective", "PerspectiveFilter"),
    "emboss": ("photo_editor.filters.stylize.emboss", "Emboss"),
    "find_edges": ("photo_editor.filters.stylize.find_edges", "FindEdges"),
    "solarize": ("photo_editor.filters.stylize.solarize", "Solarize"),
    "oil_paint": ("photo_editor.filters.stylize.oil_paint", "OilPaint"),
    "clouds": ("photo_editor.filters.render.clouds", "Clouds"),
    "difference_clouds": ("photo_editor.filters.render.difference_clouds", "DifferenceClouds"),
    "lighting_effects": ("photo_editor.filters.render.lighting_effects", "LightingEffects"),
}


def _load_class(module_name: str, class_name: str) -> type[Filter]:
    module = import_module(module_name)
    loaded = getattr(module, class_name)
    if not issubclass(loaded, Filter):
        raise TypeError(f"{module_name}.{class_name} is not a Filter")
    return loaded


@lru_cache(maxsize=1)
def get_filter_map() -> dict[str, type[Filter]]:
    """Return internal-key to filter-class mapping."""
    return {
        key: _load_class(module_name, class_name)
        for key, (module_name, class_name) in _FILTER_SPECS.items()
    }


def get_filter_class(key: str) -> type[Filter] | None:
    """Return the filter class for an internal menu key."""
    return get_filter_map().get(key)


@lru_cache(maxsize=1)
def get_filter_name_map() -> dict[str, type[Filter]]:
    """Return display-name to filter-class mapping."""
    return {filter_cls().name: filter_cls for filter_cls in get_filter_map().values()}