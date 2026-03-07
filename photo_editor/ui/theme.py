"""Professional themes for the photo editor."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from .styles import render_qss


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"Expected a 6-digit hex color, got {value!r}")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _mix(left: str, right: str, ratio: float) -> str:
    left_rgb = _hex_to_rgb(left)
    right_rgb = _hex_to_rgb(right)
    blended = tuple(
        round((1.0 - ratio) * left_channel + ratio * right_channel)
        for left_channel, right_channel in zip(left_rgb, right_rgb)
    )
    return "#{:02x}{:02x}{:02x}".format(*blended)


def _rgba(color: str, alpha: float) -> str:
    red, green, blue = _hex_to_rgb(color)
    return f"rgba({red}, {green}, {blue}, {alpha:.3f})"


def _gradient(*colors: str) -> str:
    stops = []
    last_index = max(len(colors) - 1, 1)
    for index, color in enumerate(colors):
        stop = index / last_index
        stops.append(f"stop:{stop:.3f} {color}")
    return "qlineargradient(x1:0, y1:0, x2:1, y2:1, {})".format(
        ", ".join(stops)
    )


def _build_palette(
    *,
    bg0: str,
    bg1: str,
    bg2: str,
    text: str,
    text_dim: str,
    accent: str,
    accent_alt: str,
    fg_accent: str = "#ffffff",
) -> dict[str, str]:
    border = _mix(bg1, text, 0.14)
    border_light = _mix(bg2, text, 0.22)
    hover = _mix(bg1, text, 0.08)
    btn = _mix(bg1, bg2, 0.56)
    input_bg = _mix(bg0, bg1, 0.72)
    slider_handle = _mix(accent, "#ffffff", 0.36)
    slider_hover = _mix(accent, "#ffffff", 0.52)
    scroll = _mix(bg0, text, 0.22)
    scroll_hover = _mix(scroll, "#ffffff", 0.18)
    panel = _mix(bg1, bg2, 0.38)
    panel_alt = _mix(bg0, bg1, 0.78)
    card = _mix(bg1, bg2, 0.68)
    surface_hover = _mix(panel, text, 0.06)
    surface_pressed = _mix(panel, accent, 0.12)
    outline_soft = _rgba(text, 0.10)
    outline_strong = _rgba(text, 0.18)
    selection_bg = _rgba(accent, 0.24)
    accent_soft = _rgba(accent, 0.18)
    accent_muted = _rgba(accent, 0.10)

    return {
        "bg1": bg0,
        "bg2": bg1,
        "bg3": bg2,
        "bg1_alt": panel_alt,
        "fg": text,
        "fg_dim": text_dim,
        "border": border,
        "border_light": border_light,
        "accent": accent,
        "accent_border": _mix(accent, "#ffffff", 0.18),
        "hover": hover,
        "scroll": scroll,
        "scroll_hover": scroll_hover,
        "btn": btn,
        "slider_handle": slider_handle,
        "slider_hover": slider_hover,
        "input_bg": input_bg,
        "fg_accent": fg_accent,
        "app_bg": bg0,
        "window_gradient": _gradient(bg0, bg1, bg2),
        "menu_bar_bg": _rgba(_mix(bg0, bg1, 0.42), 0.98),
        "menu_bar_border": _rgba(text, 0.08),
        "popup_bg": _rgba(card, 0.985),
        "popup_border": _rgba(text, 0.14),
        "popup_gradient": _gradient(_mix(card, bg2, 0.08), card),
        "toolbar_bg": _rgba(_mix(bg0, bg1, 0.52), 0.96),
        "toolbar_gradient": _gradient(_mix(bg0, bg1, 0.48), _mix(bg1, bg2, 0.34)),
        "toolbar_separator": _rgba(text, 0.10),
        "surface_panel": _rgba(panel, 0.96),
        "surface_panel_alt": _rgba(panel_alt, 0.96),
        "surface_card": _rgba(card, 0.98),
        "surface_panel_gradient": _gradient(_mix(panel_alt, panel, 0.42), panel, _mix(panel, card, 0.24)),
        "surface_card_gradient": _gradient(card, _mix(card, text, 0.025)),
        "surface_hover": surface_hover,
        "surface_pressed": surface_pressed,
        "surface_selected": _mix(panel, accent, 0.10),
        "outline_soft": outline_soft,
        "outline_strong": outline_strong,
        "outline_focus": _rgba(accent_alt, 0.56),
        "accent_soft": accent_soft,
        "accent_muted": accent_muted,
        "accent_hover": _mix(accent, "#ffffff", 0.12),
        "accent_pressed": _mix(accent, "#000000", 0.10),
        "selection_bg": selection_bg,
        "status_bg": _rgba(_mix(bg0, bg1, 0.60), 0.98),
        "status_border": _rgba(text, 0.08),
        "pill_bg": accent_soft,
        "pill_border": _rgba(accent, 0.34),
        "pill_fg": text,
        "tab_idle_bg": _rgba(_mix(bg0, bg1, 0.48), 0.78),
        "tab_hover_bg": _rgba(surface_hover, 0.98),
        "tab_active_bg": _rgba(card, 0.98),
        "tab_border": _rgba(text, 0.10),
        "input_hover": _mix(input_bg, text, 0.05),
        "input_focus": _mix(input_bg, accent_alt, 0.10),
        "input_border": _rgba(text, 0.12),
        "button_bg": _rgba(btn, 0.98),
        "button_bg_gradient": _gradient(_mix(btn, bg2, 0.10), btn),
        "button_hover": _rgba(_mix(btn, text, 0.05), 0.98),
        "button_pressed": _rgba(_mix(btn, accent, 0.12), 0.98),
        "button_border": _rgba(text, 0.12),
        "button_checked": _rgba(_mix(btn, accent, 0.18), 0.98),
        "button_checked_gradient": _gradient(_mix(btn, accent, 0.15), _mix(btn, accent_alt, 0.10)),
        "button_checked_border": _rgba(accent, 0.42),
        "slider_track": _mix(bg0, bg2, 0.68),
        "scroll_track": _rgba(bg0, 0.30),
        "list_item_bg": _rgba(card, 0.92),
        "list_item_hover": _rgba(surface_hover, 0.98),
        "tab_active_gradient": _gradient(card, _mix(card, accent_alt, 0.05)),
    }

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
    "Dark": _build_palette(
        bg0="#1a1a1a",
        bg1="#242424",
        bg2="#2f2f2f",
        text="#e8e8e8",
        text_dim="#9d9d9d",
        accent="#4f8fba",
        accent_alt="#6ec2d1",
    ),
    "Basera Dark": _build_palette(
        bg0="#161722",
        bg1="#1d2030",
        bg2="#272b40",
        text="#edf2ff",
        text_dim="#97a2c3",
        accent="#29d7d7",
        accent_alt="#d85ae3",
    ),
    "Blue Noir": _build_palette(
        bg0="#07111d",
        bg1="#0d1828",
        bg2="#142338",
        text="#e8f1ff",
        text_dim="#8ea5c3",
        accent="#5ea8ff",
        accent_alt="#66d6c8",
    ),
    "Aurora Ink": _build_palette(
        bg0="#0a1113",
        bg1="#121c20",
        bg2="#1a2a30",
        text="#ebf7f6",
        text_dim="#90aca9",
        accent="#4fd1c5",
        accent_alt="#8b7dff",
    ),
    "Copper Dusk": _build_palette(
        bg0="#16100d",
        bg1="#221814",
        bg2="#31211a",
        text="#f6ede7",
        text_dim="#b29b8d",
        accent="#d48a5c",
        accent_alt="#f0b37a",
        fg_accent="#20130e",
    ),
    "Light": _build_palette(
        bg0="#eef2f7",
        bg1="#f7f9fc",
        bg2="#ffffff",
        text="#1b2430",
        text_dim="#617082",
        accent="#2f6fed",
        accent_alt="#0ea5a4",
        fg_accent="#ffffff",
    ),
    "Paper Glass": _build_palette(
        bg0="#f3f0ea",
        bg1="#faf7f2",
        bg2="#fffdf9",
        text="#2b2722",
        text_dim="#7d756b",
        accent="#4f7cff",
        accent_alt="#2fb29a",
        fg_accent="#ffffff",
    ),
    "Dracula": _build_palette(
        bg0="#161821",
        bg1="#212431",
        bg2="#2a3040",
        text="#f6f4ff",
        text_dim="#8c91c8",
        accent="#bd93f9",
        accent_alt="#ff79c6",
        fg_accent="#170f25",
    ),
    "Midnight Blue": _build_palette(
        bg0="#08101d",
        bg1="#101a2b",
        bg2="#17253a",
        text="#e7f0ff",
        text_dim="#88a1c4",
        accent="#57a5ff",
        accent_alt="#7ee0ff",
    ),
    "Pitch Black": _build_palette(
        bg0="#020304",
        bg1="#090b0f",
        bg2="#12151a",
        text="#f2f5f7",
        text_dim="#7d8792",
        accent="#8ea3b8",
        accent_alt="#c7d0db",
        fg_accent="#0a0c0f",
    ),
    "Modern Black": _build_palette(
        bg0="#050608",
        bg1="#0d1015",
        bg2="#171b22",
        text="#fafbfc",
        text_dim="#9ca8b8",
        accent="#ff6b6b",
        accent_alt="#ffb86b",
    ),
    "Modern Dark": _build_palette(
        bg0="#0b0d12",
        bg1="#121621",
        bg2="#1a2030",
        text="#edf2ff",
        text_dim="#909ab2",
        accent="#7c8cff",
        accent_alt="#45d0c7",
    ),
    "Neutral 2027": _build_palette(
        bg0="#111315",
        bg1="#171a1e",
        bg2="#1f252c",
        text="#f1f3f5",
        text_dim="#9aa3ad",
        accent="#c5ced8",
        accent_alt="#95a4b3",
        fg_accent="#111315",
    ),
    "Forest": _build_palette(
        bg0="#0a120d",
        bg1="#122019",
        bg2="#1c3024",
        text="#edf7ee",
        text_dim="#90a996",
        accent="#5ecf8d",
        accent_alt="#9ce7ba",
        fg_accent="#092012",
    ),
}

THEMES = {k: _generate_stylesheet(v) for k, v in PALETTES.items()}

