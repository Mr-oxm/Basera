"""PySide6 user interface components for the Photo Editor.

This package contains all UI code: main window, canvas, panels, dialogs,
widgets, controllers, and supporting modules. The architecture separates
domain logic into controllers that wire menu/panel signals to handlers.

=============================================================================
FOLDER STRUCTURE
=============================================================================

ui/
├── __init__.py          # This file — package overview and documentation
├── main_window.py       # MainWindow — top-level application window
├── canvas_view.py       # CanvasView — zoomable/pannable document canvas
├── toolbar.py           # EditorToolbar — tool buttons, FG/BG swatches
├── menus.py             # EditorMenuBar — File, Edit, Layer, etc.
├── status_bar.py        # EditorStatusBar — document info, zoom, cursor pos
├── file_tab_bar.py      # FileTabBar — tabs for open documents
├── shortcut_manager.py  # ShortcutManager — keyboard bindings (singleton)
├── tool_manager.py      # ToolManager — tool instances and event dispatch
├── filter_runner.py     # FilterRunner — runs filter/adjustment dialogs
├── theme.py             # DARK_STYLESHEET — dark theme stylesheet
│
├── canvas/              # Canvas subcomponents
├── controllers/         # Domain-specific UI logic handlers
├── panels/              # Dockable side panels
├── widgets/             # Reusable UI widgets (color, gradient, rulers)
└── dialogs/             # Modal dialogs (new doc, filter, shortcuts, etc.)

=============================================================================
ROOT-LEVEL FILES
=============================================================================

main_window.py
    MainWindow (QMainWindow)
        Top-level window. Assembles menu bar, toolbar, canvas, file tabs,
        dock panels (Layers, Color, History, Properties, Transform).
        Manages document lifecycle, render pipeline, tool manager.
        Key methods: _build_ui, _refresh, _update_rulers, _do_deferred_render.

canvas_view.py
    CanvasView (QOpenGLWidget or QWidget)
        Interactive canvas: zoom, pan, selection overlay (marching ants),
        transform box, guides, in-canvas text editing.
        GPU-accelerated when QOpenGLWidget available.
        Signals: cursor_moved, tool_pressed/moved/released, view_changed,
        guide_grabbed/drag_moved/drag_released.

toolbar.py
    EditorToolbar (QToolBar)
        Grouped tool buttons with flyout sub-toolbars.
        FG/BG colour swatches, swap/reset buttons.
        Tool groups: move, marquee, selection, crop, eyedropper, retouching,
        brush, eraser, paint bucket, gradient, text, shape, vector, zoom, pan.

menus.py
    EditorMenuBar (QMenuBar)
        File, Edit, Image, Layer, Select, Filter, View, Help.
        Shortcuts from ShortcutManager (live-updated on preset change).

status_bar.py
    EditorStatusBar (QStatusBar)
        Pills: document size, zoom %, cursor position.
        Auto-rasterize checkbox. Modern pill-based layout.

file_tab_bar.py
    FileTabBar (QWidget)
        Horizontal tabs for open documents with close buttons.
        Signals: tab_selected, tab_close_requested.

shortcut_manager.py
    ShortcutManager (QObject, singleton)
        Centralised keyboard shortcuts. Presets: Photoshop, Affinity Photo.
        User-editable bindings persist to JSON.
        Signal: shortcuts_changed — fires when bindings change.

tool_manager.py
    ToolManager
        Creates tool instances (Brush, Eraser, Move, Crop, etc.).
        select(tool_type), active_tool, active_type.
        Dispatches canvas events to the active tool.

filter_runner.py
    run_filter_dialog(), run_adjustment_dialog()
        Opens FilterDialog for adjustments/filters.
        Live preview: parameter changes apply temporarily to the canvas.

theme.py
    DARK_STYLESHEET (str)
        Professional dark theme for QMainWindow, menus, toolbars, dock
        widgets, list/tree widgets, scrollbars, etc.

=============================================================================
canvas/ — Canvas subcomponents
=============================================================================

canvas_input.py
    CanvasInputHandler
        Handles mouse (press, move, release, wheel) and keyboard for canvas.
        Middle-click pan, scroll zoom, guide drag, delegates to tools.

canvas_overlays.py
    CanvasOverlays
        Draws overlays: marching ants, transform box, guides, text cursor,
        selection highlight, clone/heal preview, gradient line, etc.

canvas_cursors.py
    CURSORS, HANDLE_CURSORS, HANDLE_HIT
        Tool-to-cursor mapping. build_rotate_cursor(), build_source_cursor().
    checker_tile(), gradient_cursor()
        Checkerboard and gradient cursor pixmaps.

=============================================================================
controllers/ — Domain-specific handlers
=============================================================================

Each controller wires menu/panel signals to handlers. Holds reference to
MainWindow (self._mw) for shared behavior (_refresh, _update_rulers).

document_ctrl.py    DocumentController — new, open, save, tabs, undo/redo
layer_ctrl.py       LayerController — add/delete layers, masks, blend mode
selection_ctrl.py   SelectionController — select all, feather, cut/copy/paste
view_ctrl.py        ViewController — zoom, pan, grid, rulers, guides
filter_ctrl.py      FilterController — filter/adjustment layers, FilterDialog
transform_ctrl.py   TransformController — flip, rotate, align/distribute
crop_ctrl.py        CropController — crop tool, canvas/layer crop
vector_ctrl.py      VectorController — fill/stroke, node actions
gradient_ctrl.py    GradientController — gradient tool setup
text_ctrl.py        TextController — text tool, overlay, key handler
color_ctrl.py       ColorController — foreground color from Color panel
tool_ctrl.py        ToolController — tool selection, eyedropper, brush cursor
canvas_ctrl.py      CanvasController — canvas mouse input, tool delegation
shortcut_ctrl.py    ShortcutController — QShortcuts for tools, swap colors
drop_ctrl.py        DropController — drag-and-drop place image

=============================================================================
panels/ — Dockable side panels
=============================================================================

layers_panel.py
    LayersPanel — Layer tree, blend mode, opacity, visibility, mask icons.
    Toolbar: new layer, fx, mask, duplicate, delete, etc.

color_panel.py
    ColorPanel — FG/BG swatches, opacity slider, color picker (wheel/sliders).

history_panel.py
    HistoryPanel — Undo/redo history list, jump to state.

properties_panel.py
    PropertiesPanel — Context-sensitive: MovePropertiesBar, TextPropertiesBar,
    GradientPropertiesBar, SelectionPropertiesBar, ZoomPropertiesBar,
    CropPropertiesBar, VectorPropertiesBar.

transform_panel.py
    TransformPanel — Anchor widget, position/size/rotation inputs.

adjustments_panel.py
    AdjustmentsPanel — Quick access to adjustment layers.

=============================================================================
widgets/ — Reusable UI widgets
=============================================================================

color_dropdown.py   ColorDropdown — FG/BG color picker with popup
color_wheel.py      ColorWheel — HSV color wheel
color_sliders.py    ColorSliders — RGB/HSV/HSL/CMYK channel sliders
gradient_editor.py  GradientEditor, GradientBar — gradient stop editor
swatch_grid.py      SwatchGrid — color swatch grid
rulers.py           HorizontalRuler, VerticalRuler, RulerCorner, Guide

=============================================================================
dialogs/ — Modal dialogs
=============================================================================

new_document.py     NewDocumentDialog — width, height, resolution
filter_dialog.py    FilterDialog — adjustment/filter parameters, live preview
shortcuts_dialog.py KeyboardShortcutsDialog — edit keyboard bindings
layer_styles_dialog.py  LayerStylesDialog — drop shadow, glow, stroke, etc.
text_dialog.py      TextDialog — text layer editing
"""
