from photo_editor.registries import (
    get_adjustment_class,
    get_adjustment_map,
    get_filter_class,
    get_filter_map,
    get_filter_name_map,
)


def test_adjustment_registry_resolves_display_name() -> None:
    adjustment_map = get_adjustment_map()
    assert "Brightness/Contrast" in adjustment_map
    assert get_adjustment_class("Brightness/Contrast") is adjustment_map["Brightness/Contrast"]


def test_filter_registry_resolves_internal_key() -> None:
    filter_map = get_filter_map()
    assert "gaussian_blur" in filter_map
    assert get_filter_class("gaussian_blur") is filter_map["gaussian_blur"]


def test_filter_registry_resolves_display_name() -> None:
    filter_name_map = get_filter_name_map()
    assert "Gaussian Blur" in filter_name_map
    assert filter_name_map["Gaussian Blur"] is get_filter_class("gaussian_blur")