"""Main application window — assembles all panels, menus, and canvas."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDockWidget, QMainWindow, QMessageBox

from ..core.document import Document
from ..core.enums import BlendMode, ToolType
from ..engine.render_pipeline import RenderPipeline
from .canvas_view import CanvasView
from .file_tab_bar import FileTabBar
from .menus import EditorMenuBar
from .panels.color_panel import ColorPanel
from .panels.history_panel import HistoryPanel
from .panels.layers_panel import LayersPanel
from .panels.properties_panel import PropertiesPanel
from .panels.transform_panel import TransformPanel
from .controllers import DocumentController
from .shortcut_manager import ShortcutManager
from .status_bar import EditorStatusBar
from .theme import DARK_STYLESHEET
from .tool_manager import ToolManager
from .toolbar import EditorToolbar

_IMG_FLT = "Images (*.png *.jpg *.jpeg *.webp *.tiff *.tif *.bmp)"


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Photo Editor")
        self.resize(1440, 900)
        self.setStyleSheet(DARK_STYLESHEET)
        self.setAcceptDrops(True)

        self._doc: Document | None = None
        self._pipeline = RenderPipeline()
        self._tools = ToolManager()

        # Multi-document tracking: list of (Document, str|None) pairs
        self._open_docs: list[tuple[Document, str | None]] = []

        # Blend-mode hover preview state
        self._blend_preview_original: BlendMode | None = None

        # Render throttle — max ~30 fps during drag
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(33)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._do_deferred_render)
        self._render_pending = False
        # Deferred panel refresh — coalesced to avoid rebuilding panels
        # dozens of times per second during interactive operations.
        self._panel_refresh_timer = QTimer(self)
        self._panel_refresh_timer.setInterval(200)  # 5 fps panel updates
        self._panel_refresh_timer.setSingleShot(True)
        self._panel_refresh_timer.timeout.connect(self._do_deferred_panel_refresh)
        self._panel_refresh_pending = False
        
        # Track whether text editing is active to manage conflicting shortcuts
        self._text_editing_active = False

        self._shortcut_mgr = ShortcutManager.instance()

        self._build_ui()
        self._document_ctrl = DocumentController()
        self._document_ctrl.wire(self)
        from .controllers.selection_ctrl import SelectionController
        self._selection_ctrl = SelectionController()
        self._selection_ctrl.wire(self)
        from .controllers.filter_ctrl import FilterController
        self._filter_ctrl = FilterController()
        self._filter_ctrl.wire(self)
        from .controllers.transform_ctrl import TransformController
        self._transform_ctrl = TransformController()
        self._transform_ctrl.wire(self)
        from .controllers.crop_ctrl import CropController
        self._crop_ctrl = CropController()
        self._crop_ctrl.wire(self)
        from .controllers.vector_ctrl import VectorController
        self._vector_ctrl = VectorController()
        self._vector_ctrl.wire(self)
        from .controllers.gradient_ctrl import GradientController
        self._gradient_ctrl = GradientController()
        self._gradient_ctrl.wire(self)
        from .controllers.text_ctrl import TextController
        self._text_ctrl = TextController()
        self._text_ctrl.wire(self)
        from .controllers.layer_ctrl import LayerController
        self._layer_ctrl = LayerController()
        self._layer_ctrl.wire(self)
        from .controllers.view_ctrl import ViewController
        self._view_ctrl = ViewController()
        self._view_ctrl.wire(self)
        from .controllers.tool_ctrl import ToolController
        self._tool_ctrl = ToolController()
        self._tool_ctrl.wire(self)
        from .controllers.color_ctrl import ColorController
        self._color_ctrl = ColorController()
        self._color_ctrl.wire(self)
        from .controllers.canvas_ctrl import CanvasController
        self._canvas_ctrl = CanvasController()
        self._canvas_ctrl.wire(self)
        from .controllers.shortcut_ctrl import ShortcutController
        self._shortcut_ctrl = ShortcutController()
        self._shortcut_ctrl.wire(self)
        from .controllers.drop_ctrl import DropController
        self._drop_ctrl = DropController()
        self._drop_ctrl.wire(self)
        self._wire_menus()
        self._wire_panels()
        self._wire_canvas()
        self._wire_file_tabs()
        # Shortcuts wired by ShortcutController
        self._document_ctrl.new_document(1920, 1080)

    # ---- UI assembly --------------------------------------------------------

    def _build_ui(self) -> None:
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QToolBar
        from .widgets.rulers import HorizontalRuler, VerticalRuler, RulerCorner, Guide, RULER_SIZE
        
        self._menu = EditorMenuBar(self)
        self.setMenuBar(self._menu)

        # Properties panel as a toolbar directly under the menu bar
        self._props_panel = PropertiesPanel()
        self._props_toolbar = QToolBar("Properties", self)
        self._props_toolbar.setMovable(False)
        self._props_toolbar.setFloatable(False)
        self._props_toolbar.addWidget(self._props_panel)
        self._props_toolbar.setStyleSheet(
            "QToolBar { background: #333333; border: none; border-bottom: 1px solid #444; spacing: 0; padding: 0; }"
            "QToolBar > QWidget { background: #333333; }"
        )
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._props_toolbar)

        self._toolbar = EditorToolbar(self)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._toolbar)
        
        # Central widget: file tabs + rulers + canvas
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        
        # File tab bar at the top of the central area
        self._file_tabs = FileTabBar()
        central_layout.addWidget(self._file_tabs)
        
        # Grid: rulers + canvas
        ruler_grid = QWidget()
        grid = QGridLayout(ruler_grid)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)

        self._ruler_corner = RulerCorner()
        self._h_ruler = HorizontalRuler()
        self._v_ruler = VerticalRuler()
        self._canvas = CanvasView(self)
        self._canvas.set_tool_manager_ref(self._tools)

        grid.addWidget(self._ruler_corner, 0, 0)
        grid.addWidget(self._h_ruler, 0, 1)
        grid.addWidget(self._v_ruler, 1, 0)
        grid.addWidget(self._canvas, 1, 1)

        # Rulers default visible
        self._rulers_visible = True
        self._guides: list = []

        # Ruler/guide signals wired by ViewController

        central_layout.addWidget(ruler_grid, 1)
        
        self.setCentralWidget(central)
        
        # Dock panels on the sides
        self._layers_panel = LayersPanel()
        self._layers_dock = self._dock(self._layers_panel, "Layers", Qt.DockWidgetArea.RightDockWidgetArea)
        self._history_panel = HistoryPanel()
        self._dock(self._history_panel, "History", Qt.DockWidgetArea.RightDockWidgetArea)
        self._color_panel = ColorPanel()
        self._color_dock = self._dock(self._color_panel, "Color", Qt.DockWidgetArea.RightDockWidgetArea)
        self.tabifyDockWidget(self._layers_dock, self._color_dock)
        self._layers_dock.raise_()
        
        self._transform_panel = TransformPanel()
        self._transform_dock = self._dock(self._transform_panel, "Transform", Qt.DockWidgetArea.RightDockWidgetArea)
        self.tabifyDockWidget(self._layers_dock, self._transform_dock)

        self._status = EditorStatusBar(self)
        self.setStatusBar(self._status)

    def _dock(self, widget, title: str, area) -> QDockWidget:
        d = QDockWidget(title, self)
        d.setWidget(widget)
        self.addDockWidget(area, d)
        return d

    # ---- Wiring: menus ------------------------------------------------------

    def _wire_menus(self) -> None:
        a = self._menu.actions_map
        # Flip/rotate wired by TransformController, filter_* by FilterController
        if "keyboard_shortcuts" in a:
            a["keyboard_shortcuts"].triggered.connect(
                self._shortcut_ctrl._on_keyboard_shortcuts
            )
        if "about" in a:
            a["about"].triggered.connect(self._on_about)

    # ---- Wiring: panels -----------------------------------------------------

    def _wire_panels(self) -> None:
        # Toolbar and props panel wired by ToolController, color panel by ColorController
        # text/gradient/align/vector wired by TextController, GradientController,
        # TransformController, VectorController
        self._transform_panel.value_changed.connect(lambda: self._refresh(invalidate=True))

    # ---- Wiring: file tabs --------------------------------------------------

    def _wire_file_tabs(self) -> None:
        pass  # Tab signals wired by DocumentController

    # ---- Wiring: canvas -----------------------------------------------------

    def _wire_canvas(self) -> None:
        self._canvas.cursor_moved.connect(self._status.set_cursor_pos)
        # Canvas input wired by CanvasController
        self._canvas.view_changed.connect(self._view_ctrl.update_rulers)
        # Guide drag wired by ViewController

    # ---- Document lifecycle -------------------------------------------------

    def _refresh(self, invalidate: bool = True, layer_id: str | None = None) -> None:
        """Full UI refresh.

        Parameters
        ----------
        invalidate : bool
            If *True* (default), the render cache is marked stale so the
            composite is recomputed.  Pass *False* for operations that
            only change non-pixel state (layer selection, panel sync)
            to skip expensive recompositing.
        layer_id : str | None
            Optional layer that changed.  When set the engine can use
            its incremental cache instead of a full rebuild.
        """
        if not self._doc:
            return
        self._canvas.set_document_ref(self._doc)
        if invalidate:
            self._pipeline.invalidate(layer_id)
        result = self._pipeline.execute_to_uint8(self._doc)
        self._canvas.set_image(result, force=invalidate)
        self._layers_panel.refresh(self._doc)
        self._history_panel.refresh(self._doc.history)
        self._transform_panel.refresh(self._doc)
        self._selection_ctrl.update_selection_overlay()
        self._transform_ctrl.update_transform_box()
        self._view_ctrl.update_rulers()

    def _refresh_canvas_only(self) -> None:
        """Re-render and update canvas only (skip panel updates)."""
        if not self._doc:
            return
        active = self._doc.layers.active_layer
        self._pipeline.invalidate(active.id if active else None)
        result = self._pipeline.execute_to_uint8(self._doc)
        self._canvas.set_image(result, force=True)
        self._selection_ctrl.update_selection_overlay()
        self._transform_ctrl.update_transform_box()
        self._transform_panel.refresh(self._doc)
        self._view_ctrl.update_rulers()

    def _refresh_lightweight(self) -> None:
        """Re-render canvas + lightweight panel sync (no thumbnails)."""
        if not self._doc:
            return
        active = self._doc.layers.active_layer
        self._pipeline.invalidate(active.id if active else None)
        result = self._pipeline.execute_to_uint8(self._doc)
        self._canvas.set_image(result, force=True)
        self._layers_panel.refresh_controls_only(self._doc)
        self._transform_ctrl.update_transform_box()

    def _schedule_render(self) -> None:
        """Request a deferred render (throttled to ~30fps)."""
        if not self._render_pending:
            self._render_pending = True
            self._render_timer.start()

    def _do_deferred_render(self) -> None:
        """Timer callback — perform the actual canvas render."""
        self._render_pending = False
        self._refresh_canvas_only()

    def _schedule_panel_refresh(self) -> None:
        """Request a deferred panel refresh (throttled to ~5fps)."""
        if not self._panel_refresh_pending:
            self._panel_refresh_pending = True
            self._panel_refresh_timer.start()

    def _do_deferred_panel_refresh(self) -> None:
        """Timer callback — perform the actual panel refresh."""
        self._panel_refresh_pending = False
        if self._doc:
            self._layers_panel.refresh(self._doc, thumbnails=False)
            self._transform_panel.refresh(self._doc)
            self._history_panel.refresh(self._doc.history)

    # ---- Key event handling -------------------------------------------------

    def keyPressEvent(self, event) -> None:
        if (self._tools.active_type == ToolType.TEXT
                and self._canvas._text_editing):
            return super().keyPressEvent(event)

        key = event.key()
        mods = event.modifiers()

        if self._vector_ctrl.handle_key_press(key, event):
            return
        if not mods and self._layer_ctrl.handle_numpad_opacity(key):
            return

        super().keyPressEvent(event)

    def dragEnterEvent(self, event) -> None:
        self._drop_ctrl.on_drag_enter(event)

    def dropEvent(self, event) -> None:
        self._drop_ctrl.on_drop(event)

    def _on_about(self) -> None:
        """Show the About dialog."""
        QMessageBox.about(
            self,
            "About Photo Editor",
            "<h3>Photo Editor</h3>"
            "<p>A professional raster image editor built with PySide6.</p>"
            "<p>Features include layers, masks, blending modes, "
            "filters, adjustments, and more.</p>",
        )
