"""Helpers for loading palette-driven QSS templates from the ui/css folder."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


_CSS_DIR = Path(__file__).with_name("css")


class QssTemplate(str):
    """String template that can inject the active theme palette before formatting."""

    def _with_active_palette(self) -> str:
        try:
            from .theme import ThemeManager

            palette = ThemeManager.instance().active_palette
        except Exception:
            palette = None

        qss = str(self)
        if not palette:
            return qss

        for key, value in palette.items():
            qss = qss.replace(f"[[{key}]]", str(value))
        return qss

    def format(self, /, *args: object, **kwargs: object) -> str:
        return self._with_active_palette().format(*args, **kwargs)


@lru_cache(maxsize=None)
def load_qss_template(name: str) -> str:
    """Return the raw QSS template contents for *name*."""
    path = _CSS_DIR / name
    return QssTemplate(path.read_text(encoding="utf-8"))


def render_qss(name: str, palette: dict | None = None, **tokens: object) -> str:
    """Render a QSS template using ``[[token]]`` placeholders."""
    values: dict[str, object] = {}
    if palette:
        values.update(palette)
    values.update(tokens)

    qss = load_qss_template(name)
    for key, value in values.items():
        qss = qss.replace(f"[[{key}]]", str(value))
    return qss


def format_qss(name: str, **tokens: object) -> str:
    """Render a ``str.format``-style QSS template."""
    return load_qss_template(name).format(**tokens)


def themed_value(palette: dict, key: str, fallback: str | None = None) -> str:
    """Return a palette value with an optional fallback."""
    if key in palette:
        return str(palette[key])
    if fallback is None:
        raise KeyError(key)
    return fallback
