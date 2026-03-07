"""Filesystem-backed icon helpers for application assets."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon


_APP_ASSET_DIR = Path(__file__).resolve().parents[2] / "assets" / "app"


def app_icon_path(name: str = "logo.png") -> Path:
    return _APP_ASSET_DIR / name


def app_icon(name: str = "logo.png") -> QIcon:
    path = app_icon_path(name)
    return QIcon(str(path)) if path.exists() else QIcon()
