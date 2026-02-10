"""File tab bar — shows tabs for each open document with close buttons."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor
from PySide6.QtWidgets import QTabBar, QWidget, QHBoxLayout, QToolButton, QStyle


class _CloseButton(QToolButton):
    """A tiny × button drawn manually so it's always visible."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                border-radius: 3px;
                padding: 0px;
            }
            QToolButton:hover {
                background: #555;
            }
        """)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#ccc") if self.underMouse() else QColor("#888")
        pen = QPen(color)
        pen.setWidthF(1.5)
        p.setPen(pen)
        m = 4
        w, h = self.width(), self.height()
        p.drawLine(m, m, w - m, h - m)
        p.drawLine(w - m, m, m, h - m)
        p.end()


class FileTabBar(QWidget):
    """Horizontal tab bar for open document tabs with close buttons."""

    tab_selected = Signal(int)      # index of selected tab
    tab_close_requested = Signal(int)  # index of tab to close

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tab_bar = QTabBar()
        self._tab_bar.setTabsClosable(False)  # We add our own close buttons
        self._tab_bar.setMovable(True)
        self._tab_bar.setExpanding(False)      # Left-aligned tabs
        self._tab_bar.setDrawBase(False)
        self._tab_bar.setElideMode(Qt.TextElideMode.ElideRight)

        self._tab_bar.currentChanged.connect(self.tab_selected.emit)

        self._tab_bar.setStyleSheet("""
            QTabBar {
                background: #1e1e1e;
                border: none;
            }
            QTabBar::tab {
                background: #2d2d2d;
                color: #888;
                padding: 5px 28px 5px 10px;
                border: none;
                border-right: 1px solid #1e1e1e;
                min-width: 80px;
                max-width: 220px;
            }
            QTabBar::tab:selected {
                background: #1e1e1e;
                color: #fff;
            }
            QTabBar::tab:hover:!selected {
                background: #383838;
                color: #ccc;
            }
        """)

        layout.addWidget(self._tab_bar)
        layout.addStretch()

        self.setFixedHeight(30)
        self.setStyleSheet("background: #1e1e1e;")

    # ---- Public API ---------------------------------------------------------

    def add_tab(self, title: str, tooltip: str = "") -> int:
        """Add a new tab and return its index."""
        idx = self._tab_bar.addTab(title)
        if tooltip:
            self._tab_bar.setTabToolTip(idx, tooltip)
        # Add a custom close button (manually drawn × so it's always visible)
        btn = _CloseButton(self._tab_bar)
        btn.clicked.connect(lambda _=False, i=idx: self._on_close_clicked(i))
        self._tab_bar.setTabButton(idx, QTabBar.ButtonPosition.RightSide, btn)
        self._tab_bar.setCurrentIndex(idx)
        return idx

    def _on_close_clicked(self, index: int) -> None:
        """Resolve the actual current index of the tab (may shift after removals)."""
        # The captured index may be stale; find via the button reference
        btn = self.sender()
        for i in range(self._tab_bar.count()):
            if self._tab_bar.tabButton(i, QTabBar.ButtonPosition.RightSide) is btn:
                self.tab_close_requested.emit(i)
                return
        # Fallback
        self.tab_close_requested.emit(index)

    def remove_tab(self, index: int) -> None:
        """Remove a tab by index."""
        self._tab_bar.removeTab(index)

    def set_tab_text(self, index: int, text: str) -> None:
        """Update the title of a tab."""
        self._tab_bar.setTabText(index, text)

    def set_tab_modified(self, index: int, modified: bool = True) -> None:
        """Show a dot/indicator that the document has unsaved changes."""
        text = self._tab_bar.tabText(index)
        if modified and not text.endswith(" •"):
            self._tab_bar.setTabText(index, text + " •")
        elif not modified and text.endswith(" •"):
            self._tab_bar.setTabText(index, text[:-2])

    def current_index(self) -> int:
        return self._tab_bar.currentIndex()

    def set_current_index(self, index: int) -> None:
        self._tab_bar.setCurrentIndex(index)

    def count(self) -> int:
        return self._tab_bar.count()

    def tab_text(self, index: int) -> str:
        return self._tab_bar.tabText(index)
