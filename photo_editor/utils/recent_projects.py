"""Recent projects list — persisted to the user's config directory.

Each entry is a dict with keys:
    path   – absolute path to the .basera file
    name   – display name (stem of the file)
    mtime  – last modified time (float, Unix timestamp) for sorting

The list is stored as JSON in:
    Windows : %APPDATA%/Basera/recent_projects.json
    macOS   : ~/Library/Application Support/Basera/recent_projects.json
    Linux   : ~/.config/Basera/recent_projects.json
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


_APP_NAME = "Basera"
_MAX_RECENT = 12


def _config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif os.uname().sysname == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / _APP_NAME


def _recent_file() -> Path:
    return _config_dir() / "recent_projects.json"


def load_recent_projects() -> list[dict]:
    """Return the stored recent-projects list (most-recent first).

    Returns an empty list if the file does not exist or is corrupt.
    Entries whose files no longer exist on disk are silently dropped.
    """
    fp = _recent_file()
    entries: list[dict] = []

    if fp.exists():
        try:
            entries = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            entries = []

    # Prune missing files
    entries = [e for e in entries if Path(e.get("path", "")).exists()]
    return entries[:_MAX_RECENT]


def add_recent_project(path: str | Path) -> None:
    """Record *path* as the most-recently used project.

    Deduplicates by path and trims the list to ``_MAX_RECENT`` entries.
    Safe to call from any thread (file I/O is atomic on most platforms).
    """
    p = Path(path).resolve()
    entries = load_recent_projects()

    # Remove any existing entry for this path
    entries = [e for e in entries if Path(e.get("path", "")).resolve() != p]

    entry = {
        "path": str(p),
        "name": p.stem,
        "mtime": p.stat().st_mtime if p.exists() else time.time(),
    }
    entries.insert(0, entry)
    entries = entries[:_MAX_RECENT]

    fp = _recent_file()
    try:
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # Non-fatal — recent list is a convenience feature


def remove_recent_project(path: str | Path) -> None:
    """Remove *path* from the recent-projects list."""
    p = Path(path).resolve()
    entries = load_recent_projects()
    entries = [e for e in entries if Path(e.get("path", "")).resolve() != p]
    fp = _recent_file()
    try:
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def format_file_size(path: str | Path) -> str:
    """Return a human-readable file size string for *path*."""
    try:
        size = Path(path).stat().st_size
    except OSError:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
