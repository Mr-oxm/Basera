"""Application menu bar with all top-level menus."""

from __future__ import annotations

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenuBar


class EditorMenuBar(QMenuBar):
    """Full menu bar mirroring Photoshop-style organisation."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.actions_map: dict[str, QAction] = {}
        self._build()

    def _build(self) -> None:
        self._file_menu()
        self._edit_menu()
        self._image_menu()
        self._layer_menu()
        self._select_menu()
        self._filter_menu()
        self._view_menu()
        self._help_menu()

    # ---- File ---------------------------------------------------------------

    def _file_menu(self) -> None:
        m = self.addMenu("&File")
        self._add(m, "new", "&New…", "Ctrl+N")
        self._add(m, "open", "&Open…", "Ctrl+O")
        self._add(m, "place_image", "&Place Image as Layer…", "Ctrl+Shift+O")
        m.addSeparator()
        self._add(m, "save", "&Save", "Ctrl+S")
        self._add(m, "save_as", "Save &As…", "Ctrl+Shift+S")
        self._add(m, "export", "&Export…", "Ctrl+Shift+E")
        m.addSeparator()
        self._add(m, "quit", "&Quit", "Ctrl+Q")

    def _edit_menu(self) -> None:
        m = self.addMenu("&Edit")
        self._add(m, "undo", "&Undo", "Ctrl+Z")
        self._add(m, "redo", "&Redo", "Ctrl+Shift+Z")
        m.addSeparator()
        self._add(m, "cut", "Cu&t", "Ctrl+X")
        self._add(m, "copy", "&Copy", "Ctrl+C")
        self._add(m, "paste", "&Paste", "Ctrl+V")
        m.addSeparator()
        self._add(m, "delete_sel", "&Delete", "Delete")
        self._add(m, "fill_fg", "Fill with &Foreground Color", "Alt+Backspace")
        self._add(m, "fill_bg", "Fill with &Background Color", "Ctrl+Backspace")

    def _image_menu(self) -> None:
        m = self.addMenu("&Image")
        self._add(m, "resize_canvas", "Canvas &Size…")
        self._add(m, "resize_image", "Image &Size…")
        m.addSeparator()
        self._add(m, "rotate_cw", "Rotate 90° CW")
        self._add(m, "rotate_ccw", "Rotate 90° CCW")
        self._add(m, "flip_h", "Flip &Horizontal")
        self._add(m, "flip_v", "Flip &Vertical")

    def _layer_menu(self) -> None:
        m = self.addMenu("&Layer")
        self._add(m, "new_layer", "&New Layer", "Ctrl+Shift+N")
        self._add(m, "new_group", "New &Group")
        self._add(m, "dup_layer", "&Duplicate Layer", "Ctrl+J")
        self._add(m, "del_layer", "De&lete Layer")
        m.addSeparator()
        self._add(m, "merge_down", "Merge &Down", "Ctrl+E")
        self._add(m, "flatten", "&Flatten Image")
        m.addSeparator()
        mask_sub = m.addMenu("Mas&k")
        self._add(mask_sub, "add_mask", "Add Layer &Mask (White)")
        self._add(mask_sub, "add_mask_black", "Add Layer Mask (&Black)")
        self._add(mask_sub, "add_mask_standalone", "Add &Standalone Mask Layer")
        mask_sub.addSeparator()
        self._add(mask_sub, "remove_mask_layer", "&Remove Mask Layer")
        self._add(mask_sub, "apply_mask_layer", "Appl&y Mask Layer")
        mask_sub.addSeparator()
        self._add(mask_sub, "invert_mask_layer", "&Invert Mask Layer")
        self._add(mask_sub, "convert_to_mask", "&Convert Layer to Mask")
        m.addSeparator()
        self._add(m, "toggle_vis", "Toggle &Visibility")

    def _select_menu(self) -> None:
        m = self.addMenu("&Select")
        self._add(m, "select_all", "Select &All", "Ctrl+A")
        self._add(m, "deselect", "&Deselect", "Ctrl+D")
        self._add(m, "invert_sel", "&Invert Selection", "Ctrl+Shift+I")
        m.addSeparator()
        self._add(m, "duplicate_sel", "Duplicate &Layer via Selection", "Ctrl+J")
        self._add(m, "selection_to_mask", "Selection to &Mask Layer")
        m.addSeparator()
        self._add(m, "feather_sel", "&Feather…")
        self._add(m, "grow_sel", "&Grow…")
        self._add(m, "shrink_sel", "S&hrink…")

    def _filter_menu(self) -> None:
        m = self.addMenu("F&ilter")
        for cat, items in [
            ("Blur", ["Gaussian Blur", "Motion Blur", "Radial Blur", "Surface Blur", "Lens Blur"]),
            ("Sharpen", ["Sharpen", "Unsharp Mask", "Smart Sharpen"]),
            ("Noise", ["Add Noise", "Reduce Noise", "Dust & Scratches", "Median"]),
            ("Distort", ["Ripple", "Wave", "Twirl", "Pinch", "Perspective"]),
            ("Stylize", ["Emboss", "Find Edges", "Solarize", "Oil Paint"]),
            ("Render", ["Clouds", "Difference Clouds", "Lighting Effects"]),
        ]:
            sub = m.addMenu(cat)
            for name in items:
                key = f"filter_{name.lower().replace(' ', '_').replace('&', '')}"
                self._add(sub, key, name)

    def _view_menu(self) -> None:
        m = self.addMenu("&View")
        self._add(m, "zoom_in", "Zoom &In", "Ctrl+=")
        self._add(m, "zoom_out", "Zoom &Out", "Ctrl+-")
        self._add(m, "zoom_fit", "Zoom to &Fit", "Ctrl+0")
        self._add(m, "zoom_100", "Actual &Pixels", "Ctrl+1")
        m.addSeparator()
        self._add(m, "toggle_grid", "Show &Grid")
        self._add(m, "toggle_rulers", "Show &Rulers")
        self._add(m, "toggle_guides", "Show G&uides")

    def _help_menu(self) -> None:
        m = self.addMenu("&Help")
        self._add(m, "about", "&About")

    # ---- Helper -------------------------------------------------------------

    def _add(self, menu, key: str, text: str, shortcut: str = "") -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        menu.addAction(action)
        self.actions_map[key] = action
        return action
