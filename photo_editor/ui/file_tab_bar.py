"""File tab bar — shows tabs for each open document with close buttons."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor
from PySide6.QtWidgets import QTabBar, QWidget, QHBoxLayout, QToolButton, QStyle

from .styles import render_qss


class _CloseButton(QToolButton):
    """A tiny × button drawn manually so it's always visible."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoRaise(True)
        from .theme import ThemeManager
        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._apply_theme(ThemeManager.instance().active_palette)

    def _apply_theme(self, palette: dict) -> None:
        self.setStyleSheet(render_qss("file_close_button.qss", palette))
        self._color_normal = QColor(palette['fg_dim'])
        self._color_hover = QColor(palette['fg'])

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self._color_hover if self.underMouse() else self._color_normal
        pen = QPen(color)
        pen.setWidthF(1.5)
        p.setPen(pen)
        m = 4
        w, h = self.width(), self.height()
        p.drawLine(m, m, w - m, h - m)
        p.drawLine(w - m, m, m, h - m)
        p.end()


class _CloseButtonContainer(QWidget):
    """Inset container that keeps the close button inside the tab bounds."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setFixedSize(20, 18)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 4, 2)
        layout.setSpacing(0)

        self.button = _CloseButton(self)
        layout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignCenter)


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

        layout.addWidget(self._tab_bar)
        layout.addStretch()

        self.setFixedHeight(32)
        
        from .theme import ThemeManager
        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._apply_theme(ThemeManager.instance().active_palette)

    def _apply_theme(self, palette: dict) -> None:
        self._tab_bar.setStyleSheet(render_qss("file_tabs.qss", palette))
        self.setStyleSheet(f"background: {palette['bg2']};")

    # ---- Public API ---------------------------------------------------------

    def add_tab(self, title: str, tooltip: str = "") -> int:
        """Add a new tab and return its index."""
        idx = self._tab_bar.addTab(title)
        if tooltip:
            self._tab_bar.setTabToolTip(idx, tooltip)
        # Inset the close button inside a small container so it doesn't spill past the tab edge.
        container = _CloseButtonContainer(self._tab_bar)
        btn = container.button
        btn.clicked.connect(lambda _=False, b=btn: self._on_close_clicked(b))
        self._tab_bar.setTabButton(idx, QTabBar.ButtonPosition.RightSide, container)
        self._tab_bar.setCurrentIndex(idx)
        return idx

    def _on_close_clicked(self, btn) -> None:
        """Resolve the actual current index of the tab (may shift after removals)."""
        # Find via the button reference
        for i in range(self._tab_bar.count()):
            tab_button = self._tab_bar.tabButton(i, QTabBar.ButtonPosition.RightSide)
            if tab_button is btn:
                self.tab_close_requested.emit(i)
                return
            if hasattr(tab_button, "button") and tab_button.button is btn:
                self.tab_close_requested.emit(i)
                return

    def remove_tab(self, index: int) -> None:
        """Remove a tab by index."""
        self._tab_bar.removeTab(index)

    def set_tab_text(self, index: int, text: str) -> None:
        """Update the title of a tab."""
        self._tab_bar.setTabText(index, text)

    def set_tab_tooltip(self, index: int, text: str) -> None:
        """Update the tooltip of a tab."""
        self._tab_bar.setTabToolTip(index, text)

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
