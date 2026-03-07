"""Professional themes for the photo editor."""

from PySide6.QtCore import QObject, Signal

from .styles import render_qss

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
    return render_qss("base.qss", palette)

PALETTES = {
    "Dark": {
        "bg1": "#2b2b2b", "bg2": "#383838", "bg3": "#333333", "bg1_alt": "#2f2f2f",
        "fg": "#cccccc", "fg_dim": "#999999", "border": "#444444", "border_light": "#555555",
        "accent": "#4a6fa5", "accent_border": "#5a7fb5", "hover": "#505050",
        "scroll": "#555555", "scroll_hover": "#666666", "btn": "#444444", "slider_handle": "#aaaaaa",
        "input_bg": "#3a3a3a", "fg_accent": "#ffffff"
    },
    "Light": {
        "bg1": "#e5e5e5", "bg2": "#f5f5f5", "bg3": "#ffffff", "bg1_alt": "#e0e0e0",
        "fg": "#333333", "fg_dim": "#666666", "border": "#cccccc", "border_light": "#bbbbbb",
        "accent": "#0066cc", "accent_border": "#0055aa", "hover": "#d5d5d5",
        "scroll": "#c0c0c0", "scroll_hover": "#a0a0a0", "btn": "#e0e0e0", "slider_handle": "#666666",
        "input_bg": "#ffffff", "fg_accent": "#ffffff"
    },
    "Dracula": {
        "bg1": "#21222c", "bg2": "#44475a", "bg3": "#282a36", "bg1_alt": "#21222c",
        "fg": "#f8f8f2", "fg_dim": "#6272a4", "border": "#44475a", "border_light": "#6272a4",
        "accent": "#bd93f9", "accent_border": "#ff79c6", "hover": "#6272a4",
        "scroll": "#6272a4", "scroll_hover": "#ff79c6", "btn": "#44475a", "slider_handle": "#ff79c6",
        "input_bg": "#282a36", "fg_accent": "#282a36"
    },
    "Midnight Blue": {
        "bg1": "#0b1120", "bg2": "#1e293b", "bg3": "#0f172a", "bg1_alt": "#0b1120",
        "fg": "#e2e8f0", "fg_dim": "#94a3b8", "border": "#334155", "border_light": "#475569",
        "accent": "#3b82f6", "accent_border": "#60a5fa", "hover": "#334155",
        "scroll": "#475569", "scroll_hover": "#64748b", "btn": "#1e293b", "slider_handle": "#94a3b8",
        "input_bg": "#0f172a", "fg_accent": "#ffffff"
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
        "bg1": "#121a13", "bg2": "#233324", "bg3": "#1a251b", "bg1_alt": "#121a13",
        "fg": "#d4decd", "fg_dim": "#8b9c8a", "border": "#2f4231", "border_light": "#425c44",
        "accent": "#4caf50", "accent_border": "#81c784", "hover": "#2f4231",
        "scroll": "#425c44", "scroll_hover": "#c8e6c9", "btn": "#233324", "slider_handle": "#81c784",
        "input_bg": "#1a251b", "fg_accent": "#ffffff"
    }
}

THEMES = {k: _generate_stylesheet(v) for k, v in PALETTES.items()}

