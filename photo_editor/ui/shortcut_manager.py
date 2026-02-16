"""Centralised keyboard-shortcut manager with preset support.

Features:
* Two built-in presets: **Photoshop** and **Affinity Photo**
* User-editable bindings that persist to a JSON file
* Live re-binding: when bindings change the ``shortcuts_changed`` signal fires
  so every QAction / toolbar button can update its key-sequence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal


# ---------------------------------------------------------------------------
# Default presets
# ---------------------------------------------------------------------------

# Each preset maps an *action_id* (str) to a human-readable key-sequence
# string that QKeySequence understands (e.g. "Ctrl+S", "V", "Shift+G").

_PHOTOSHOP_PRESET: Dict[str, str] = {
    # ---- File ---------------------------------------------------------------
    "new":              "Ctrl+N",
    "open":             "Ctrl+O",
    "place_image":      "Ctrl+Shift+O",
    "save":             "Ctrl+S",
    "save_as":          "Ctrl+Shift+S",
    "export":           "Ctrl+Shift+E",
    "quit":             "Ctrl+Q",

    # ---- Edit ---------------------------------------------------------------
    "undo":             "Ctrl+Z",
    "redo":             "Ctrl+Shift+Z",
    "cut":              "Ctrl+X",
    "copy":             "Ctrl+C",
    "paste":            "Ctrl+V",
    "delete_sel":       "Delete",
    "fill_fg":          "Alt+Backspace",
    "fill_bg":          "Ctrl+Backspace",

    # ---- Image --------------------------------------------------------------
    "resize_canvas":    "",
    "resize_image":     "",
    "rotate_cw":        "",
    "rotate_ccw":       "",
    "flip_h":           "",
    "flip_v":           "",

    # ---- Layer --------------------------------------------------------------
    "new_layer":        "Ctrl+Shift+N",
    "new_group":        "",
    "dup_layer":        "Ctrl+J",
    "del_layer":        "",
    "merge_down":       "Ctrl+E",
    "flatten":          "",
    "add_mask":         "",
    "add_mask_black":   "",
    "add_mask_standalone": "",
    "remove_mask_layer":"",
    "apply_mask_layer": "",
    "invert_mask_layer":"",
    "convert_to_mask":  "",
    "toggle_vis":       "",

    # ---- Select -------------------------------------------------------------
    "select_all":       "Ctrl+A",
    "deselect":         "Ctrl+D",
    "invert_sel":       "Ctrl+Shift+I",
    "duplicate_sel":    "Ctrl+J",
    "selection_to_mask":"",
    "feather_sel":      "",
    "grow_sel":         "",
    "shrink_sel":       "",

    # ---- View ---------------------------------------------------------------
    "zoom_in":          "Ctrl+=",
    "zoom_out":         "Ctrl+-",
    "zoom_fit":         "Ctrl+0",
    "zoom_100":         "Ctrl+1",
    "toggle_grid":      "Ctrl+'",
    "toggle_rulers":    "Ctrl+R",
    "toggle_guides":    "",

    # ---- Help ---------------------------------------------------------------
    "about":            "",
    "keyboard_shortcuts": "Ctrl+Alt+K",

    # ---- Tools (single-key press, NOT menu actions) -------------------------
    "tool_move":                "V",
    "tool_rect_select":         "M",
    "tool_ellipse_select":      "M",
    "tool_lasso":               "L",
    "tool_magic_wand":          "W",
    "tool_crop":                "C",
    "tool_eyedropper":          "I",
    "tool_healing_brush":       "J",
    "tool_clone_stamp":         "S",
    "tool_brush":               "B",
    "tool_eraser":              "E",
    "tool_gradient":            "G",
    "tool_paint_bucket":        "K",
    "tool_text":                "T",
    "tool_shape":               "U",
    "tool_pen":                 "P",
    "tool_node":                "A",
    "tool_vector_shape":        "Shift+U",
    "tool_zoom":                "Z",
    "tool_pan":                 "H",

    # ---- Color / misc -------------------------------------------------------
    "swap_colors":              "X",
    "reset_colors":             "D",
    "brush_size_increase":      "]",
    "brush_size_decrease":      "[",
    "toggle_fullscreen":        "F",
}

_AFFINITY_PRESET: Dict[str, str] = {
    # ---- File ---------------------------------------------------------------
    "new":              "Ctrl+N",
    "open":             "Ctrl+O",
    "place_image":      "Ctrl+Shift+O",
    "save":             "Ctrl+S",
    "save_as":          "Ctrl+Shift+S",
    "export":           "Ctrl+Shift+E",
    "quit":             "Ctrl+Q",

    # ---- Edit ---------------------------------------------------------------
    "undo":             "Ctrl+Z",
    "redo":             "Ctrl+Y",
    "cut":              "Ctrl+X",
    "copy":             "Ctrl+C",
    "paste":            "Ctrl+V",
    "delete_sel":       "Delete",
    "fill_fg":          "Alt+Backspace",
    "fill_bg":          "Ctrl+Backspace",

    # ---- Image --------------------------------------------------------------
    "resize_canvas":    "",
    "resize_image":     "",
    "rotate_cw":        "",
    "rotate_ccw":       "",
    "flip_h":           "",
    "flip_v":           "",

    # ---- Layer --------------------------------------------------------------
    "new_layer":        "Ctrl+Shift+N",
    "new_group":        "Ctrl+G",
    "dup_layer":        "Ctrl+J",
    "del_layer":        "Backspace",
    "merge_down":       "Ctrl+E",
    "flatten":          "",
    "add_mask":         "",
    "add_mask_black":   "",
    "add_mask_standalone": "",
    "remove_mask_layer":"",
    "apply_mask_layer": "",
    "invert_mask_layer":"Ctrl+I",
    "convert_to_mask":  "",
    "toggle_vis":       "",

    # ---- Select -------------------------------------------------------------
    "select_all":       "Ctrl+A",
    "deselect":         "Ctrl+D",
    "invert_sel":       "Ctrl+Shift+I",
    "duplicate_sel":    "",
    "selection_to_mask":"",
    "feather_sel":      "",
    "grow_sel":         "",
    "shrink_sel":       "",

    # ---- View ---------------------------------------------------------------
    "zoom_in":          "Ctrl+=",
    "zoom_out":         "Ctrl+-",
    "zoom_fit":         "Ctrl+0",
    "zoom_100":         "Ctrl+1",
    "toggle_grid":      "Ctrl+'",
    "toggle_rulers":    "Ctrl+R",
    "toggle_guides":    "",

    # ---- Help ---------------------------------------------------------------
    "about":            "",
    "keyboard_shortcuts": "Ctrl+Alt+K",

    # ---- Tools --------------------------------------------------------------
    "tool_move":                "V",
    "tool_rect_select":         "M",
    "tool_ellipse_select":      "M",
    "tool_lasso":               "L",
    "tool_magic_wand":          "W",
    "tool_crop":                "C",
    "tool_eyedropper":          "I",
    "tool_healing_brush":       "J",
    "tool_clone_stamp":         "S",
    "tool_brush":               "B",
    "tool_eraser":              "E",
    "tool_gradient":            "G",
    "tool_paint_bucket":        "K",
    "tool_text":                "T",
    "tool_shape":               "U",
    "tool_pen":                 "P",
    "tool_node":                "A",
    "tool_vector_shape":        "Shift+U",
    "tool_zoom":                "Z",
    "tool_pan":                 "H",

    # ---- Color / misc -------------------------------------------------------
    "swap_colors":              "X",
    "reset_colors":             "D",
    "brush_size_increase":      "]",
    "brush_size_decrease":      "[",
    "toggle_fullscreen":        "F",
}


# ---------------------------------------------------------------------------
# Human-readable action names and categories for the dialog
# ---------------------------------------------------------------------------

# (category, action_id, display_name)
ACTION_REGISTRY: List[Tuple[str, str, str]] = [
    # ---- File ----------------------------------------------------------------
    ("File",    "new",              "New Document"),
    ("File",    "open",             "Open"),
    ("File",    "place_image",      "Place Image as Layer"),
    ("File",    "save",             "Save"),
    ("File",    "save_as",          "Save As"),
    ("File",    "export",           "Export"),
    ("File",    "quit",             "Quit"),

    # ---- Edit ---------------------------------------------------------------
    ("Edit",    "undo",             "Undo"),
    ("Edit",    "redo",             "Redo"),
    ("Edit",    "cut",              "Cut"),
    ("Edit",    "copy",             "Copy"),
    ("Edit",    "paste",            "Paste"),
    ("Edit",    "delete_sel",       "Delete Selection"),
    ("Edit",    "fill_fg",          "Fill with Foreground"),
    ("Edit",    "fill_bg",          "Fill with Background"),

    # ---- Image --------------------------------------------------------------
    ("Image",   "resize_canvas",    "Canvas Size"),
    ("Image",   "resize_image",     "Image Size"),
    ("Image",   "rotate_cw",        "Rotate 90° CW"),
    ("Image",   "rotate_ccw",       "Rotate 90° CCW"),
    ("Image",   "flip_h",           "Flip Horizontal"),
    ("Image",   "flip_v",           "Flip Vertical"),

    # ---- Layer --------------------------------------------------------------
    ("Layer",   "new_layer",        "New Layer"),
    ("Layer",   "new_group",        "New Group"),
    ("Layer",   "dup_layer",        "Duplicate Layer"),
    ("Layer",   "del_layer",        "Delete Layer"),
    ("Layer",   "merge_down",       "Merge Down"),
    ("Layer",   "flatten",          "Flatten Image"),
    ("Layer",   "add_mask",         "Add Mask (White)"),
    ("Layer",   "add_mask_black",   "Add Mask (Black)"),
    ("Layer",   "add_mask_standalone", "Add Standalone Mask"),
    ("Layer",   "remove_mask_layer","Remove Mask Layer"),
    ("Layer",   "apply_mask_layer", "Apply Mask Layer"),
    ("Layer",   "invert_mask_layer","Invert Mask Layer"),
    ("Layer",   "convert_to_mask",  "Convert to Mask"),
    ("Layer",   "toggle_vis",       "Toggle Visibility"),

    # ---- Select -------------------------------------------------------------
    ("Select",  "select_all",       "Select All"),
    ("Select",  "deselect",         "Deselect"),
    ("Select",  "invert_sel",       "Invert Selection"),
    ("Select",  "duplicate_sel",    "Duplicate via Selection"),
    ("Select",  "selection_to_mask","Selection to Mask"),
    ("Select",  "feather_sel",      "Feather"),
    ("Select",  "grow_sel",         "Grow"),
    ("Select",  "shrink_sel",       "Shrink"),

    # ---- View ---------------------------------------------------------------
    ("View",    "zoom_in",          "Zoom In"),
    ("View",    "zoom_out",         "Zoom Out"),
    ("View",    "zoom_fit",         "Zoom to Fit"),
    ("View",    "zoom_100",         "Actual Pixels"),
    ("View",    "toggle_grid",      "Show Grid"),
    ("View",    "toggle_rulers",    "Show Rulers"),
    ("View",    "toggle_guides",    "Show Guides"),

    # ---- Help ---------------------------------------------------------------
    ("Help",    "about",            "About"),
    ("Help",    "keyboard_shortcuts","Keyboard Shortcuts"),

    # ---- Tools (single-key shortcuts) ---------------------------------------
    ("Tools",   "tool_move",            "Move Tool"),
    ("Tools",   "tool_rect_select",     "Rectangular Marquee"),
    ("Tools",   "tool_ellipse_select",  "Elliptical Marquee"),
    ("Tools",   "tool_lasso",           "Lasso"),
    ("Tools",   "tool_magic_wand",      "Magic Wand"),
    ("Tools",   "tool_crop",            "Crop"),
    ("Tools",   "tool_eyedropper",      "Eyedropper"),
    ("Tools",   "tool_healing_brush",   "Healing Brush"),
    ("Tools",   "tool_clone_stamp",     "Clone Stamp"),
    ("Tools",   "tool_brush",           "Brush"),
    ("Tools",   "tool_eraser",          "Eraser"),
    ("Tools",   "tool_gradient",        "Gradient"),
    ("Tools",   "tool_paint_bucket",    "Paint Bucket"),
    ("Tools",   "tool_text",            "Text"),
    ("Tools",   "tool_shape",           "Shape"),
    ("Tools",   "tool_pen",             "Pen Tool"),
    ("Tools",   "tool_node",            "Node Tool"),
    ("Tools",   "tool_vector_shape",    "Vector Shape"),
    ("Tools",   "tool_zoom",            "Zoom"),
    ("Tools",   "tool_pan",             "Pan"),

    # ---- Color / Misc -------------------------------------------------------
    ("General", "swap_colors",          "Swap FG/BG Colors"),
    ("General", "reset_colors",         "Reset FG/BG Colors"),
    ("General", "brush_size_increase",  "Increase Brush Size"),
    ("General", "brush_size_decrease",  "Decrease Brush Size"),
    ("General", "toggle_fullscreen",    "Toggle Fullscreen"),
]

# Convenience lookup: action_id → (category, display_name)
_ACTION_INFO: Dict[str, Tuple[str, str]] = {
    aid: (cat, name) for cat, aid, name in ACTION_REGISTRY
}

PRESETS = {
    "Photoshop": _PHOTOSHOP_PRESET,
    "Affinity Photo": _AFFINITY_PRESET,
}


# ---------------------------------------------------------------------------
# Persistence path
# ---------------------------------------------------------------------------

def _config_dir() -> Path:
    """Return (and create) the user-local config directory."""
    d = Path.home() / ".photo_editor"
    d.mkdir(exist_ok=True)
    return d


def _config_path() -> Path:
    return _config_dir() / "shortcuts.json"


# ---------------------------------------------------------------------------
# ShortcutManager
# ---------------------------------------------------------------------------

class ShortcutManager(QObject):
    """Manages the mapping from *action_id* → key-sequence string.

    Signals
    -------
    shortcuts_changed()
        Emitted after any binding change (preset switch or single edit).
    preset_changed(str)
        Emitted when the active preset name changes.
    """

    shortcuts_changed = Signal()
    preset_changed = Signal(str)

    _instance: Optional["ShortcutManager"] = None

    def __init__(self) -> None:
        super().__init__()
        self._preset_name: str = "Photoshop"
        self._bindings: Dict[str, str] = dict(_PHOTOSHOP_PRESET)
        self._custom_overrides: Dict[str, str] = {}
        self._load()

    # ---- Singleton access ---------------------------------------------------

    @classmethod
    def instance(cls) -> "ShortcutManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ---- Public API ---------------------------------------------------------

    @property
    def preset_name(self) -> str:
        return self._preset_name

    def binding(self, action_id: str) -> str:
        """Return the current key-sequence string for *action_id*."""
        return self._bindings.get(action_id, "")

    def all_bindings(self) -> Dict[str, str]:
        """Return a copy of the full binding map."""
        return dict(self._bindings)

    def set_preset(self, name: str) -> None:
        """Switch to a built-in preset, discarding custom overrides."""
        if name not in PRESETS:
            return
        self._preset_name = name
        self._bindings = dict(PRESETS[name])
        self._custom_overrides.clear()
        self._save()
        self.preset_changed.emit(name)
        self.shortcuts_changed.emit()

    def set_binding(self, action_id: str, key_seq: str) -> None:
        """Change a single binding and persist it."""
        self._bindings[action_id] = key_seq
        self._custom_overrides[action_id] = key_seq
        self._save()
        self.shortcuts_changed.emit()

    def reset_to_preset(self) -> None:
        """Reset all custom overrides back to the active preset defaults."""
        if self._preset_name in PRESETS:
            self._bindings = dict(PRESETS[self._preset_name])
        self._custom_overrides.clear()
        self._save()
        self.shortcuts_changed.emit()

    def is_custom(self, action_id: str) -> bool:
        """Return True if this action has a user-customised binding."""
        return action_id in self._custom_overrides

    def default_binding(self, action_id: str) -> str:
        """Return the preset default for *action_id*."""
        preset = PRESETS.get(self._preset_name, _PHOTOSHOP_PRESET)
        return preset.get(action_id, "")

    def action_info(self, action_id: str) -> Tuple[str, str]:
        """Return (category, display_name) for *action_id*."""
        return _ACTION_INFO.get(action_id, ("Other", action_id))

    def actions_for_category(self, category: str) -> List[Tuple[str, str, str]]:
        """Return [(action_id, display_name, key_seq), …] for a category."""
        result = []
        for cat, aid, name in ACTION_REGISTRY:
            if cat == category:
                result.append((aid, name, self._bindings.get(aid, "")))
        return result

    def categories(self) -> List[str]:
        """Return an ordered list of unique categories."""
        seen = set()
        cats = []
        for cat, _, _ in ACTION_REGISTRY:
            if cat not in seen:
                cats.append(cat)
                seen.add(cat)
        return cats

    # ---- Persistence --------------------------------------------------------

    def _save(self) -> None:
        data = {
            "preset": self._preset_name,
            "overrides": self._custom_overrides,
        }
        try:
            _config_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass  # Non-critical — user just loses persistence

    def _load(self) -> None:
        path = _config_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        preset = data.get("preset", "Photoshop")
        if preset in PRESETS:
            self._preset_name = preset
            self._bindings = dict(PRESETS[preset])
        overrides = data.get("overrides", {})
        if isinstance(overrides, dict):
            self._custom_overrides = overrides
            self._bindings.update(overrides)
