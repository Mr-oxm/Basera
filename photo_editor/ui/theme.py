"""Professional themes for the photo editor."""

from PySide6.QtCore import QObject, Signal

class ThemeManager(QObject):
    theme_changed = Signal(dict)
    
    _instance = None
    
    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
        
    def __init__(self):
        super().__init__()
        self.active_theme_name = "Dark"
        self.active_palette = PALETTES["Dark"]
        
    def set_theme(self, name: str):
        if name in PALETTES:
            self.active_theme_name = name
            self.active_palette = PALETTES[name]
            self.theme_changed.emit(self.active_palette)

def _generate_stylesheet(palette):
    return f"""
QMainWindow, QWidget {{
    background-color: {palette['bg1']};
    color: {palette['fg']};
    font-family: "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 12px;
}}
QMenuBar {{
    background-color: {palette['bg3']};
    color: {palette['fg']};
    border-bottom: 1px solid {palette['border']};
}}
QMenuBar::item:selected {{ background-color: {palette['hover']}; }}
QMenu {{
    background-color: {palette['bg2']};
    color: {palette['fg']};
    border: 1px solid {palette['border_light']};
}}
QMenu::item:selected {{ background-color: {palette['accent']}; color: {palette['fg_accent']}; }}
QMenu::separator {{ height: 1px; background: {palette['border_light']}; margin: 4px 8px; }}
QToolBar {{
    background-color: {palette['bg3']};
    border: none;
    spacing: 2px;
    padding: 2px;
}}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 3px; padding: 4px; }}
QToolButton:hover {{ background-color: {palette['border']}; border-color: {palette['border_light']}; }}
QToolButton:checked {{ background-color: {palette['accent']}; border-color: {palette['accent_border']}; }}
QDockWidget {{
    titlebar-close-icon: none;
    color: {palette['fg']};
}}
QDockWidget::title {{
    background-color: {palette['bg2']};
    padding: 6px;
    border-bottom: 1px solid {palette['border']};
}}
QListWidget, QTreeWidget {{
    background-color: {palette['bg1_alt']};
    border: 1px solid {palette['border']};
    alternate-background-color: {palette['bg3']};
}}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background-color: {palette['accent']};
    color: {palette['fg_accent']};
}}
QScrollBar:vertical {{
    background-color: {palette['bg1']}; width: 10px; border: none;
}}
QScrollBar::handle:vertical {{
    background-color: {palette['scroll']}; min-height: 30px; border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{ background-color: {palette['scroll_hover']}; }}
QScrollBar:horizontal {{
    background-color: {palette['bg1']}; height: 10px; border: none;
}}
QScrollBar::handle:horizontal {{
    background-color: {palette['scroll']}; min-width: 30px; border-radius: 5px;
}}
QPushButton {{
    background-color: {palette['btn']}; border: 1px solid {palette['border_light']};
    border-radius: 3px; padding: 5px 12px; color: {palette['fg']};
}}
QPushButton:hover {{ background-color: {palette['hover']}; }}
QPushButton:pressed {{ background-color: {palette['accent']}; color: {palette['fg_accent']}; }}
QSlider::groove:horizontal {{
    background: {palette['btn']}; height: 4px; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {palette['slider_handle']}; width: 12px; height: 12px;
    margin: -4px 0; border-radius: 6px;
}}
QSlider::handle:horizontal:hover {{ background: {palette['fg']}; }}
QComboBox {{
    background-color: {palette['btn']}; border: 1px solid {palette['border_light']};
    border-radius: 3px; padding: 3px 8px; color: {palette['fg']};
}}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background-color: {palette['bg2']}; color: {palette['fg']};
    selection-background-color: {palette['accent']};
    color: {palette['fg_accent']};
}}
QSpinBox, QDoubleSpinBox {{
    background-color: {palette['input_bg']}; border: 1px solid {palette['border_light']};
    border-radius: 3px; padding: 2px; color: {palette['fg']};
}}
QLabel {{ color: {palette['fg']}; }}
QStatusBar {{
    background-color: {palette['bg1_alt']} !important;
    color: {palette['fg_dim']} !important;
    border-top: 1px solid {palette['input_bg']} !important;
    padding: 0px !important;
}}
QStatusBar::item {{ border: none; }}
QTabWidget::pane {{ border: 1px solid {palette['border']}; }}
QTabBar::tab {{
    background-color: {palette['bg2']}; color: {palette['slider_handle']};
    padding: 6px 14px; border: 1px solid {palette['border']};
}}
QTabBar::tab:selected {{ background-color: {palette['bg1']}; color: {palette['fg']}; border-bottom: none; }}
QGroupBox {{
    border: 1px solid {palette['border']}; border-radius: 4px;
    margin-top: 8px; padding-top: 12px; color: {palette['fg']};
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
"""

