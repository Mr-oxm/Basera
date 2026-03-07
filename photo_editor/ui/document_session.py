"""Document session state for open documents and file tabs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.document import Document
    from .file_tab_bar import FileTabBar


@dataclass
class DocumentSessionEntry:
    document: Document
    path: str | None = None


class DocumentSession:
    """Owns the open-document list and its file-tab representation."""

    def __init__(self, tabs: FileTabBar) -> None:
        self._tabs = tabs
        self._entries: list[DocumentSessionEntry] = []

    def __len__(self) -> int:
        return len(self._entries)

    def add(self, document: Document, path: str | None = None, *, title: str | None = None) -> int:
        entry = DocumentSessionEntry(document=document, path=path)
        self._entries.append(entry)
        label = title or document.name
        tooltip = path or ""
        return self._tabs.add_tab(label, tooltip=tooltip)

    def entry_at(self, index: int) -> DocumentSessionEntry | None:
        if 0 <= index < len(self._entries):
            return self._entries[index]
        return None

    def current_index(self) -> int:
        return self._tabs.current_index()

    def current_entry(self) -> DocumentSessionEntry | None:
        return self.entry_at(self.current_index())

    def activate(self, index: int) -> DocumentSessionEntry | None:
        entry = self.entry_at(index)
        if entry is None:
            return None
        self._tabs.set_current_index(index)
        return entry

    def update_path(self, index: int, path: str) -> None:
        entry = self.entry_at(index)
        if entry is None:
            return
        entry.path = path

    def update_tab_metadata(self, index: int, *, title: str | None = None, tooltip: str | None = None) -> None:
        if title is not None:
            self._tabs.set_tab_text(index, title)
        if tooltip is not None:
            self._tabs.set_tab_tooltip(index, tooltip)

    def close(self, index: int) -> None:
        if 0 <= index < len(self._entries):
            self._entries.pop(index)
            self._tabs.remove_tab(index)