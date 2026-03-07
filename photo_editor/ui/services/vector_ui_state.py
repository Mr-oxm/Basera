"""Shared helpers for vector-specific canvas and properties-panel state."""

from __future__ import annotations


def enter_pick_segments_mode(props_panel, canvas, pick_segments_state) -> None:
    props_panel.vector_bar.enter_pick_segments()
    canvas._pick_segments_state = pick_segments_state
    canvas.update()


def exit_pick_segments_mode(props_panel, canvas) -> None:
    props_panel.vector_bar.exit_pick_segments()
    canvas._pick_segments_state = None
    canvas.update()


def show_boolean_preview(canvas, preview_path, source_ids) -> None:
    canvas._bool_preview_path = preview_path
    canvas._bool_source_ids = set(source_ids)
    canvas.update()


def clear_boolean_preview(canvas) -> None:
    canvas._bool_preview_path = None
    canvas._bool_source_ids = set()
    canvas.update()


def update_boolean_toolbar(props_panel, count: int, first: str, second: str) -> None:
    props_panel.vector_bar.update_boolean_state(count, first, second)