PALETTES = {
    "Dark": {
        "bg1": "#2b2b2b", "bg2": "#383838", "bg3": "#333333", "bg1_alt": "#2f2f2f",
        "fg": "#cccccc", "fg_dim": "#999999", "border": "#444444", "border_light": "#555555",
        "accent": "#4a6fa5", "accent_border": "#5a7fb5", "hover": "#505050",
        "scroll": "#555555", "scroll_hover": "#666666", "btn": "#444444", "slider_handle": "#aaaaaa",
        "input_bg": "#3a3a3a", "fg_accent": "#ffffff"
    },
    "Light": {
        "bg1": "#ffffff", "bg2": "#f5f5f5", "bg3": "#e5e5e5", "bg1_alt": "#f0f0f0",
        "fg": "#333333", "fg_dim": "#666666", "border": "#cccccc", "border_light": "#bbbbbb",
        "accent": "#0066cc", "accent_border": "#0055aa", "hover": "#d5d5d5",
        "scroll": "#c0c0c0", "scroll_hover": "#a0a0a0", "btn": "#e0e0e0", "slider_handle": "#666666",
        "input_bg": "#ffffff", "fg_accent": "#ffffff"
    },
    "Dracula": {
        "bg1": "#282a36", "bg2": "#44475a", "bg3": "#21222c", "bg1_alt": "#282a36",
        "fg": "#f8f8f2", "fg_dim": "#6272a4", "border": "#44475a", "border_light": "#6272a4",
        "accent": "#bd93f9", "accent_border": "#ff79c6", "hover": "#6272a4",
        "scroll": "#6272a4", "scroll_hover": "#ff79c6", "btn": "#44475a", "slider_handle": "#ff79c6",
        "input_bg": "#21222c", "fg_accent": "#282a36"
    },
    "Midnight Blue": {
        "bg1": "#0f172a", "bg2": "#1e293b", "bg3": "#0b1120", "bg1_alt": "#0f172a",
        "fg": "#e2e8f0", "fg_dim": "#94a3b8", "border": "#334155", "border_light": "#475569",
        "accent": "#3b82f6", "accent_border": "#60a5fa", "hover": "#334155",
        "scroll": "#475569", "scroll_hover": "#64748b", "btn": "#1e293b", "slider_handle": "#94a3b8",
        "input_bg": "#0b1120", "fg_accent": "#ffffff"
    },
    "Pitch Black": {
        "bg1": "#000000", "bg2": "#111111", "bg3": "#0a0a0a", "bg1_alt": "#050505",
        "fg": "#e0e0e0", "fg_dim": "#777777", "border": "#222222", "border_light": "#333333",
        "accent": "#666666", "accent_border": "#888888", "hover": "#1a1a1a",
        "scroll": "#222222", "scroll_hover": "#444444", "btn": "#151515", "slider_handle": "#888888",
        "input_bg": "#0a0a0a", "fg_accent": "#ffffff"
    },
    "Modern Black": {
        "bg1": "#09090b", "bg2": "#18181b", "bg3": "#121214", "bg1_alt": "#000000",
        "fg": "#fafafa", "fg_dim": "#a1a1aa", "border": "#27272a", "border_light": "#3f3f46",
        "accent": "#ef4444", "accent_border": "#f87171", "hover": "#27272a",
        "scroll": "#3f3f46", "scroll_hover": "#52525b", "btn": "#18181b", "slider_handle": "#a1a1aa",
        "input_bg": "#09090b", "fg_accent": "#ffffff"
    },
    "Modern Dark": {
        "bg1": "#0d0d12", "bg2": "#14141b", "bg3": "#1a1a24", "bg1_alt": "#08080b",
        "fg": "#e2e2ec", "fg_dim": "#8b8b9e", "border": "#2b2b36", "border_light": "#3f3f4e",
        "accent": "#6366f1", "accent_border": "#5a67d8", "hover": "#22222f",
        "scroll": "#3f3f4e", "scroll_hover": "#525266", "btn": "#1c1c26", "slider_handle": "#a5a5b8",
        "input_bg": "#0a0a0f", "fg_accent": "#ffffff"
    },
    "Neutral 2027": {
        "bg1": "#121212", "bg2": "#1a1a1a", "bg3": "#242424", "bg1_alt": "#0d0d0d",
        "fg": "#e6e6e6", "fg_dim": "#a3a3a3", "border": "#2e2e2e", "border_light": "#454545",
        "accent": "#a8a8a8", "accent_border": "#c2c2c2", "hover": "#262626",
        "scroll": "#454545", "scroll_hover": "#5c5c5c", "btn": "#202020", "slider_handle": "#b8b8b8",
        "input_bg": "#141414", "fg_accent": "#ffffff"
    },
    "Forest": {
        "bg1": "#1a251b", "bg2": "#233324", "bg3": "#121a13", "bg1_alt": "#1a251b",
        "fg": "#d4decd", "fg_dim": "#8b9c8a", "border": "#2f4231", "border_light": "#425c44",
        "accent": "#4caf50", "accent_border": "#81c784", "hover": "#2f4231",
        "scroll": "#425c44", "scroll_hover": "#c8e6c9", "btn": "#233324", "slider_handle": "#81c784",
        "input_bg": "#121a13", "fg_accent": "#ffffff"
    }
}

THEMES = {k: _generate_stylesheet(v) for k, v in PALETTES.items()}

