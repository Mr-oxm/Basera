from photo_editor.ui.document_session import DocumentSession


class FakeTabs:
    def __init__(self) -> None:
        self.items = []
        self.current = -1

    def add_tab(self, title: str, tooltip: str = "") -> int:
        self.items.append({"title": title, "tooltip": tooltip})
        self.current = len(self.items) - 1
        return self.current

    def current_index(self) -> int:
        return self.current

    def set_current_index(self, index: int) -> None:
        self.current = index

    def set_tab_text(self, index: int, text: str) -> None:
        self.items[index]["title"] = text

    def set_tab_tooltip(self, index: int, text: str) -> None:
        self.items[index]["tooltip"] = text

    def remove_tab(self, index: int) -> None:
        self.items.pop(index)
        if not self.items:
            self.current = -1
        else:
            self.current = min(self.current, len(self.items) - 1)


class FakeDocument:
    def __init__(self, name: str) -> None:
        self.name = name


def test_document_session_tracks_entries_and_tabs() -> None:
    tabs = FakeTabs()
    session = DocumentSession(tabs)
    doc = FakeDocument("Untitled")

    index = session.add(doc, None, title="Untitled")

    assert index == 0
    assert len(session) == 1
    assert session.current_entry().document is doc
    assert tabs.items[0] == {"title": "Untitled", "tooltip": ""}


def test_document_session_updates_metadata_and_close() -> None:
    tabs = FakeTabs()
    session = DocumentSession(tabs)
    doc = FakeDocument("Doc")

    session.add(doc, None, title="Doc")
    session.update_path(0, "c:/tmp/doc.png")
    session.update_tab_metadata(0, title="doc.png", tooltip="c:/tmp/doc.png")

    assert session.entry_at(0).path == "c:/tmp/doc.png"
    assert tabs.items[0] == {"title": "doc.png", "tooltip": "c:/tmp/doc.png"}

    session.close(0)

    assert len(session) == 0
    assert tabs.current_index() == -1